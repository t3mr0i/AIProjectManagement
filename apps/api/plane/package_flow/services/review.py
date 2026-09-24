# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Human review approvals and the merge gate (FR-R03, FR-R04, FR-G10, INV-03, INV-05).

* Approvals are human-only (``HUMAN_PRINCIPAL_REQUIRED`` for agents).
* Code approvals need ``review.approve_code`` and bind to the MR's exact head
  and target sha, the approved revision and the review policy version.
* Outcome acceptance needs ``review.accept_outcome`` and never grants merge.
* Merge needs ``merge.request`` + a human + a valid code approval for exactly
  the MR's current head. The provider head is fetched *before* merging; a
  different head → ``409 HEAD_MISMATCH`` and no merge (AC17). The adapter must
  declare ``request_merge`` and ``verify_human_approval`` as supported and the
  target branch must be protected, otherwise ``409 CAPABILITY_MISSING``
  (read-only path, FR-G10). The merge is ``pending`` until a provider event
  confirms it (202).
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..adapters import get_adapter
from ..adapters.base import RepoRef, TransportError
from ..capabilities import require_capability, require_extension_enabled
from ..errors import Conflict, DomainError, HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import Capability, IntegrationConnection, MergeRequestLink, PackageProfile, ReviewApproval
from . import events
from .delivery import invalidate_code_approvals, revision_is_stale
from .integrations import declaration_for, provider_context


def review_policy_version() -> str:
    return str(getattr(settings, "PACKAGE_FLOW_REVIEW_POLICY_VERSION", "review-policy-1"))


class ProviderUnavailable(DomainError):
    status_code = 502
    code = "PROVIDER_UNAVAILABLE"


def _profile_and_revision(issue):
    profile = (
        PackageProfile.objects.select_related("approved_revision", "working_revision")
        .filter(issue_id=issue.id, deleted_at__isnull=True)
        .first()
    )
    if profile is None:
        raise Conflict("Work item has no package profile", code="NO_PACKAGE")
    if profile.approved_revision_id is None:
        raise Conflict("No approved revision to review against", code="NO_APPROVED_REVISION")
    if revision_is_stale(profile):
        raise Conflict(
            "Package content changed since the approved revision; re-approval required",
            code="REVISION_STALE",
            detail={"approved_revision_id": str(profile.approved_revision_id)},
        )
    return profile, profile.approved_revision


def create_review_approval(principal, issue, data) -> ReviewApproval:
    if not principal.is_human:
        raise HumanPrincipalRequired("Review approvals require an interactive human principal")
    kind = data.get("kind")
    decision = data.get("decision") or "approved"
    if kind not in (ReviewApproval.Kind.CODE, ReviewApproval.Kind.OUTCOME):
        raise ValidationFailed("kind must be 'code' or 'outcome'")
    if decision not in ("approved", "changes_requested"):
        raise ValidationFailed("decision must be 'approved' or 'changes_requested'")
    user = principal.user
    capability = (
        Capability.REVIEW_APPROVE_CODE if kind == ReviewApproval.Kind.CODE else Capability.REVIEW_ACCEPT_OUTCOME
    )
    require_capability(user, issue.workspace_id, issue.project_id, capability)
    require_extension_enabled(issue.workspace_id, issue.project_id)
    _profile, revision = _profile_and_revision(issue)
    link = None
    head_sha = target_sha = ""
    if kind == ReviewApproval.Kind.CODE:
        link = (
            MergeRequestLink.objects.filter(
                id=data.get("merge_request_id"), issue_id=issue.id, deleted_at__isnull=True
            ).first()
            if data.get("merge_request_id")
            else None
        )
        if link is None:
            raise NotFound("Merge request not found")
        if link.state != "open":
            raise Conflict("Merge request is not open", code="MR_NOT_OPEN")
        head_sha = (data.get("head_sha") or "").strip()
        if not head_sha or head_sha != link.head_sha:
            raise Conflict(
                "Reviewed head is not the merge request's current head",
                code="HEAD_MISMATCH",
                detail={"current_head_sha": link.head_sha, "reviewed_head_sha": head_sha},
            )
        target_sha = link.target_sha
    with transaction.atomic():
        approval = ReviewApproval.objects.create(
            issue=issue,
            kind=kind,
            revision=revision,
            merge_request=link,
            head_sha=head_sha,
            target_sha=target_sha,
            policy_version=review_policy_version(),
            approved_by=user,
            decision=decision,
            comment=data.get("comment") or "",
            created_by=user,
        )
        if decision == "approved":
            events.emit(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.id,
                event_type="review.approved",
                aggregate_type="review",
                aggregate_id=approval.id,
                actor_kind="human",
                actor_id=user.id,
                payload={
                    "kind": kind,
                    "revisionId": str(revision.id),
                    "mergeRequestId": str(link.id) if link else None,
                    "headSha": head_sha,
                    "policyVersion": approval.policy_version,
                },
                summary=f"{kind} review approved",
            )
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            action=f"review.{kind}.{decision}",
            target_type="review_approval",
            target_id=approval.id,
            actor=user,
            detail={"head_sha": head_sha, "revision_id": str(revision.id)},
        )
    return approval


def request_merge(principal, link, expected_head_sha, *, squash=None):
    """Merge gate. Returns ``(http_status, body)``; raises DomainError on refusal."""
    if not principal.is_human:
        raise HumanPrincipalRequired("Merge requires an interactive human principal")
    user = principal.user
    issue = link.issue
    require_capability(user, issue.workspace_id, issue.project_id, Capability.MERGE_REQUEST)
    require_extension_enabled(issue.workspace_id, issue.project_id)
    if link.state != "open":
        raise Conflict("Merge request is not open", code="MR_NOT_OPEN", detail={"state": link.state})
    if link.pending_merge and not link.pending_merge.get("confirmed_at"):
        if link.pending_merge.get("head_sha") == expected_head_sha:
            return 202, {"status": "pending_confirmation", "merge_request_id": str(link.id), **link.pending_merge}
        raise Conflict("A merge is already pending confirmation", code="MERGE_PENDING")
    if not expected_head_sha or expected_head_sha != link.head_sha:
        raise Conflict(
            "Expected head does not match the known head",
            code="HEAD_MISMATCH",
            detail={"known_head_sha": link.head_sha, "expected_head_sha": expected_head_sha},
        )
    binding = link.repository_binding
    connection = binding.connection
    if connection.deleted_at is not None or connection.status != IntegrationConnection.Status.ACTIVE:
        raise Conflict(
            "Integration is not active; merge path is read-only",
            code="CAPABILITY_MISSING",
            detail={"reason": "integration_" + connection.status, "read_only": True},
        )
    adapter = get_adapter(connection.provider)
    decl = declaration_for(connection, adapter)
    missing = [c for c in ("request_merge", "verify_human_approval") if not decl.is_supported(c)]
    if missing:
        raise Conflict(
            "Provider cannot enforce a human-approved merge; path is read-only",
            code="CAPABILITY_MISSING",
            detail={"missing": missing, "levels": {c: decl.level(c) for c in missing}, "read_only": True},
        )
    _profile, revision = _profile_and_revision(issue)
    approval = (
        ReviewApproval.objects.filter(
            merge_request=link,
            kind=ReviewApproval.Kind.CODE,
            decision="approved",
            invalidated_at__isnull=True,
            deleted_at__isnull=True,
            head_sha=link.head_sha,
            revision=revision,
            policy_version=review_policy_version(),
        )
        .order_by("-created_at")
        .first()
    )
    if approval is None:
        raise Conflict(
            "A valid human code approval for the current head is required",
            code="REVIEW_REQUIRED",
            detail={"head_sha": link.head_sha},
        )
    ctx = provider_context(connection)
    repo = RepoRef(binding.external_id, binding.path_with_namespace)
    try:
        remote = adapter.fetch_merge_request(ctx, repo, link.external_id)
    except TransportError:
        raise ProviderUnavailable("Provider unreachable; cannot verify head before merge") from None
    if not remote.get("ok"):
        raise ProviderUnavailable("Provider did not return the merge request", detail={"status": remote.get("status")})
    if remote.get("state") != "open":
        raise Conflict(
            "Provider reports the merge request is not open", code="MR_NOT_OPEN", detail={"state": remote.get("state")}
        )
    provider_head = remote.get("head_sha") or ""
    if provider_head != approval.head_sha:
        with transaction.atomic():
            MergeRequestLink.objects.filter(pk=link.pk).update(head_sha=provider_head, updated_at=timezone.now())
            link.head_sha = provider_head
            invalidate_code_approvals(link, provider_head, "provider head changed before merge")
        raise Conflict(
            "Provider head changed since review; no merge was performed",
            code="HEAD_MISMATCH",
            detail={"approved_head_sha": approval.head_sha, "provider_head_sha": provider_head},
        )
    if approval.target_sha and remote.get("target_sha") and remote["target_sha"] != approval.target_sha:
        raise Conflict(
            "Target branch base changed since review; re-review required",
            code="HEAD_MISMATCH",
            detail={
                "reason": "target_changed",
                "approved_target_sha": approval.target_sha,
                "provider_target_sha": remote["target_sha"],
            },
        )
    try:
        protection = adapter.fetch_branch_protection(ctx, repo, link.target_branch or binding.default_branch)
    except TransportError:
        raise ProviderUnavailable("Provider unreachable; cannot verify branch protection") from None
    if protection.get("protected") is not True:
        raise Conflict(
            "Target branch is not protected at the provider; platform approval alone is not enforceable",
            code="CAPABILITY_MISSING",
            detail={"reason": "target_branch_unprotected", "protection": protection, "read_only": True},
        )
    try:
        result = adapter.merge(ctx, repo, link.external_id, sha=approval.head_sha, squash=squash)
    except TransportError:
        raise ProviderUnavailable("Provider unreachable during merge; state unknown until reconciliation") from None
    if result.get("head_mismatch"):
        raise Conflict(
            "Provider rejected merge: head moved",
            code="HEAD_MISMATCH",
            detail={"provider_status": result.get("status")},
        )
    if not result.get("accepted"):
        raise Conflict(
            "Provider rejected the merge", code="MERGE_REJECTED", detail={"provider_status": result.get("status")}
        )
    pending = {
        "requested_at": timezone.now().isoformat(),
        "requested_by": str(user.id),
        "approval_id": str(approval.id),
        "head_sha": approval.head_sha,
        "provider_status": result.get("status"),
        "reported_merged_commit_sha": result.get("merged_commit_sha") or "",
    }
    with transaction.atomic():
        MergeRequestLink.objects.filter(pk=link.pk).update(pending_merge=pending, updated_at=timezone.now())
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            action="merge.requested",
            target_type="merge_request_link",
            target_id=link.id,
            actor=user,
            detail={
                "head_sha": approval.head_sha,
                "approval_id": str(approval.id),
                "provider_status": result.get("status"),
            },
        )
    return 202, {"status": "pending_confirmation", "merge_request_id": str(link.id), **pending}
