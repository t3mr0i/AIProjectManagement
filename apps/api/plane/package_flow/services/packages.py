# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Package profile, revisions, readiness, execution approvals and status projection.

Requirement refs: FR-W01, FR-W02, FR-W04, FR-W05, FR-W06, FR-W09, FR-W10,
FR-B02, FR-B05, FR-B06, FR-B07, FR-B11, INV-01, INV-03, INV-04.

All functions take native Plane rows that were already scope-checked by the
view layer (workspace -> project -> issue). ``principal`` is a
:class:`plane.package_flow.principal.Principal`.
"""

import hashlib
import json
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from plane.db.models import Issue, IssueAssignee

from ..errors import Conflict, HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import (
    ChangeRecord,
    ExecutionApproval,
    PackageProfile,
    PackageRevision,
    RepositoryBinding,
    ReviewApproval,
    RunnerProfile,
)
from . import events

POLICY_VERSION = "pf-policy-1"
CONTRACT_VERSION = "1.1.0"

# Allowed runner actions (execution-authorization 1.1.0). "merge" is deliberately absent:
# merges only happen through the human-gated merge endpoint (INV-05, AC27).
ALLOWED_ACTIONS = (
    "prepare_worktree",
    "edit_allowed_files",
    "run_allowed_checks",
    "create_commit",
    "push_work_branch",
    "open_merge_request",
)
SECURITY_TOUCHES = {"permissions", "permission", "auth", "authentication", "authorization", "security"}
DEFAULT_APPROVAL_HOURS = 72
MAX_APPROVAL_HOURS = 24 * 30
DEFAULT_LIMITS = {"max_seconds": 3600, "max_spend_minor": 0, "currency": "EUR"}
ACTIVE_RUN_STATUSES = ("queued", "claimed", "running", "waiting")
COMMIT_RE = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
CHECK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
MAX_CHECKS = 20
MAX_CHECK_ARGS = 64
MAX_CHECK_ARG_LEN = 1000

PHASES = ("drafts", "ready", "build", "review", "ship", "done")


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------
def canonical_json(value) -> str:
    """Documented canonical form: sorted keys, no whitespace, UTF-8, ``str`` for non-JSON types."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_description(issue) -> str:
    return (issue.description_html or "").strip()


def native_description_hash(issue) -> str:
    return sha256_hex(_normalized_description(issue))


def native_source_hash(issue) -> str:
    """Hash of the native fields that carry intent: title + description (FR-B06)."""
    return sha256_hex(canonical_json({"title": issue.name or "", "description_sha256": native_description_hash(issue)}))


def current_native_source_hash(issue_id) -> str:
    """Recompute from the database, never from a projected event (PF06)."""
    issue = Issue.all_objects.only("id", "name", "description_html").get(id=issue_id)
    return native_source_hash(issue)


def revision_content(source) -> dict:
    """Canonical content dict of a profile working draft or a revision."""
    return {
        "intent": source.intent or "",
        "outcome": source.outcome or "",
        "non_goals": list(source.non_goals or []),
        "scope": dict(source.scope or {}),
        "criteria": list(source.criteria or []),
        "decisions": list(getattr(source, "decisions", None) or []),
        "artifacts": list(getattr(source, "artifacts", None) or []),
        "profile_kind": source.profile_kind,
        "package_type": source.package_type,
    }


def content_hash(content: dict, title: str, description_sha256: str) -> str:
    return sha256_hex(
        canonical_json({"content": content, "title": title or "", "native_description_sha256": description_sha256})
    )


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------
def get_profile(issue):
    return PackageProfile.objects.filter(issue_id=issue.id, deleted_at__isnull=True).first()


def require_profile(issue):
    profile = get_profile(issue)
    if profile is None:
        raise NotFound("Work item has no package profile", code="NO_PROFILE")
    return profile


def _default_completion(package_type):
    if package_type == PackageProfile.PackageType.CODE:
        return PackageProfile.CompletionCriterion.DELIVERY_AND_ACCEPTANCE
    return PackageProfile.CompletionCriterion.ACCEPTED_DELIVERABLE


def _choice(value, choices, field):
    if value not in {c for c, _ in choices}:
        raise ValidationFailed(
            f"Invalid value for {field}", detail={"field": field, "allowed": [c for c, _ in choices]}
        )
    return value


def activate_profile(issue, principal, profile_kind=None, package_type=None):
    """Explicit, idempotent 0..1 activation on an existing issue (FR-B02, PF02). Returns (profile, created)."""
    existing = get_profile(issue)
    if existing is not None:
        return existing, False
    profile_kind = _choice(profile_kind or "light", PackageProfile.ProfileKind.choices, "profile_kind")
    package_type = _choice(package_type or "code", PackageProfile.PackageType.choices, "package_type")
    try:
        with transaction.atomic():
            profile = PackageProfile.objects.create(
                issue=issue,
                profile_kind=profile_kind,
                package_type=package_type,
                completion_criterion=_default_completion(package_type),
                activated_by=principal.user,
            )
            events.emit(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.id,
                event_type="package.profile.activated",
                aggregate_type="package",
                aggregate_id=issue.id,
                actor_kind=principal.kind,
                actor_id=principal.id,
                deduplication_key=f"package.profile.activated:{issue.id}",
                payload={"workItemId": str(issue.id), "profileKind": profile_kind, "packageType": package_type},
            )
    except IntegrityError:
        return PackageProfile.objects.get(issue_id=issue.id), False
    return profile, True


def _clean_str_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationFailed(f"{field} must be a list of strings", detail={"field": field})
    return [v.strip() for v in value if v.strip()]


def _clean_criteria(value, previous):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationFailed("criteria must be a list", detail={"field": "criteria"})
    used = {c.get("id") for c in previous or [] if isinstance(c, dict)}
    numbers = [int(i[2:]) for i in used if isinstance(i, str) and i.startswith("C-") and i[2:].isdigit()]
    next_no = max(numbers, default=0) + 1
    result, seen = [], set()
    for item in value:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            raise ValidationFailed("criterion must be an object", detail={"field": "criteria"})
        text = str(item.get("text") or item.get("statement") or "").strip()
        cid = item.get("id")
        if not cid:
            cid = f"C-{next_no}"
            next_no += 1
        cid = str(cid)
        if cid in seen:
            raise ValidationFailed("duplicate criterion id", detail={"field": "criteria", "id": cid})
        seen.add(cid)
        criterion = {"id": cid, "text": text}
        if item.get("verification"):
            criterion["verification"] = str(item["verification"])
        criterion["required"] = bool(item.get("required", True))
        result.append(criterion)
    return result


def _clean_dict(value, field):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationFailed(f"{field} must be an object", detail={"field": field})
    return value


PROFILE_FIELDS = (
    "intent",
    "outcome",
    "non_goals",
    "scope",
    "criteria",
    "risk",
    "profile_kind",
    "package_type",
    "completion_criterion",
)


def update_profile(profile, data, principal):
    """Edit the working draft with optimistic concurrency (``expected_version``)."""
    with transaction.atomic():
        locked = PackageProfile.objects.select_for_update().get(pk=profile.pk)
        expected = data.get("expected_version")
        if expected is not None and int(expected) != locked.version:
            raise Conflict(
                "Profile was changed concurrently",
                code="VERSION_CONFLICT",
                detail={"expected_version": expected, "current_version": locked.version},
            )
        changed = []
        for field in PROFILE_FIELDS:
            if field not in data:
                continue
            value = data[field]
            if field in ("intent", "outcome"):
                value = str(value or "")
            elif field == "non_goals":
                value = _clean_str_list(value, field)
            elif field == "criteria":
                value = _clean_criteria(value, locked.criteria)
            elif field in ("scope", "risk"):
                value = _clean_dict(value, field)
            elif field == "profile_kind":
                value = _choice(value, PackageProfile.ProfileKind.choices, field)
            elif field == "package_type":
                value = _choice(value, PackageProfile.PackageType.choices, field)
                if "completion_criterion" not in data:
                    locked.completion_criterion = _default_completion(value)
                    changed.append("completion_criterion")
            elif field == "completion_criterion":
                value = _choice(value, PackageProfile.CompletionCriterion.choices, field)
            setattr(locked, field, value)
            changed.append(field)
        if changed:
            locked.version += 1
            locked.updated_by = principal.user
            locked.save()
    return locked


# ---------------------------------------------------------------------------
# readiness (FR-W02, FR-W05)
# ---------------------------------------------------------------------------
def _scope_in(scope):
    scope = scope or {}
    return scope.get("in_scope") or scope.get("in") or []


def readiness_of(content: dict, title: str = "x") -> dict:
    missing = []

    def need(ok, field, message):
        if not ok:
            missing.append({"field": field, "message": message})

    need(bool((title or "").strip()), "title", "Title is required")
    need(bool(content["intent"].strip()), "intent", "Describe the goal / why")
    need(bool(content["outcome"].strip()), "outcome", "Describe the desired outcome")
    criteria = [c for c in content["criteria"] if isinstance(c, dict) and str(c.get("text", "")).strip()]
    need(bool(criteria), "criteria", "Add at least one concrete acceptance criterion")
    need(bool(_scope_in(content["scope"])), "scope", "Limit the scope (at least one in-scope item)")
    if content["profile_kind"] == PackageProfile.ProfileKind.DEEP:
        risk = content.get("risk") or {}
        need(bool(str(risk.get("notes", "")).strip()), "risk.notes", "Deep profile requires risk notes")
        need(bool(content["non_goals"]), "non_goals", "Deep profile requires explicit non-goals")
    policies = []
    touches = {str(t).lower() for t in (content["scope"] or {}).get("touches", []) or []}
    if touches & SECURITY_TOUCHES:
        policies.append(
            {
                "id": "security_review",
                "message": "Permission/auth/security change: project security review required before merge",
            }
        )
    return {
        "ready": not missing,
        "missing": missing,
        "policies": policies,
        "profile_kind": content["profile_kind"],
    }


def profile_readiness(profile, issue) -> dict:
    content = revision_content(profile)
    content["risk"] = profile.risk or {}
    return readiness_of(content, issue.name)


def revision_readiness(revision) -> dict:
    content = revision_content(revision)
    content["risk"] = (revision.source_versions or {}).get("risk", {})
    return readiness_of(content, revision.title)


# ---------------------------------------------------------------------------
# revisions (FR-W04)
# ---------------------------------------------------------------------------
def latest_revision(issue):
    return PackageRevision.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("-number").first()


def create_revision(issue, profile, principal, *, decisions=None, artifacts=None, expected_revision_id=None):
    """Immutable snapshot of the working draft + native title/description. Returns (revision, created)."""
    if decisions is not None and not isinstance(decisions, list):
        raise ValidationFailed("decisions must be a list", detail={"field": "decisions"})
    if artifacts is not None and not isinstance(artifacts, list):
        raise ValidationFailed("artifacts must be a list", detail={"field": "artifacts"})
    with transaction.atomic():
        locked = PackageProfile.objects.select_for_update().get(pk=profile.pk)
        fresh_issue = Issue.all_objects.get(pk=issue.pk)
        if expected_revision_id is not None and str(locked.working_revision_id or "") != str(
            expected_revision_id or ""
        ):
            raise Conflict(
                "Working revision changed concurrently",
                code="VERSION_CONFLICT",
                detail={"expected_revision_id": expected_revision_id, "current": str(locked.working_revision_id or "")},
            )
        latest = latest_revision(fresh_issue)
        content = revision_content(locked)
        if decisions is None:
            content["decisions"] = list(latest.decisions) if latest else []
        else:
            content["decisions"] = decisions
        if artifacts is None:
            content["artifacts"] = list(latest.artifacts) if latest else []
        else:
            content["artifacts"] = artifacts
        desc_hash = native_description_hash(fresh_issue)
        chash = content_hash(content, fresh_issue.name, desc_hash)
        if latest is not None and latest.content_hash == chash:
            return latest, False
        number = (latest.number if latest else 0) + 1
        revision = PackageRevision.objects.create(
            issue=fresh_issue,
            number=number,
            title=fresh_issue.name,
            intent=content["intent"],
            outcome=content["outcome"],
            non_goals=content["non_goals"],
            scope=content["scope"],
            criteria=content["criteria"],
            decisions=content["decisions"],
            artifacts=content["artifacts"],
            profile_kind=content["profile_kind"],
            package_type=content["package_type"],
            content_hash=chash,
            based_on=latest,
            created_by=principal.user,
            source_versions={
                "native": {
                    "issue_id": str(fresh_issue.id),
                    "title": fresh_issue.name,
                    "description_sha256": desc_hash,
                    "native_source_hash": native_source_hash(fresh_issue),
                    "issue_updated_at": fresh_issue.updated_at.isoformat() if fresh_issue.updated_at else None,
                },
                "profile_version": locked.version,
                "risk": locked.risk or {},
            },
        )
        locked.working_revision = revision
        locked.save(update_fields=["working_revision", "updated_at"])
        events.emit(
            workspace_id=fresh_issue.workspace_id,
            project_id=fresh_issue.project_id,
            issue_id=fresh_issue.id,
            event_type="package.revision.created",
            aggregate_type="package",
            aggregate_id=fresh_issue.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            deduplication_key=f"package.revision.created:{revision.id}",
            payload={"revisionId": str(revision.id), "number": number, "contentHash": chash},
            summary=f"Revision {number} created",
        )
    return revision, True


def revision_is_stale(revision, current_hash=None) -> bool:
    current_hash = current_hash or current_native_source_hash(revision.issue_id)
    return (revision.source_versions or {}).get("native", {}).get("native_source_hash") != current_hash


COMPARE_FIELDS = (
    "title",
    "intent",
    "outcome",
    "non_goals",
    "scope",
    "criteria",
    "decisions",
    "artifacts",
    "profile_kind",
    "package_type",
)


def compare_revisions(rev_from, rev_to) -> dict:
    changes = []
    for field in COMPARE_FIELDS:
        a, b = getattr(rev_from, field), getattr(rev_to, field)
        if canonical_json(a) != canonical_json(b):
            changes.append({"field": field, "from": a, "to": b})
    crit_a = {c.get("id"): c for c in rev_from.criteria or [] if isinstance(c, dict)}
    crit_b = {c.get("id"): c for c in rev_to.criteria or [] if isinstance(c, dict)}
    criteria = {
        "added": [crit_b[k] for k in crit_b if k not in crit_a],
        "removed": [crit_a[k] for k in crit_a if k not in crit_b],
        "changed": [
            {"id": k, "from": crit_a[k], "to": crit_b[k]}
            for k in crit_a
            if k in crit_b and canonical_json(crit_a[k]) != canonical_json(crit_b[k])
        ],
    }
    return {
        "from": {"id": str(rev_from.id), "number": rev_from.number, "content_hash": rev_from.content_hash},
        "to": {"id": str(rev_to.id), "number": rev_to.number, "content_hash": rev_to.content_hash},
        "changes": changes,
        "criteria": criteria,
    }


# ---------------------------------------------------------------------------
# approvals (FR-W05, INV-01, INV-03)
# ---------------------------------------------------------------------------
def approval_state(approval, now=None) -> str:
    now = now or timezone.now()
    if approval.revoked_at is not None:
        return "revoked"
    if approval.expires_at <= now:
        return "expired"
    return "valid"


def valid_approval_for(issue, profile=None):
    """The currently valid approval for the profile's approved revision, if any."""
    profile = profile or get_profile(issue)
    if profile is None or profile.approved_revision_id is None:
        return None
    return (
        ExecutionApproval.objects.filter(
            issue_id=issue.id,
            revision_id=profile.approved_revision_id,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            deleted_at__isnull=True,
        )
        .order_by("-approved_at")
        .first()
    )


def _validate_repository_scope(scope, project):
    if scope is None:
        return []
    if not isinstance(scope, list):
        raise ValidationFailed("repository_scope must be a list", detail={"field": "repository_scope"})
    cleaned = []
    for entry in scope:
        if not isinstance(entry, dict):
            raise ValidationFailed("repository_scope entry must be an object", detail={"field": "repository_scope"})
        binding_id = entry.get("binding_id")
        base_commit = str(entry.get("base_commit") or "").lower()
        target_branch = str(entry.get("target_branch") or "").strip()
        paths = entry.get("allowed_paths") or []
        # Bindings from another project/workspace cannot be injected by reference (FR-B02).
        binding = (
            RepositoryBinding.objects.filter(
                id=binding_id, project_id=project.id, deleted_at__isnull=True, is_active=True
            ).first()
            if binding_id and _is_uuid(binding_id)
            else None
        )
        if binding is None:
            raise ValidationFailed(
                "Unknown repository binding", code="BINDING_NOT_FOUND", detail={"binding_id": binding_id}
            )
        if not COMMIT_RE.match(base_commit):
            raise ValidationFailed("base_commit must be a full commit sha", detail={"field": "base_commit"})
        if not target_branch:
            raise ValidationFailed("target_branch is required", detail={"field": "target_branch"})
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p.strip() for p in paths):
            raise ValidationFailed("allowed_paths must be a non-empty list", detail={"field": "allowed_paths"})
        for p in paths:
            if p.startswith("/") or ".." in p.split("/"):
                raise ValidationFailed("allowed_paths must be relative", detail={"field": "allowed_paths", "path": p})
        cleaned.append(
            {
                "binding_id": str(binding.id),
                "base_commit": base_commit,
                "target_branch": target_branch,
                "allowed_paths": [p.strip() for p in paths],
            }
        )
    return cleaned


def _is_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _validate_limits(limits):
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    try:
        max_seconds = int(limits["max_seconds"])
        max_spend = int(limits["max_spend_minor"])
    except (TypeError, ValueError):
        raise ValidationFailed("limits must be integers", detail={"field": "limits"})
    currency = str(limits.get("currency") or "")
    if max_seconds < 1 or max_spend < 0 or not CURRENCY_RE.match(currency):
        raise ValidationFailed("invalid limits", detail={"field": "limits"})
    return {"max_seconds": max_seconds, "max_spend_minor": max_spend, "currency": currency}


def _validate_checks(checks):
    """Human-defined checks for ``run_allowed_checks``: ``[{name, command: [argv], trusted?}]``.

    The command is an argv list (no shell string); it is executed by the external runner only,
    never by the Plane server. Names are slugs and unique.
    """
    if checks is None:
        return []
    if not isinstance(checks, list):
        raise ValidationFailed("checks must be a list", detail={"field": "checks"})
    if len(checks) > MAX_CHECKS:
        raise ValidationFailed("too many checks", detail={"field": "checks", "max": MAX_CHECKS})
    cleaned, names = [], set()
    for entry in checks:
        if not isinstance(entry, dict):
            raise ValidationFailed("check must be an object", detail={"field": "checks"})
        name = entry.get("name")
        command = entry.get("command")
        if not isinstance(name, str) or not CHECK_NAME_RE.match(name):
            raise ValidationFailed("check name must be a slug", detail={"field": "checks", "name": name})
        if name in names:
            raise ValidationFailed("duplicate check name", detail={"field": "checks", "name": name})
        if (
            not isinstance(command, list)
            or not command
            or len(command) > MAX_CHECK_ARGS
            or not all(isinstance(a, str) and a and len(a) <= MAX_CHECK_ARG_LEN for a in command)
        ):
            raise ValidationFailed(
                "check command must be a non-empty list of strings", detail={"field": "checks", "name": name}
            )
        trusted = entry.get("trusted", False)
        if not isinstance(trusted, bool):
            raise ValidationFailed("check trusted must be a boolean", detail={"field": "checks", "name": name})
        names.add(name)
        cleaned.append({"name": name, "command": list(command), "trusted": trusted})
    return cleaned


def create_approval(issue, profile, principal, data):
    """Human execution approval for one exact, ready, current revision."""
    # Principal kind comes from authentication, never from payload (INV-03, AC03).
    if not principal.is_human:
        raise HumanPrincipalRequired("Execution approvals require an interactive human principal")
    revision_id = data.get("revision_id")
    revision = (
        PackageRevision.objects.filter(id=revision_id, issue_id=issue.id, deleted_at__isnull=True).first()
        if revision_id and _is_uuid(revision_id)
        else None
    )
    if revision is None:
        raise NotFound("Revision not found", code="REVISION_NOT_FOUND")
    readiness = revision_readiness(revision)
    if not readiness["ready"]:
        raise ValidationFailed("Revision is not ready for execution", code="REVISION_NOT_READY", detail=readiness)
    latest = latest_revision(issue)
    current_hash = current_native_source_hash(issue.id)
    if latest is None or latest.id != revision.id or revision_is_stale(revision, current_hash):
        raise Conflict(
            "Revision is not the current content of the work item",
            code="REVISION_STALE",
            detail={"latest_revision_id": str(latest.id) if latest else None},
        )
    allowed_actions = data.get("allowed_actions") or []
    if (
        not isinstance(allowed_actions, list)
        or not allowed_actions
        or any(a not in ALLOWED_ACTIONS for a in allowed_actions)
    ):
        raise ValidationFailed(
            "allowed_actions must be a non-empty subset of the policy actions",
            code="ACTION_NOT_ALLOWED",
            detail={"allowed": list(ALLOWED_ACTIONS)},
        )
    repository_scope = _validate_repository_scope(data.get("repository_scope"), issue.project)
    if revision.package_type == PackageProfile.PackageType.CODE and not repository_scope:
        raise ValidationFailed("Code packages need a repository scope", detail={"field": "repository_scope"})
    limits = _validate_limits(data.get("limits"))
    checks = _validate_checks(data.get("checks"))
    runner = None
    if data.get("runner_profile_id"):
        runner = RunnerProfile.objects.filter(
            id=data["runner_profile_id"] if _is_uuid(data["runner_profile_id"]) else None,
            workspace_id=issue.workspace_id,
            is_active=True,
            deleted_at__isnull=True,
        ).first()
        if runner is None:
            raise ValidationFailed("Unknown runner profile", code="RUNNER_NOT_FOUND")
    hours = data.get("expires_in_hours") or DEFAULT_APPROVAL_HOURS
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        raise ValidationFailed("expires_in_hours must be an integer")
    if hours < 1 or hours > MAX_APPROVAL_HOURS:
        raise ValidationFailed("expires_in_hours out of range", detail={"max": MAX_APPROVAL_HOURS})
    now = timezone.now()
    with transaction.atomic():
        approval = ExecutionApproval.objects.create(
            issue=issue,
            revision=revision,
            revision_hash=revision.content_hash,
            approved_by=principal.user,
            approved_at=now,
            expires_at=now + timedelta(hours=hours),
            policy_version=POLICY_VERSION,
            repository_scope=repository_scope,
            allowed_actions=list(dict.fromkeys(allowed_actions)),
            runner_profile=runner,
            limits=limits,
            checks=checks,
            native_source_hash=current_hash,
            created_by=principal.user,
        )
        locked = PackageProfile.objects.select_for_update().get(pk=profile.pk)
        locked.approved_revision = revision
        locked.flags = [f for f in (locked.flags or []) if f != "scope_changed"]
        locked.save(update_fields=["approved_revision", "flags", "updated_at"])
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="package.execution.approved",
            aggregate_type="package",
            aggregate_id=issue.id,
            actor_kind="human",
            actor_id=principal.id,
            deduplication_key=f"package.execution.approved:{approval.id}",
            payload={
                "approvalId": str(approval.id),
                "revisionId": str(revision.id),
                "revisionHash": revision.content_hash,
                "policyVersion": POLICY_VERSION,
            },
            summary=f"Revision {revision.number} approved for execution",
        )
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            actor=principal.user,
            actor_kind="human",
            action="execution.approved",
            target_type="execution_approval",
            target_id=approval.id,
            detail={"revision_id": str(revision.id), "allowed_actions": approval.allowed_actions},
        )
    return approval


def revoke_approval(issue, approval, principal, reason=""):
    from . import execution

    if approval.revoked_at is not None:
        return approval
    with transaction.atomic():
        approval = ExecutionApproval.objects.select_for_update().get(pk=approval.pk)
        if approval.revoked_at is not None:
            return approval
        approval.revoked_at = timezone.now()
        approval.revoked_by = principal.user
        approval.revoke_reason = str(reason or "")[:2000]
        approval.save(update_fields=["revoked_at", "revoked_by", "revoke_reason", "updated_at"])
        profile = get_profile(issue)
        if profile is not None and profile.approved_revision_id == approval.revision_id:
            if valid_approval_for(issue, profile) is None:
                profile.approved_revision = None
                profile.save(update_fields=["approved_revision", "updated_at"])
        execution.cancel_runs(
            approval.runs.filter(status__in=ACTIVE_RUN_STATUSES), reason="approval_revoked", principal=principal
        )
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="package.execution.revoked",
            aggregate_type="package",
            aggregate_id=issue.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            deduplication_key=f"package.execution.revoked:{approval.id}",
            payload={"approvalId": str(approval.id), "reason": approval.revoke_reason},
        )
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="execution.revoked",
            target_type="execution_approval",
            target_id=approval.id,
            detail={"reason": approval.revoke_reason},
        )
    return approval


# ---------------------------------------------------------------------------
# change records (FR-W06)
# ---------------------------------------------------------------------------
CHANGE_RECORD_STATUSES = ("open", "done", "dropped")


def create_change_record(issue, profile, principal, data):
    kind = _choice(data.get("kind") or "change", ChangeRecord.Kind.choices, "kind")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValidationFailed("title is required", detail={"field": "title"})
    with transaction.atomic():
        record = ChangeRecord.objects.create(
            issue=issue,
            kind=kind,
            title=title[:255],
            description=str(data.get("description") or ""),
            revision=profile.approved_revision or profile.working_revision,
            created_by=principal.user,
        )
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="change_record.created",
            aggregate_type="package",
            aggregate_id=issue.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            deduplication_key=f"change_record.created:{record.id}",
            payload={"changeRecordId": str(record.id), "kind": kind},
        )
    return record


def update_change_record(record, data, principal):
    if "status" in data:
        record.status = _choice(data["status"], [(s, s) for s in CHANGE_RECORD_STATUSES], "status")
    if "title" in data and str(data["title"]).strip():
        record.title = str(data["title"]).strip()[:255]
    if "description" in data:
        record.description = str(data["description"] or "")
    record.updated_by = principal.user
    record.save()
    return record


# ---------------------------------------------------------------------------
# status projection (FR-B11, FR-W10, PF11)
# ---------------------------------------------------------------------------
def _delivery_summary(issue):
    try:
        from .delivery import delivery_summary  # written by the delivery workstream
    except ImportError:
        return {"delivery": "unknown", "repositories": [], "flags": []}
    try:
        summary = delivery_summary(issue) or {}
    except Exception:  # noqa: BLE001 - projection must never break reads
        return {"delivery": "unknown", "repositories": [], "flags": ["stale_evidence"]}
    return {
        "delivery": summary.get("delivery") or "unknown",
        "repositories": list(summary.get("repositories") or []),
        "flags": list(summary.get("flags") or []),
    }


def compute_package_status(issue, profile=None) -> dict:
    """Read-model projection; never a second manually maintained status copy (§8.1)."""
    from ..models import ExecutionRun, MergeRequestLink

    state = getattr(issue, "state", None)
    native_group = state.group if state is not None else None
    base = {"work_item_id": str(issue.id), "native_state_group": native_group}
    profile = profile if profile is not None else get_profile(issue)
    if profile is None:
        return {
            **base,
            "is_package": False,
            "lifecycle": None,
            "phase": None,
            "delivery": "unknown",
            "flags": [],
            "repositories": [],
            "explanations": ["Work item is not a package"],
        }
    explanations = []
    flags = [f for f in (profile.flags or []) if isinstance(f, str)]
    delivery = _delivery_summary(issue)
    for f in delivery["flags"]:
        if f not in flags:
            flags.append(f)
    delivery_state = delivery["delivery"]

    approval = valid_approval_for(issue, profile)
    runs = ExecutionRun.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
    active_run = runs.filter(status__in=ACTIVE_RUN_STATUSES).exists()
    finished_run = runs.filter(status="finished").exists()
    open_mr = MergeRequestLink.objects.filter(issue_id=issue.id, state="open", deleted_at__isnull=True).exists()
    outcome_ok = ReviewApproval.objects.filter(
        issue_id=issue.id,
        kind=ReviewApproval.Kind.OUTCOME,
        decision="approved",
        invalidated_at__isnull=True,
        deleted_at__isnull=True,
    ).exists()
    is_code = profile.package_type == PackageProfile.PackageType.CODE

    if is_code:
        completed = delivery_state in ("deployed", "released") and outcome_ok
    else:
        # Non-code deliverables complete through accepted outcome, never through git (FR-W10, AC31).
        completed = outcome_ok

    if completed:
        lifecycle, phase = "completed", "done"
        explanations.append("Completion criterion met")
    elif is_code and delivery_state in ("partially_integrated", "integrated", "deployed", "released"):
        lifecycle, phase = "review", "ship"
        explanations.append(f"Delivery {delivery_state}; completion requires deployment and outcome acceptance")
    elif active_run:
        lifecycle, phase = "active", "build"
        explanations.append("An authorized run is active")
    elif open_mr or (finished_run and delivery_state in ("not_integrated", "unknown", "rolled_back")):
        lifecycle, phase = "review", "review"
        explanations.append("Result available for review")
    elif approval is not None:
        lifecycle, phase = "ready", "ready"
        explanations.append("Approved revision; not started")
    else:
        lifecycle, phase = "draft", "drafts"
        explanations.append("No valid execution approval")

    if native_group == "completed" and not completed:
        flags.append("native_done_without_delivery")
        explanations.append("Native state is done but delivery/acceptance evidence is missing")
    if native_group == "cancelled":
        lifecycle = "cancelled"
    if issue.archived_at is not None or getattr(issue.project, "archived_at", None) is not None:
        lifecycle = "archived"
    return {
        **base,
        "is_package": True,
        "lifecycle": lifecycle,
        "phase": phase,
        "delivery": delivery_state,
        "flags": list(dict.fromkeys(flags)),
        "repositories": delivery["repositories"],
        "explanations": explanations,
        "approved_revision_id": str(profile.approved_revision_id) if profile.approved_revision_id else None,
        "working_revision_id": str(profile.working_revision_id) if profile.working_revision_id else None,
    }


# ---------------------------------------------------------------------------
# package list (FR-B07, PF07)
# ---------------------------------------------------------------------------
def package_issue_queryset(user, workspace_id, project_ids):
    """Issues with a profile incl. authorized drafts; excludes deleted/archived/foreign rows."""
    from ..capabilities import accessible_project_ids

    accessible = {str(p) for p in accessible_project_ids(user, workspace_id)}
    allowed = [p for p in {str(x) for x in project_ids} if p in accessible]
    return (
        Issue.all_objects.filter(
            workspace_id=workspace_id,
            project_id__in=allowed,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            project__archived_at__isnull=True,
            project__deleted_at__isnull=True,
            package_profile__isnull=False,
            package_profile__deleted_at__isnull=True,
        )
        .filter(Q(state__isnull=True) | ~Q(state__group="triage"))
        .select_related("state", "project", "package_profile")
        .order_by("-updated_at")
    )


def list_packages(user, workspace_id, project_ids, view="all"):
    if view not in ("all", *PHASES):
        raise ValidationFailed("Unknown view", detail={"allowed": ["all", *PHASES]})
    issues = list(package_issue_queryset(user, workspace_id, project_ids)[:500])
    assignees = {}
    for row in IssueAssignee.objects.filter(issue_id__in=[i.id for i in issues], deleted_at__isnull=True).values_list(
        "issue_id", "assignee_id"
    ):
        assignees.setdefault(row[0], []).append(str(row[1]))
    rows = []
    for issue in issues:
        status = compute_package_status(issue, issue.package_profile)
        if view != "all" and status["phase"] != view:
            continue
        rows.append(
            {
                **status,
                "name": issue.name,
                "sequence_id": issue.sequence_id,
                "project_id": str(issue.project_id),
                "project_identifier": issue.project.identifier,
                "priority": issue.priority,
                "is_draft": issue.is_draft,
                "assignee_ids": assignees.get(issue.id, []),
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                "open_questions": _open_questions(issue),
            }
        )
    return rows


def _open_questions(issue):
    from ..models import ExecutionRun

    return ExecutionRun.objects.filter(
        issue_id=issue.id, status="waiting", pause_reason="question", deleted_at__isnull=True
    ).count()
