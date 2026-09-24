# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Code/delivery correlation, delivery read model and review view.

Requirement refs: FR-G08, FR-G09, FR-R01, FR-R02, FR-R05, FR-R06, FR-B10,
FR-B11, INV-05, INV-07, INV-08, AC15..AC21, AC32, PF10, PF11.

Rules
* Correlation to native issues: existing ``MergeRequestLink`` → explicit
  references in branch/title/description (``PH-<uuid>``, ``workItemId: <uuid>``,
  Plane ``ABC-12``) resolved **only inside the project the repository is bound
  to** → commit/sha matches. The payload never selects a workspace.
* Commit messages are stored as *claims* only; they never become evidence (AC15).
* A merge is one business fact per ``merge:<binding>:<mr>`` regardless of how
  many raw sources report it (native activity, webhook, redelivery, poll) (PF10).
* Delivery history is append-only; a rollback/revert is a new row that
  ``reverts`` the previous one (FR-R06). Older events never regress the
  current projection because the projection orders by ``occurred_at`` (AC21).
* ``delivery_summary`` only states provider-known facts (AC32): a native
  "Done" state or a finished run is never a deployment (PF11, AC19).
"""

import logging
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from ..adapters import get_adapter
from ..adapters.base import (
    CHECK,
    DEPLOYMENT,
    MR_KINDS,
    PUSH,
    RELEASE,
    RepoRef,
    TransportError,
    parse_references,
)
from ..models import (
    Delivery,
    Evidence,
    ExternalLink,
    MergeRequestLink,
    PackageProfile,
    PackageRevision,
    RepositoryBinding,
    ReviewApproval,
    SyncConflict,
)
from . import events

logger = logging.getLogger("plane.package_flow.delivery")

NOT_INTEGRATED = "not_integrated"
PARTIALLY_INTEGRATED = "partially_integrated"
INTEGRATED = "integrated"
DEPLOYED = "deployed"
RELEASED = "released"
ROLLED_BACK = "rolled_back"
UNKNOWN = "unknown"
RANK = {NOT_INTEGRATED: 0, INTEGRATED: 1, DEPLOYED: 2, RELEASED: 3}

CI_KINDS = ("build", "test", "lint")
MAX_COMMITS = 200


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _source(n=None, inbound=None, kind="provider_webhook", **extra):
    src = {"kind": kind}
    if inbound is not None:
        src["inbound_event_id"] = str(inbound.id)
        if isinstance(inbound.payload, dict) and "polled" in inbound.payload:
            src["kind"] = "provider_poll"
    if n is not None:
        src.update(provider=n.provider, external_event_id=n.external_event_id, raw_type=n.raw_type)
    src.update(extra)
    return src


def _emit(
    binding_or_issue,
    issue,
    event_type,
    aggregate_type,
    aggregate_id,
    payload,
    dedup,
    n=None,
    summary="",
    occurred_at=None,
    actor_id=None,
    source_kind="provider",
):
    connection = getattr(binding_or_issue, "connection", None)
    return events.emit(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue_id=issue.id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_kind="system",
        actor_id=actor_id or (f"{connection.provider}:{connection.id}" if connection else "plane-native"),
        payload=payload,
        occurred_at=occurred_at or (n.occurred_at if n else None),
        deduplication_key=dedup[:255],
        source_kind=source_kind,
        source_id=connection.provider if connection else "plane",
        source_instance_id=str(connection.id) if connection else "local",
        summary=summary,
    )


def resolve_references(binding, refs):
    """Resolve correlation hints to native issues of the binding's project only."""
    from plane.db.models import Issue

    found, seen = [], set()
    for ref in refs or []:
        qs = Issue.all_objects.filter(project_id=binding.project_id, deleted_at__isnull=True)
        if ref.get("type") == "uuid":
            qs = qs.filter(id=ref["value"])
        elif ref.get("type") == "sequence":
            qs = qs.filter(project__identifier__iexact=ref["identifier"], sequence_id=ref["sequence"])
        else:
            continue
        issue = qs.first()
        if issue is not None and issue.id not in seen:
            seen.add(issue.id)
            found.append(issue)
    return found


def _add_source(delivery, source):
    detail = dict(delivery.detail or {})
    sources = list(detail.get("sources") or [])
    key = (source.get("kind"), source.get("inbound_event_id"), source.get("external_event_id"), source.get("ref"))
    if not any(
        (s.get("kind"), s.get("inbound_event_id"), s.get("external_event_id"), s.get("ref")) == key for s in sources
    ):
        sources.append(source)
    detail["sources"] = sources
    delivery.detail = detail


def _create_delivery(issue, dedup_key, **fields):
    """Insert a delivery row once per ``(issue, dedup_key)``; returns (row, created)."""
    existing = Delivery.objects.filter(issue=issue, dedup_key=dedup_key, deleted_at__isnull=True).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            return Delivery.objects.create(issue=issue, dedup_key=dedup_key, **fields), True
    except IntegrityError:
        return Delivery.objects.get(issue=issue, dedup_key=dedup_key, deleted_at__isnull=True), False


# ---------------------------------------------------------------------------
# event handling
# ---------------------------------------------------------------------------


def handle_code_event(connection, n, *, inbound=None, adapter=None) -> bool:
    """Apply one normalized repository event. Workspace scope = the connection's workspace."""
    if not n.repository_external_id:
        return False
    bindings = RepositoryBinding.objects.select_related("connection").filter(
        connection=connection,
        workspace_id=connection.workspace_id,
        external_id=n.repository_external_id,
        is_active=True,
        deleted_at__isnull=True,
    )
    handled = False
    for binding in bindings:
        if n.kind in MR_KINDS:
            handled = _handle_mr(binding, n, inbound) or handled
        elif n.kind == CHECK:
            handled = _handle_check(binding, n, inbound) or handled
        elif n.kind == PUSH:
            handled = _handle_push(binding, n, inbound) or handled
        elif n.kind == DEPLOYMENT:
            handled = _handle_deployment(binding, n, inbound, adapter) or handled
        elif n.kind == RELEASE:
            handled = _handle_release(binding, n, inbound, adapter) or handled
    return handled


def invalidate_code_approvals(link, new_head, reason_prefix="new head"):
    now = timezone.now()
    count = 0
    for approval in (
        ReviewApproval.objects.select_for_update()
        .filter(merge_request=link, kind=ReviewApproval.Kind.CODE, invalidated_at__isnull=True, deleted_at__isnull=True)
        .exclude(head_sha=new_head)
    ):
        approval.invalidated_at = now
        approval.invalidated_reason = f"{reason_prefix}: {approval.head_sha[:12]} -> {new_head[:12]}"[:255]
        approval.save(update_fields=["invalidated_at", "invalidated_reason", "updated_at"])
        events.emit(
            workspace_id=link.workspace_id,
            project_id=link.project_id,
            issue_id=link.issue_id,
            event_type="review.invalidated",
            aggregate_type="review",
            aggregate_id=approval.id,
            actor_kind="system",
            actor_id="review-gate",
            payload={"approvalId": str(approval.id), "approvedHead": approval.head_sha, "newHead": new_head},
            deduplication_key=f"review.invalidated:{approval.id}",
            summary="Code approval invalidated by a new head",
        )
        count += 1
    return count


def _merge_commits(link, commits):
    known = {c.get("sha") for c in link.commits or []}
    merged = list(link.commits or [])
    for c in commits or []:
        if c.get("sha") and c["sha"] not in known:
            # Commit messages are claims, never proof (J07, AC15).
            merged.append(
                {
                    "sha": c["sha"],
                    "message": (c.get("message") or "")[:2000],
                    "timestamp": c.get("timestamp"),
                    "status": "claimed",
                }
            )
            known.add(c["sha"])
    link.commits = merged[-MAX_COMMITS:]


def _handle_mr(binding, n, inbound) -> bool:
    link = (
        MergeRequestLink.objects.select_for_update()
        .filter(repository_binding=binding, external_id=n.mr_external_id, deleted_at__isnull=True)
        .first()
    )
    if link is None:
        issues = resolve_references(binding, n.correlation)
        if not issues:
            if n.mr_state == "merged" and (n.reverts_mr_external_id or n.reverts_commit_sha):
                return _handle_revert(binding, n, inbound)
            return False
        link = MergeRequestLink(
            issue=issues[0],
            repository_binding=binding,
            external_id=n.mr_external_id,
            source_branch=n.source_branch or "",
            target_branch=n.target_branch or "",
        )
    is_late = bool(link.last_event_at and n.occurred_at and n.occurred_at < link.last_event_at)
    if not is_late:
        link.title = (n.mr_title or link.title)[:500]
        link.url = n.url or link.url
        link.source_branch = n.source_branch or link.source_branch
        link.target_branch = n.target_branch or link.target_branch
        link.target_sha = n.target_sha or link.target_sha
        if n.occurred_at:
            link.last_event_at = n.occurred_at
    head_changed = False
    old_head = link.head_sha
    if n.head_sha and not is_late and link.state != "merged" and n.head_sha != link.head_sha:
        link.head_sha = n.head_sha
        head_changed = bool(old_head)
    elif n.head_sha and not link.head_sha:
        link.head_sha = n.head_sha
    if n.mr_state == "merged":
        # Merge is terminal and never regressed by a late update (AC21).
        link.state = "merged"
        link.merged_commit_sha = n.merged_commit_sha or link.merged_commit_sha
        link.merge_method = n.merge_method or link.merge_method
        if link.pending_merge:
            link.pending_merge = {**link.pending_merge, "confirmed_at": timezone.now().isoformat()}
    elif not is_late and link.state != "merged":
        link.state = n.mr_state or link.state
    _merge_commits(link, n.commits)
    link.save()
    if head_changed:
        invalidate_code_approvals(link, link.head_sha)
    issue = link.issue
    _emit(
        binding,
        issue,
        "git.mr.observed",
        "package",
        issue.id,
        {
            "bindingId": str(binding.id),
            "mergeRequestId": link.external_id,
            "state": link.state,
            "headSha": link.head_sha,
            "late": is_late,
        },
        f"mr:{binding.id}:{link.external_id}:{n.head_sha}:{n.mr_state}",
        n=n,
    )
    if n.mr_state == "merged":
        record_merge(
            issue,
            binding,
            link,
            merged_commit_sha=link.merged_commit_sha,
            occurred_at=n.occurred_at,
            source=_source(n, inbound),
        )
        if n.reverts_mr_external_id or n.reverts_commit_sha:
            _handle_revert(binding, n, inbound)
    return True


def record_merge(issue, binding, link, *, merged_commit_sha="", occurred_at=None, source=None):
    """One integrated delivery + one ``git.merge.observed`` per binding/MR (PF10, FR-G08)."""
    key = f"merge:{binding.id}:{link.external_id}"
    source = source or {"kind": "unknown"}
    delivery, created = _create_delivery(
        issue,
        key,
        repository_binding=binding,
        stage=Delivery.Stage.INTEGRATED,
        commit_sha=merged_commit_sha or "",
        source=source.get("provider") or source.get("kind") or "provider",
        trust="provider" if source.get("kind", "").startswith("provider") else "native",
        occurred_at=occurred_at or timezone.now(),
        detail={"merge_request_id": link.external_id, "merge_method": link.merge_method, "sources": []},
    )
    _add_source(delivery, source)
    update = ["detail", "updated_at"]
    if merged_commit_sha and delivery.commit_sha != merged_commit_sha:
        # The provider-reported merged/squash commit wins over a missing/native value (FR-G08).
        delivery.commit_sha = merged_commit_sha
        update.append("commit_sha")
    delivery.save(update_fields=update)
    event, _ = _emit(
        binding,
        issue,
        "git.merge.observed",
        "package",
        issue.id,
        {
            "bindingId": str(binding.id),
            "repository": binding.path_with_namespace,
            "mergeRequestId": link.external_id,
            "mergedCommitSha": merged_commit_sha,
            "mergeMethod": link.merge_method,
            "deliveryId": str(delivery.id),
        },
        key,
        occurred_at=delivery.occurred_at,
        summary=f"Merge observed in {binding.path_with_namespace}",
    )
    return delivery, created


def observe_native_merge(
    issue, binding, mr_external_id, *, merged_commit_sha="", occurred_at=None, ref="native-activity"
):
    """Native Plane activity path (e.g. upstream GitHub sync / issue activity) for a merge.

    Correlates with the webhook path through the same dedup key (PF10).
    """
    with transaction.atomic():
        link = (
            MergeRequestLink.objects.select_for_update()
            .filter(repository_binding=binding, external_id=str(mr_external_id), deleted_at__isnull=True)
            .first()
        )
        if link is None:
            link = MergeRequestLink.objects.create(
                issue=issue,
                repository_binding=binding,
                external_id=str(mr_external_id),
                source_branch="",
                target_branch=binding.default_branch,
            )
        if link.state != "merged":
            link.state = "merged"
            link.merged_commit_sha = link.merged_commit_sha or merged_commit_sha
            link.save(update_fields=["state", "merged_commit_sha", "updated_at"])
        return record_merge(
            link.issue,
            binding,
            link,
            merged_commit_sha=link.merged_commit_sha or merged_commit_sha,
            occurred_at=occurred_at,
            source={"kind": "native_activity", "ref": ref},
        )


def _latest_delivery(issue, binding, environment=None):
    qs = Delivery.objects.filter(issue=issue, repository_binding=binding, deleted_at__isnull=True).exclude(
        stage=Delivery.Stage.ROLLED_BACK
    )
    if environment:
        qs = qs.filter(environment=environment)
    return qs.order_by("-occurred_at", "-created_at").first()


def record_rollback(issue, binding, *, environment, commit_sha, occurred_at, source, dedup_key, reason, reverts=None):
    reverts = reverts or _latest_delivery(issue, binding, environment or None)
    delivery, created = _create_delivery(
        issue,
        dedup_key,
        repository_binding=binding,
        stage=Delivery.Stage.ROLLED_BACK,
        commit_sha=commit_sha or "",
        environment=environment or "",
        source=source.get("provider") or source.get("kind") or "provider",
        trust="provider",
        occurred_at=occurred_at or timezone.now(),
        reverts=reverts,
        detail={"reason": reason, "follow_up_required": True, "sources": [source]},
    )
    if created:
        _emit(
            binding,
            issue,
            "delivery.rolled_back",
            "delivery",
            delivery.id,
            {
                "bindingId": str(binding.id),
                "environment": environment,
                "reason": reason,
                "revertsDeliveryId": str(reverts.id) if reverts else None,
            },
            f"rollback:{dedup_key}",
            occurred_at=delivery.occurred_at,
            summary=f"Rollback observed ({reason})",
        )
    return delivery, created


def _handle_revert(binding, n, inbound) -> bool:
    targets = []
    if n.reverts_mr_external_id:
        link = MergeRequestLink.objects.filter(
            repository_binding=binding, external_id=n.reverts_mr_external_id, deleted_at__isnull=True
        ).first()
        if link is not None:
            targets.append(link.issue)
    if n.reverts_commit_sha:
        for d in Delivery.objects.filter(
            repository_binding=binding, commit_sha__startswith=n.reverts_commit_sha, deleted_at__isnull=True
        ).select_related("issue"):
            if d.issue not in targets:
                targets.append(d.issue)
    for issue in targets:
        record_rollback(
            issue,
            binding,
            environment="",
            commit_sha=n.merged_commit_sha,
            occurred_at=n.occurred_at,
            source=_source(n, inbound),
            dedup_key=f"revert:{binding.id}:{n.mr_external_id}",
            reason="revert_merged",
        )
    return bool(targets)


def _issues_for_commit(binding, sha, mr_external_id="", branch=""):
    from plane.db.models import Issue

    ids = set()
    cond = Q()
    if mr_external_id:
        cond |= Q(external_id=mr_external_id)
    if sha:
        cond |= Q(head_sha=sha) | Q(merged_commit_sha=sha)
    if cond:
        ids.update(
            MergeRequestLink.objects.filter(cond, repository_binding=binding, deleted_at__isnull=True).values_list(
                "issue_id", flat=True
            )
        )
    if sha:
        ids.update(
            Delivery.objects.filter(repository_binding=binding, commit_sha=sha, deleted_at__isnull=True).values_list(
                "issue_id", flat=True
            )
        )
    if branch:
        ids.update(i.id for i in resolve_references(binding, parse_references(branch)))
    return list(Issue.all_objects.filter(id__in=ids, deleted_at__isnull=True))


def _handle_check(binding, n, inbound) -> bool:
    if n.check_status == "running":
        return False  # not a result
    result = {
        "passed": Evidence.Result.PASSED,
        "failed": Evidence.Result.FAILED,
        "cancelled": Evidence.Result.NOT_RUN,
    }.get(n.check_status, Evidence.Result.UNKNOWN)
    issues = _issues_for_commit(binding, n.head_sha, n.mr_external_id, n.source_branch)
    for issue in issues:
        key = f"check:{binding.connection_id}:{n.check_id}:{n.check_status}:{n.head_sha}"[:255]
        try:
            with transaction.atomic():
                ev = Evidence.objects.create(
                    issue=issue,
                    kind=n.check_kind or "build",
                    name=(n.check_name or "check")[:255],
                    source=f"{n.provider}:ci",
                    trust=Evidence.Trust.PROVIDER_CI,
                    result=result,
                    repository_binding=binding,
                    commit_sha=n.head_sha or "",
                    occurred_at=n.occurred_at or timezone.now(),
                    url=(n.url or "")[:1000],
                    detail={"check_id": n.check_id, "sources": [_source(n, inbound)]},
                    dedup_key=key,
                )
        except IntegrityError:
            continue
        _emit(
            binding,
            issue,
            "ci.check.observed",
            "package",
            issue.id,
            {"evidenceId": str(ev.id), "name": ev.name, "result": ev.result, "commitSha": ev.commit_sha},
            f"check:{binding.id}:{n.check_id}:{n.check_status}:{issue.id}",
            n=n,
        )
    return bool(issues)


def _handle_push(binding, n, inbound) -> bool:
    handled = False
    for link in MergeRequestLink.objects.select_for_update().filter(
        repository_binding=binding, source_branch=n.source_branch, state="open", deleted_at__isnull=True
    ):
        is_late = bool(link.last_event_at and n.occurred_at and n.occurred_at < link.last_event_at)
        _merge_commits(link, n.commits)
        old = link.head_sha
        if n.head_sha and not is_late and n.head_sha != old:
            link.head_sha = n.head_sha
            if n.occurred_at:
                link.last_event_at = n.occurred_at
        link.save()
        if old and link.head_sha != old:
            invalidate_code_approvals(link, link.head_sha)
        handled = True
    for issue in resolve_references(binding, n.correlation):
        for c in n.commits or []:
            _emit(
                binding,
                issue,
                "git.commit.observed",
                "package",
                issue.id,
                # The message is shown as a claim; it is never evidence (AC15).
                {
                    "bindingId": str(binding.id),
                    "sha": c.get("sha"),
                    "branch": n.source_branch,
                    "message": (c.get("message") or "")[:500],
                    "messageStatus": "claimed",
                },
                f"commit:{binding.id}:{c.get('sha')}:{issue.id}",
                n=n,
            )
        handled = True
    return handled


def _contains(adapter, binding, ancestor, descendant):
    if not adapter or not ancestor or not descendant:
        return None
    if ancestor == descendant:
        return True
    from .integrations import provider_context

    try:
        return adapter.contains_commit(
            provider_context(binding.connection),
            RepoRef(binding.external_id, binding.path_with_namespace),
            ancestor,
            descendant,
        )
    except TransportError:
        return None


def _handle_deployment(binding, n, inbound, adapter) -> bool:
    if n.deployment_status != "success" or not n.environment:
        return False
    adapter = adapter or get_adapter(binding.connection.provider)
    source = _source(n, inbound)
    handled = False
    if n.is_rollback:
        # Every issue currently deployed in this environment whose commit is not contained in the
        # rollback target is rolled back (history kept).
        for issue_id in set(
            Delivery.objects.filter(
                repository_binding=binding,
                environment=n.environment,
                stage=Delivery.Stage.DEPLOYED,
                deleted_at__isnull=True,
            ).values_list("issue_id", flat=True)
        ):
            current = (
                Delivery.objects.filter(
                    issue_id=issue_id, repository_binding=binding, environment=n.environment, deleted_at__isnull=True
                )
                .order_by("-occurred_at", "-created_at")
                .first()
            )
            if current is None or current.stage != Delivery.Stage.DEPLOYED:
                continue
            if _contains(adapter, binding, current.commit_sha, n.head_sha) is True:
                continue
            record_rollback(
                current.issue,
                binding,
                environment=n.environment,
                commit_sha=n.head_sha,
                occurred_at=n.occurred_at,
                source=source,
                dedup_key=f"rollback:{binding.id}:{n.deployment_id or n.head_sha}:{n.environment}",
                reason="deployment_rollback",
                reverts=current,
            )
            handled = True
        return handled

    issues = {i.id: i for i in _issues_for_commit(binding, n.head_sha)}
    for i in resolve_references(binding, n.correlation):
        issues.setdefault(i.id, i)
    # Merged work contained in the deployed commit (provider ancestry check when supported).
    for d in (
        Delivery.objects.select_related("issue")
        .filter(repository_binding=binding, stage=Delivery.Stage.INTEGRATED, deleted_at__isnull=True)
        .exclude(issue_id__in=list(issues))
        .exclude(commit_sha="")
        .order_by("-occurred_at")[:50]
    ):
        if _contains(adapter, binding, d.commit_sha, n.head_sha) is True:
            issues.setdefault(d.issue_id, d.issue)
    for issue in issues.values():
        delivery, created = _create_delivery(
            issue,
            f"deploy:{binding.id}:{n.deployment_id or n.head_sha}:{n.environment}",
            repository_binding=binding,
            stage=Delivery.Stage.DEPLOYED,
            commit_sha=n.head_sha,
            environment=n.environment,
            source=n.provider,
            trust="provider",
            occurred_at=n.occurred_at or timezone.now(),
            detail={"deployment_id": n.deployment_id, "url": n.url, "sources": [source]},
        )
        if created:
            _emit(
                binding,
                issue,
                "deployment.observed",
                "delivery",
                delivery.id,
                {
                    "bindingId": str(binding.id),
                    "environment": n.environment,
                    "commitSha": n.head_sha,
                    "deploymentId": n.deployment_id,
                },
                f"deployment:{binding.id}:{n.deployment_id or n.head_sha}:{n.environment}:{issue.id}",
                n=n,
                summary=f"Deployment to {n.environment} observed",
            )
        handled = True
    return handled


def _handle_release(binding, n, inbound, adapter) -> bool:
    adapter = adapter or get_adapter(binding.connection.provider)
    issues = {i.id: i for i in _issues_for_commit(binding, n.head_sha)} if n.head_sha else {}
    if n.head_sha:
        for d in (
            Delivery.objects.select_related("issue")
            .filter(
                repository_binding=binding,
                stage__in=(Delivery.Stage.INTEGRATED, Delivery.Stage.DEPLOYED),
                deleted_at__isnull=True,
            )
            .exclude(issue_id__in=list(issues))
            .exclude(commit_sha="")
            .order_by("-occurred_at")[:50]
        ):
            if _contains(adapter, binding, d.commit_sha, n.head_sha) is True:
                issues.setdefault(d.issue_id, d.issue)
    for issue in issues.values():
        delivery, created = _create_delivery(
            issue,
            f"release:{binding.id}:{n.release_tag or n.head_sha}",
            repository_binding=binding,
            stage=Delivery.Stage.RELEASED,
            commit_sha=n.head_sha,
            artifact_ref=n.release_tag,
            source=n.provider,
            trust="provider",
            occurred_at=n.occurred_at or timezone.now(),
            detail={"tag": n.release_tag, "url": n.url, "sources": [_source(n, inbound)]},
        )
        if created:
            _emit(
                binding,
                issue,
                "release.observed",
                "delivery",
                delivery.id,
                {"bindingId": str(binding.id), "tag": n.release_tag, "commitSha": n.head_sha},
                f"release:{binding.id}:{n.release_tag or n.head_sha}:{issue.id}",
                n=n,
            )
    return bool(issues)


# ---------------------------------------------------------------------------
# Read model: delivery summary (status projection input)
# ---------------------------------------------------------------------------


def _revision_binding_ids(revision):
    ids = set()
    if revision is None:
        return ids
    for entry in (revision.scope or {}).get("repositories") or []:
        if isinstance(entry, str):
            ids.add(entry)
        elif isinstance(entry, dict):
            value = entry.get("bindingId") or entry.get("binding_id") or entry.get("id")
            if value:
                ids.add(str(value))
    return ids


def relevant_bindings(issue, profile=None):
    if profile is None:
        profile = (
            PackageProfile.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
            .select_related("approved_revision")
            .first()
        )
    ids = _revision_binding_ids(profile.approved_revision if profile and profile.approved_revision_id else None)
    ids |= {
        str(x)
        for x in MergeRequestLink.objects.filter(issue_id=issue.id, deleted_at__isnull=True).values_list(
            "repository_binding_id", flat=True
        )
    }
    ids |= {
        str(x)
        for x in Delivery.objects.filter(
            issue_id=issue.id, deleted_at__isnull=True, repository_binding__isnull=False
        ).values_list("repository_binding_id", flat=True)
    }
    valid = []
    for i in ids:
        try:
            valid.append(uuid.UUID(str(i)))
        except ValueError:
            continue
    return list(
        RepositoryBinding.objects.select_related("connection")
        .filter(id__in=valid, project_id=issue.project_id, deleted_at__isnull=True)
        .order_by("path_with_namespace")
    )


def _binding_state(issue, binding):
    rows = Delivery.objects.filter(issue_id=issue.id, repository_binding=binding, deleted_at__isnull=True).order_by(
        "occurred_at", "created_at"
    )
    integrated, code_reverted, released = False, False, False
    integrated_commit = ""
    envs = {}
    for d in rows:
        if d.stage == Delivery.Stage.INTEGRATED:
            integrated, code_reverted = True, False
            integrated_commit = d.commit_sha or integrated_commit
        elif d.stage == Delivery.Stage.DEPLOYED:
            envs[d.environment] = {
                "name": d.environment,
                "state": DEPLOYED,
                "commit_sha": d.commit_sha,
                "occurred_at": d.occurred_at.isoformat(),
            }
        elif d.stage == Delivery.Stage.RELEASED:
            released = True
        elif d.stage == Delivery.Stage.ROLLED_BACK:
            released = False
            if d.environment:
                envs[d.environment] = {
                    "name": d.environment,
                    "state": ROLLED_BACK,
                    "commit_sha": d.commit_sha,
                    "occurred_at": d.occurred_at.isoformat(),
                }
            else:
                code_reverted = True
    mrs = list(
        MergeRequestLink.objects.filter(
            issue_id=issue.id, repository_binding=binding, deleted_at__isnull=True
        ).order_by("-updated_at")
    )
    if code_reverted or any(e["state"] == ROLLED_BACK for e in envs.values()):
        stage = ROLLED_BACK
    elif released:
        stage = RELEASED
    elif any(e["state"] == DEPLOYED for e in envs.values()):
        stage = DEPLOYED
    elif integrated:
        stage = INTEGRATED
    else:
        stage = NOT_INTEGRATED
    mr_state = None
    if mrs:
        states = {m.state for m in mrs}
        mr_state = "merged" if "merged" in states else ("open" if "open" in states else "closed")
    return {
        "binding_id": str(binding.id),
        "name": binding.path_with_namespace,
        "role": binding.role,
        "provider": binding.connection.provider,
        "instance_url": binding.connection.instance_url,
        "delivery": stage,
        "merge_request_state": mr_state,
        "integrated_commit_sha": integrated_commit or None,
        "environments": sorted(envs.values(), key=lambda e: e["name"]),
        "pending_merge": any(bool(m.pending_merge) and not m.pending_merge.get("confirmed_at") for m in mrs),
    }


def delivery_summary(issue) -> dict:
    """Delivery state projection for one native issue (FR-G09, FR-R05, FR-B11, AC18/19/20/23/32)."""
    from .integrations import offline_info

    profile = (
        PackageProfile.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
        .select_related("approved_revision")
        .first()
    )
    bindings = relevant_bindings(issue, profile)
    repos = [_binding_state(issue, b) for b in bindings]
    stages = [r["delivery"] for r in repos]
    if not repos:
        overall = UNKNOWN
    elif ROLLED_BACK in stages:
        overall = ROLLED_BACK
    else:
        ranks = [RANK[s] for s in stages]
        if min(ranks) == 0:
            overall = PARTIALLY_INTEGRATED if max(ranks) > 0 else NOT_INTEGRATED
        else:
            overall = min(stages, key=lambda s: RANK[s])

    flags = []
    connections = {b.connection_id: b.connection for b in bindings}
    for link in ExternalLink.objects.select_related("connection").filter(issue_id=issue.id, deleted_at__isnull=True):
        connections.setdefault(link.connection_id, link.connection)
    offline = offline_info(connections.values())
    if offline:
        flags.append("integration_offline")
    if SyncConflict.objects.filter(issue_id=issue.id, status="open", deleted_at__isnull=True).exists():
        flags.append("sync_conflict")
    if _has_stale_evidence(issue):
        flags.append("stale_evidence")
    if any(r["pending_merge"] for r in repos):
        flags.append("merge_pending_confirmation")
    state_group = getattr(getattr(issue, "state", None), "group", None)
    if state_group == "completed" and overall not in (DEPLOYED, RELEASED):
        # Native "Done" is an observed planning state, not delivery evidence (PF11).
        flags.append("native_done_without_delivery_evidence")
    last_known = [o["last_successful_sync_at"] for o in offline if o["last_successful_sync_at"]]
    return {
        "delivery": overall,
        "repositories": repos,
        "flags": flags,
        "integrations": offline,
        "last_known_at": min(last_known) if last_known else None,
        # AC32: only provider-known states; no claims about local/uncommitted work.
        "visibility": "known_provider_states_only",
        "local_state": "unknown",
    }


def _has_stale_evidence(issue) -> bool:
    for mr in MergeRequestLink.objects.filter(issue_id=issue.id, state="open", deleted_at__isnull=True).exclude(
        head_sha=""
    ):
        ev = Evidence.objects.filter(
            issue_id=issue.id, repository_binding_id=mr.repository_binding_id, deleted_at__isnull=True
        ).exclude(commit_sha="")
        if ev.exists() and not ev.filter(commit_sha=mr.head_sha).exists():
            return True
    return False


def serialize_delivery(d) -> dict:
    return {
        "id": str(d.id),
        "binding_id": str(d.repository_binding_id) if d.repository_binding_id else None,
        "stage": d.stage,
        "commit_sha": d.commit_sha,
        "artifact_ref": d.artifact_ref,
        "environment": d.environment,
        "source": d.source,
        "trust": d.trust,
        "occurred_at": d.occurred_at.isoformat(),
        "reverts": str(d.reverts_id) if d.reverts_id else None,
        "sources": (d.detail or {}).get("sources", []),
    }


def delivery_view(issue) -> dict:
    summary = delivery_summary(issue)
    summary["history"] = [
        serialize_delivery(d)
        for d in Delivery.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by(
            "occurred_at", "created_at"
        )
    ]
    return summary


# ---------------------------------------------------------------------------
# Review view (J07, FR-R01, FR-R02)
# ---------------------------------------------------------------------------

ALL_TRUST = {"local_self_report", "runner_reported", "provider_ci", "human"}


def required_trust(verification):
    v = (verification or "").strip().lower()
    if v.startswith("ci") or v in ("trusted_ci", "provider_ci", "test", "automated"):
        return "trusted_ci", {"provider_ci"}
    if v in ("manual", "human", "review"):
        return "human", {"human", "provider_ci"}
    if v == "runner":
        return "runner", {"provider_ci", "runner_reported"}
    if v in ("local", "any", "self_report"):
        return "any", set(ALL_TRUST)
    # Conservative default: unknown verification requires trusted CI.
    return "trusted_ci", {"provider_ci"}


def _criterion_matches(evidence, criterion_id, verification):
    if criterion_id and criterion_id in (evidence.criterion_ids or []):
        return True
    v = (verification or "").strip().lower()
    if v.startswith("ci:"):
        return evidence.kind in CI_KINDS and evidence.name.lower() == v[3:]
    if v in ("ci", "trusted_ci", "provider_ci", "test", "automated"):
        return evidence.kind in CI_KINDS
    return False


def serialize_evidence(e) -> dict:
    return {
        "id": str(e.id),
        "kind": e.kind,
        "name": e.name,
        "source": e.source,
        "trust": e.trust,
        "result": e.result,
        "binding_id": str(e.repository_binding_id) if e.repository_binding_id else None,
        "commit_sha": e.commit_sha,
        "artifact_ref": e.artifact_ref,
        "criterion_ids": e.criterion_ids,
        "occurred_at": e.occurred_at.isoformat(),
        "url": e.url,
    }


def serialize_mr(m) -> dict:
    return {
        "id": str(m.id),
        "binding_id": str(m.repository_binding_id),
        "repository": m.repository_binding.path_with_namespace,
        "external_id": m.external_id,
        "title": m.title,
        "url": m.url,
        "source_branch": m.source_branch,
        "target_branch": m.target_branch,
        "head_sha": m.head_sha,
        "target_sha": m.target_sha,
        "state": m.state,
        "merged_commit_sha": m.merged_commit_sha,
        "merge_method": m.merge_method,
        "pending_merge": m.pending_merge or None,
        "commits": [{"sha": c.get("sha"), "message": c.get("message"), "status": "claimed"} for c in (m.commits or [])],
        "last_event_at": m.last_event_at.isoformat() if m.last_event_at else None,
    }


def approval_validity(approval, approved_revision, mr_by_id):
    if approval.decision != "approved":
        return "changes_requested"
    if approval.invalidated_at is not None:
        return "invalidated"
    if approved_revision is None or approval.revision_id != approved_revision.id:
        return "stale_revision"
    if approval.kind == ReviewApproval.Kind.CODE:
        mr = mr_by_id.get(approval.merge_request_id)
        if mr is None or mr.head_sha != approval.head_sha:
            return "stale_head"
    return "valid"


def serialize_approval(a, validity) -> dict:
    return {
        "id": str(a.id),
        "kind": a.kind,
        "decision": a.decision,
        "merge_request_id": str(a.merge_request_id) if a.merge_request_id else None,
        "head_sha": a.head_sha,
        "target_sha": a.target_sha,
        "revision_id": str(a.revision_id),
        "policy_version": a.policy_version,
        "approved_by": str(a.approved_by_id),
        "created_at": a.created_at.isoformat(),
        "valid": validity == "valid",
        "validity": validity,
        "invalidated_at": a.invalidated_at.isoformat() if a.invalidated_at else None,
        "invalidated_reason": a.invalidated_reason,
    }


def revision_is_stale(profile) -> bool:
    """INV-05: the approved revision no longer matches the current revision content."""
    if profile is None or profile.approved_revision_id is None:
        return True
    approved = profile.approved_revision
    latest = PackageRevision.objects.filter(issue_id=profile.issue_id).order_by("-number").first()
    if latest is not None and latest.content_hash != approved.content_hash:
        return True
    if profile.working_revision_id and profile.working_revision.content_hash != approved.content_hash:
        return True
    return False


def review_view(issue) -> dict:
    from ..models import Decision

    profile = (
        PackageProfile.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
        .select_related("approved_revision", "working_revision")
        .first()
    )
    revision = profile.approved_revision if profile and profile.approved_revision_id else None
    mrs = list(
        MergeRequestLink.objects.select_related("repository_binding")
        .filter(issue_id=issue.id, deleted_at__isnull=True)
        .order_by("created_at")
    )
    mr_by_id = {m.id: m for m in mrs}
    relevant_commits = {m.head_sha for m in mrs if m.head_sha} | {
        m.merged_commit_sha for m in mrs if m.merged_commit_sha
    }
    evidence = list(Evidence.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("-occurred_at"))

    criteria_out, open_points = [], []
    for idx, raw in enumerate((revision.criteria if revision else []) or []):
        crit = raw if isinstance(raw, dict) else {"statement": str(raw)}
        cid = str(crit.get("id") or f"c{idx + 1}")
        verification = crit.get("verification") or ""
        required = crit.get("required", True)
        trust_label, accepted = required_trust(verification)
        matched = [
            e
            for e in evidence
            if _criterion_matches(e, cid, verification)
            and (not e.commit_sha or not relevant_commits or e.commit_sha in relevant_commits)
        ]
        latest = {}
        for e in matched:  # newest first
            if e.trust in accepted:
                latest.setdefault((e.name, e.repository_binding_id), e)
        results = [e.result for e in latest.values()]
        if Evidence.Result.FAILED in results:
            state, reason = "failed", "latest trusted evidence failed"
        elif results and all(r == Evidence.Result.PASSED for r in results):
            state, reason = "proven", ""
        else:
            state = "not_proven"
            if any(e.trust not in accepted for e in matched):
                reason = f"only evidence below required trust ({trust_label}) is present"
            elif matched:
                reason = "evidence not run or result unknown"
            else:
                reason = "no evidence"
        criteria_out.append(
            {
                "id": cid,
                "statement": crit.get("statement") or crit.get("text") or "",
                "verification": verification,
                "required": required,
                "required_trust": trust_label,
                "state": state,
                "reason": reason,
                "evidence": [dict(serialize_evidence(e), accepted=e.trust in accepted) for e in matched],
            }
        )
        if required and state != "proven":
            open_points.append({"kind": "criterion_not_proven", "criterion_id": cid, "state": state, "reason": reason})

    approvals = list(ReviewApproval.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("-created_at"))
    approvals_out = []
    for a in approvals:
        approvals_out.append(serialize_approval(a, approval_validity(a, revision, mr_by_id)))
    for m in mrs:
        if m.state != "open":
            continue
        has_valid = any(
            a["kind"] == "code" and a["valid"] and a["merge_request_id"] == str(m.id) for a in approvals_out
        )
        if not has_valid:
            open_points.append(
                {
                    "kind": "code_review_required",
                    "merge_request_id": str(m.id),
                    "head_sha": m.head_sha,
                    "invalidated": any(
                        a["merge_request_id"] == str(m.id) and a["validity"] in ("invalidated", "stale_head")
                        for a in approvals_out
                    ),
                }
            )
    if revision is not None and not any(a["kind"] == "outcome" and a["valid"] for a in approvals_out):
        open_points.append({"kind": "outcome_acceptance_missing"})
    if revision is None:
        open_points.append({"kind": "no_approved_revision"})
    elif revision_is_stale(profile):
        open_points.append({"kind": "revision_changed_since_approval"})
    for q in Decision.objects.filter(issue_id=issue.id, kind="open_question", deleted_at__isnull=True).exclude(
        status__in=("withdrawn", "superseded")
    ):
        open_points.append({"kind": "open_question", "id": str(q.id), "title": q.title})

    claims = [
        {"sha": c.get("sha"), "message": c.get("message"), "status": "claimed", "merge_request_id": str(m.id)}
        for m in mrs
        for c in (m.commits or [])
    ]
    return {
        "work_item_id": str(issue.id),
        "revision": (
            {
                "id": str(revision.id),
                "number": revision.number,
                "title": revision.title,
                "intent": revision.intent,
                "outcome": revision.outcome,
                "content_hash": revision.content_hash,
            }
            if revision
            else None
        ),
        "change_summary": {
            "merge_requests": len(mrs),
            "commits": sum(len(m.commits or []) for m in mrs),
            "links": [m.url for m in mrs if m.url],
            "note": "Technical diff review stays in the Git provider; linked above.",
        },
        "criteria": criteria_out,
        "merge_requests": [serialize_mr(m) for m in mrs],
        "approvals": approvals_out,
        "claims": claims,
        "claims_note": "Commit messages are claims, not requirement or test proof.",
        "open_points": open_points,
        "delivery": delivery_summary(issue),
    }
