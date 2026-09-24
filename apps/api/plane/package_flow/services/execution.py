# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runner registration, claims (lease + fencing), runs, manifest and the controlled action gate.

Requirement refs: FR-G03..FR-G07, FR-B05..FR-B07, FR-I07, INV-01, INV-03, INV-04, INV-09.

No customer code runs here; these functions only coordinate an external runner
that connects outbound. Every gate recomputes the authoritative state
synchronously (native source hash, approval, claim, lease, capability) and
never relies on a previously projected event (PF06).
"""

import fnmatch
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..capabilities import has_capability
from ..errors import Conflict, DomainError, HumanPrincipalRequired, NotFound, PermissionDenied, ValidationFailed
from ..models import (
    Capability,
    Claim,
    Evidence,
    ExecutionApproval,
    ExecutionRun,
    FencingCounter,
    RepositoryBinding,
    RunAction,
    RunnerProfile,
)
from ..principal import hash_token
from . import events
from .packages import (
    ACTIVE_RUN_STATUSES,
    CONTRACT_VERSION,
    approval_state,
    canonical_json,
    current_native_source_hash,
    get_profile,
    sha256_hex,
    valid_approval_for,
)

DEFAULT_LEASE_SECONDS = 300
MIN_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 3600
RUN_TOKEN_GRACE_SECONDS = 300
RUN_EVENT_TYPES = ("started", "progress", "waiting", "finished", "failed", "question")
TERMINAL_RUN_STATUSES = ("finished", "failed", "cancelled")


class GateRejected(DomainError):
    status_code = 409
    code = "GATE_REJECTED"


# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
def register_runner(workspace, principal, name, kind="local"):
    """Returns (runner, plaintext_token). Only the sha256 of the token is stored."""
    if not principal.is_human:
        raise HumanPrincipalRequired("Runners are registered by a human user")
    name = str(name or "").strip()
    if not name:
        raise ValidationFailed("name is required", detail={"field": "name"})
    if kind not in {c for c, _ in RunnerProfile.Kind.choices}:
        raise ValidationFailed("invalid runner kind", detail={"allowed": [c for c, _ in RunnerProfile.Kind.choices]})
    token = "pfr_" + secrets.token_urlsafe(32)
    with transaction.atomic():
        runner = RunnerProfile.objects.create(
            workspace=workspace,
            name=name[:255],
            kind=kind,
            owner=principal.user,
            token_hash=hash_token(token),
            token_prefix=token[:10],
            created_by=principal.user,
        )
        events.audit(
            workspace_id=workspace.id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="runner.registered",
            target_type="runner",
            target_id=runner.id,
            detail={"name": runner.name, "kind": kind},
        )
    return runner, token


def deactivate_runner(runner, principal, reason="runner_deactivated"):
    with transaction.atomic():
        RunnerProfile.objects.filter(pk=runner.pk).update(is_active=False, updated_at=timezone.now())
        claims = Claim.objects.filter(runner=runner, status=Claim.Status.ACTIVE)
        _revoke_claims(claims, reason, principal)
        events.audit(
            workspace_id=runner.workspace_id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="runner.deactivated",
            target_type="runner",
            target_id=runner.id,
        )


# ---------------------------------------------------------------------------
# claims (FR-G04)
# ---------------------------------------------------------------------------
def unit_key_for(issue_id, binding_id=None):
    return f"{issue_id}:{binding_id or 'none'}"


def _next_fencing_token(unit_key):
    FencingCounter.objects.get_or_create(unit_key=unit_key)
    counter = FencingCounter.objects.select_for_update().get(unit_key=unit_key)
    counter.value += 1
    counter.save(update_fields=["value"])
    return counter.value


def _current_fencing_value(unit_key):
    return FencingCounter.objects.filter(unit_key=unit_key).values_list("value", flat=True).first() or 0


def _holder_detail(claim):
    return {
        "claim_id": str(claim.id),
        "holder_id": str(claim.holder_id),
        "runner_name": claim.runner.name if claim.runner_id else None,
        "lease_expires_at": claim.lease_expires_at.isoformat(),
    }


def expire_stale_claims(unit_key=None, now=None):
    """Mark claims whose lease ran out as expired; their runs become visibly stale (FR-G07)."""
    now = now or timezone.now()
    qs = Claim.objects.filter(status=Claim.Status.ACTIVE, lease_expires_at__lte=now, deleted_at__isnull=True)
    if unit_key is not None:
        qs = qs.filter(unit_key=unit_key)
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        return 0
    Claim.objects.filter(id__in=ids, status=Claim.Status.ACTIVE).update(status=Claim.Status.EXPIRED, updated_at=now)
    ExecutionRun.objects.filter(claim_id__in=ids, status__in=("claimed", "running")).update(
        status=ExecutionRun.Status.WAITING, pause_reason="lease_expired", updated_at=now
    )
    return len(ids)


def create_claim(issue, principal, data):
    """Atomic exclusive claim; returns the claim. 409 CLAIM_HELD names the holder."""
    if issue.project.archived_at is not None:
        raise Conflict("Project is archived", code="PROJECT_ARCHIVED")
    profile = get_profile(issue)
    if profile is None:
        raise NotFound("Work item has no package profile", code="NO_PROFILE")
    approval = _approval_for_claim(issue, profile, data.get("approval_id"))
    runner = principal.runner
    if approval.runner_profile_id and (runner is None or runner.id != approval.runner_profile_id):
        raise PermissionDenied("Approval is bound to another runner", code="RUNNER_NOT_ALLOWED")
    binding_id = data.get("repository_binding_id")
    if binding_id:
        scope_ids = {str(s.get("binding_id")) for s in approval.repository_scope or []}
        if (
            str(binding_id) not in scope_ids
            or not RepositoryBinding.objects.filter(
                id=binding_id, project_id=issue.project_id, deleted_at__isnull=True
            ).exists()
        ):
            raise ValidationFailed("Repository binding is not in the approved scope", code="BINDING_NOT_IN_SCOPE")
    exclusive = data.get("exclusive", True)
    exclusive = exclusive if isinstance(exclusive, bool) else str(exclusive).lower() != "false"
    try:
        lease_seconds = int(data.get("lease_seconds") or DEFAULT_LEASE_SECONDS)
    except (TypeError, ValueError):
        raise ValidationFailed("lease_seconds must be an integer")
    lease_seconds = max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, lease_seconds))
    unit_key = unit_key_for(issue.id, binding_id)
    expire_stale_claims(unit_key)
    now = timezone.now()
    try:
        with transaction.atomic():
            token = _next_fencing_token(unit_key)
            claim = Claim.objects.create(
                issue=issue,
                repository_binding_id=binding_id or None,
                unit_key=unit_key,
                exclusive=exclusive,
                holder=principal.user,
                runner=runner,
                approval=approval,
                fencing_token=token,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                last_heartbeat_at=now,
                created_by=principal.user,
            )
            events.emit(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.id,
                event_type="run.claimed",
                aggregate_type="run",
                aggregate_id=claim.id,
                actor_kind=principal.kind,
                actor_id=principal.id,
                source_kind="runner" if runner else "platform",
                deduplication_key=f"run.claimed:{claim.id}",
                payload={"claimId": str(claim.id), "fencingToken": token, "exclusive": exclusive},
                summary="Package claimed",
            )
    except IntegrityError:
        holder = (
            Claim.objects.select_related("runner")
            .filter(unit_key=unit_key, status=Claim.Status.ACTIVE, exclusive=True)
            .first()
        )
        raise Conflict(
            "Another exclusive claim is active for this unit",
            code="CLAIM_HELD",
            detail={"holder": _holder_detail(holder) if holder else None},
        )
    return claim


def _approval_for_claim(issue, profile, approval_id):
    if approval_id:
        approval = ExecutionApproval.objects.filter(id=approval_id, issue_id=issue.id).first()
        if approval is None:
            raise Conflict("Approval not found for this work item", code="REVISION_NOT_APPROVED")
        _check_approval(approval, profile)
        return approval
    approval = valid_approval_for(issue, profile)
    if approval is None:
        raise Conflict("No valid execution approval for this package", code="REVISION_NOT_APPROVED")
    return approval


def _check_approval(approval, profile):
    state = approval_state(approval)
    if state == "revoked":
        raise Conflict("Approval was revoked", code="APPROVAL_REVOKED")
    if state == "expired":
        raise Conflict("Approval expired", code="APPROVAL_EXPIRED")
    if profile is None or profile.approved_revision_id != approval.revision_id:
        raise Conflict("Approval is not for the currently approved revision", code="REVISION_NOT_APPROVED")


def _check_claim_ownership(claim, principal):
    if principal.runner is not None:
        if claim.runner_id != principal.runner.id:
            raise NotFound("Claim not found")
    elif claim.holder_id != principal.user.id:
        raise NotFound("Claim not found")


def _require_run_start(principal, claim_or_run):
    """The responsible human must still hold run.start right now (FR-I07, AC14)."""
    if not has_capability(principal.user, claim_or_run.workspace_id, claim_or_run.project_id, Capability.RUN_START):
        raise PermissionDenied("Missing capability 'run.start'", detail={"capability": "run.start"})


def _check_fencing(claim, fencing_token, now):
    try:
        token = int(fencing_token)
    except (TypeError, ValueError):
        raise Conflict("Fencing token missing", code="STALE_FENCING_TOKEN")
    if token != claim.fencing_token or claim.fencing_token != _current_fencing_value(claim.unit_key):
        raise Conflict("Fencing token is stale", code="STALE_FENCING_TOKEN")
    if claim.status != Claim.Status.ACTIVE:
        code = "LEASE_EXPIRED" if claim.status == Claim.Status.EXPIRED else "CLAIM_INVALID"
        raise Conflict(f"Claim is {claim.status}", code=code)
    if claim.lease_expires_at <= now:
        Claim.objects.filter(pk=claim.pk, status=Claim.Status.ACTIVE).update(status=Claim.Status.EXPIRED)
        raise Conflict("Lease expired", code="LEASE_EXPIRED")


def get_claim_for(principal, claim_id):
    claim = Claim.objects.select_related("runner", "project").filter(id=claim_id, deleted_at__isnull=True).first()
    if claim is None:
        raise NotFound("Claim not found")
    if principal.runner is not None and claim.workspace_id != principal.runner.workspace_id:
        raise NotFound("Claim not found")
    _check_claim_ownership(claim, principal)
    return claim


def heartbeat_claim(claim, principal, fencing_token, lease_seconds=None):
    _require_run_start(principal, claim)
    now = timezone.now()
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        _check_fencing(claim, fencing_token, now)
        if claim.project.archived_at is not None:
            raise Conflict("Project is archived", code="PROJECT_ARCHIVED")
        seconds = max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, int(lease_seconds or DEFAULT_LEASE_SECONDS)))
        claim.lease_expires_at = now + timedelta(seconds=seconds)
        claim.last_heartbeat_at = now
        claim.save(update_fields=["lease_expires_at", "last_heartbeat_at", "updated_at"])
        ExecutionRun.objects.filter(claim=claim, status__in=("claimed", "running", "waiting")).update(
            last_heartbeat_at=now
        )
    return claim


def release_claim(claim, principal, fencing_token):
    now = timezone.now()
    with transaction.atomic():
        claim = Claim.objects.select_for_update().get(pk=claim.pk)
        _check_fencing(claim, fencing_token, now)
        claim.status = Claim.Status.RELEASED
        claim.released_at = now
        claim.save(update_fields=["status", "released_at", "updated_at"])
        events.emit(
            workspace_id=claim.workspace_id,
            project_id=claim.project_id,
            issue_id=claim.issue_id,
            event_type="claim.released",
            aggregate_type="run",
            aggregate_id=claim.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            deduplication_key=f"claim.released:{claim.id}",
        )
    return claim


# ---------------------------------------------------------------------------
# runs (INV-01, INV-04)
# ---------------------------------------------------------------------------
def _new_run_token():
    return "prt_" + secrets.token_urlsafe(32)


def build_manifest(run, approval, revision, issue):
    return {
        "schemaVersion": CONTRACT_VERSION,
        "runId": str(run.id),
        "workspaceId": str(issue.workspace_id),
        "projectId": str(issue.project_id),
        "workItemId": str(issue.id),
        "revisionId": str(revision.id),
        "revisionNumber": revision.number,
        "revisionHash": revision.content_hash,
        "approvalId": str(approval.id),
        "policyVersion": approval.policy_version,
        "claimId": str(run.claim_id),
        "fencingToken": run.claim.fencing_token,
        "runnerProfileId": str(run.runner_id) if run.runner_id else None,
        "mode": run.mode,
        "repositoryScope": [
            {
                "bindingId": s["binding_id"],
                "baseCommit": s["base_commit"],
                "targetBranch": s["target_branch"],
                "allowedPaths": list(s["allowed_paths"]),
            }
            for s in approval.repository_scope or []
        ],
        "allowedActions": list(approval.allowed_actions or []),
        "limits": {
            "maxSeconds": approval.limits.get("max_seconds"),
            "maxSpendMinor": approval.limits.get("max_spend_minor"),
            "currency": approval.limits.get("currency"),
        },
        "intent": {
            "title": revision.title,
            "intent": revision.intent,
            "outcome": revision.outcome,
            "nonGoals": list(revision.non_goals or []),
            "criteria": list(revision.criteria or []),
            "scope": revision.scope or {},
        },
        "expiresAt": approval.expires_at.isoformat(),
    }


def start_run(issue, principal, data):
    """Run start gate. Returns (run, plaintext_run_token)."""
    if issue.project.archived_at is not None:
        raise Conflict("Project is archived", code="PROJECT_ARCHIVED")
    profile = get_profile(issue)
    approval_id = data.get("approval_id")
    if profile is None or not approval_id:
        raise Conflict("No approved revision for this package", code="REVISION_NOT_APPROVED")
    approval = ExecutionApproval.objects.select_related("revision").filter(id=approval_id, issue_id=issue.id).first()
    if approval is None:
        raise Conflict("Approval not found for this work item", code="REVISION_NOT_APPROVED")
    _check_approval(approval, profile)
    # PF06: recompute the native source synchronously; never trust a projected event.
    if current_native_source_hash(issue.id) != approval.native_source_hash:
        raise Conflict("Native title/description changed after approval", code="NATIVE_SOURCE_CHANGED")
    mode = data.get("mode") or ("agent" if principal.runner else "human")
    if mode not in ("human", "agent"):
        raise ValidationFailed("mode must be human or agent")
    now = timezone.now()
    with transaction.atomic():
        claim = Claim.objects.select_for_update().filter(id=data.get("claim_id"), issue_id=issue.id).first()
        if claim is None:
            raise Conflict("Claim not found for this work item", code="CLAIM_INVALID")
        try:
            _check_claim_ownership(claim, principal)
            _check_fencing(claim, claim.fencing_token, now)
        except (NotFound, Conflict) as exc:
            raise Conflict(f"Claim is not valid: {exc.message}", code="CLAIM_INVALID")
        if claim.approval_id and claim.approval_id != approval.id:
            raise Conflict("Claim belongs to another approval", code="CLAIM_INVALID")
        if approval.runner_profile_id and claim.runner_id != approval.runner_profile_id:
            raise Conflict("Approval is bound to another runner", code="CLAIM_INVALID")
        if ExecutionRun.objects.filter(claim=claim, status__in=ACTIVE_RUN_STATUSES).exists():
            raise Conflict("A run is already active on this claim", code="RUN_ALREADY_ACTIVE")
        token = _new_run_token()
        max_seconds = int(approval.limits.get("max_seconds") or 3600)
        run = ExecutionRun(
            issue=issue,
            revision=approval.revision,
            approval=approval,
            claim=claim,
            runner=claim.runner,
            responsible=principal.user,
            status=ExecutionRun.Status.CLAIMED,
            mode=mode,
            agent_adapter=str(data.get("agent_adapter") or "")[:64],
            base_commits={s["binding_id"]: s["base_commit"] for s in approval.repository_scope or []},
            limits=approval.limits,
            run_token_hash=hash_token(token),
            run_token_expires_at=min(
                approval.expires_at, now + timedelta(seconds=max_seconds + RUN_TOKEN_GRACE_SECONDS)
            ),
            started_at=now,
            created_by=principal.user,
        )
        run.manifest = build_manifest(run, approval, approval.revision, issue)
        run.manifest_hash = sha256_hex(canonical_json(run.manifest))
        run.save()
        if claim.approval_id is None:
            Claim.objects.filter(pk=claim.pk).update(approval=approval)
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="run.started",
            aggregate_type="run",
            aggregate_id=run.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            source_kind="runner" if principal.runner else "platform",
            deduplication_key=f"run.started:{run.id}",
            payload={"runId": str(run.id), "revisionId": str(approval.revision_id), "approvalId": str(approval.id)},
            summary="Run started",
        )
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="run.started",
            target_type="execution_run",
            target_id=run.id,
            detail={"approval_id": str(approval.id), "claim_id": str(claim.id), "mode": mode},
        )
    return run, token


def get_run_for_token(principal, run_id, run_token):
    """Resolve a run-scoped runner call: runner principal + matching, unexpired ``X-Run-Token``."""
    run = (
        ExecutionRun.objects.select_related("claim", "approval", "project", "runner")
        .filter(id=run_id, deleted_at__isnull=True)
        .first()
    )
    if run is None:
        raise NotFound("Run not found")
    if principal.runner is not None:
        if run.workspace_id != principal.runner.workspace_id or run.claim.runner_id != principal.runner.id:
            raise NotFound("Run not found")
    elif run.responsible_id != principal.user.id:
        raise NotFound("Run not found")
    if (
        not run_token
        or not run.run_token_hash
        or not secrets.compare_digest(hash_token(run_token), run.run_token_hash)
        or run.run_token_expires_at is None
        or run.run_token_expires_at <= timezone.now()
    ):
        raise PermissionDenied("Run token is invalid or expired", code="RUN_TOKEN_INVALID")
    return run


def record_run_event(run, principal, data):
    kind = data.get("type")
    if kind not in RUN_EVENT_TYPES:
        raise ValidationFailed("unknown run event type", detail={"allowed": list(RUN_EVENT_TYPES)})
    _require_run_start(principal, run)
    now = timezone.now()
    with transaction.atomic():
        run = ExecutionRun.objects.select_for_update().get(pk=run.pk)
        if run.status in TERMINAL_RUN_STATUSES:
            raise Conflict(f"Run is {run.status}", code="RUN_CANCELLED" if run.status == "cancelled" else "RUN_ENDED")
        claim = Claim.objects.get(pk=run.claim_id)
        _check_fencing(claim, data.get("fencing_token"), now)
        detail = data.get("detail") or {}
        if not isinstance(detail, dict):
            raise ValidationFailed("detail must be an object")
        event_type = "run.progress"
        run.last_heartbeat_at = now
        if kind == "started":
            if run.pause_reason == "scope_changed":
                raise Conflict("Run is paused because the native scope changed", code="RUN_PAUSED")
            run.status = ExecutionRun.Status.RUNNING
            run.pause_reason = ""
            run.started_at = run.started_at or now
            event_type = "run.progress"
        elif kind == "progress":
            if run.status == ExecutionRun.Status.CLAIMED:
                run.status = ExecutionRun.Status.RUNNING
            run.progress = detail
        elif kind in ("waiting", "question"):
            run.status = ExecutionRun.Status.WAITING
            run.pause_reason = "question" if kind == "question" else str(detail.get("reason") or "waiting")[:64]
            run.progress = {**(run.progress or {}), "question": detail} if kind == "question" else run.progress
            event_type = "question.raised" if kind == "question" else "run.paused"
        elif kind == "finished":
            run.status = ExecutionRun.Status.FINISHED
            run.finished_at = now
            run.result = detail
            event_type = "run.finished"
        elif kind == "failed":
            run.status = ExecutionRun.Status.FAILED
            run.finished_at = now
            run.result = detail
            event_type = "run.finished"
        run.save()
        events.emit(
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            issue_id=run.issue_id,
            event_type=event_type,
            aggregate_type="run",
            aggregate_id=run.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            source_kind="runner",
            source_id=str(run.runner_id or "human"),
            payload={"runId": str(run.id), "type": kind, "status": run.status, "detail": detail},
        )
    return run


def _path_allowed(path, allowed_patterns):
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        return False
    parts = path.split("/")
    if ".." in parts or "." in parts:
        return False
    for pattern in allowed_patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if pattern.endswith("/**") and (path == pattern[:-3] or path.startswith(pattern[:-2])):
            return True
    return False


def evaluate_action(run, principal, data, now=None):
    """Pure-ish gate evaluation; returns (accepted, code, message). Does not write."""
    now = now or timezone.now()
    action = data.get("action")
    detail = data.get("detail") or {}
    if not isinstance(detail, dict):
        return False, "VALIDATION_FAILED", "detail must be an object"
    if not has_capability(principal.user, run.workspace_id, run.project_id, Capability.RUN_START):
        return False, "PERMISSION_DENIED", "Responsible user no longer holds run.start"
    if run.project.archived_at is not None or run.project.deleted_at is not None:
        return False, "PROJECT_ARCHIVED", "Project is archived"
    if run.status == ExecutionRun.Status.CANCELLED or run.cancel_requested_at is not None:
        return False, "RUN_CANCELLED", "Run was cancelled"
    if run.status in ("finished", "failed"):
        return False, "RUN_ENDED", "Run has ended"
    claim = Claim.objects.get(pk=run.claim_id)
    try:
        _check_fencing(claim, data.get("fencing_token"), now)
    except Conflict as exc:
        return False, exc.code, exc.message
    if run.status == ExecutionRun.Status.WAITING and run.pause_reason in ("scope_changed", "lease_expired"):
        return False, "RUN_PAUSED", f"Run is paused ({run.pause_reason})"
    approval = ExecutionApproval.objects.get(pk=run.approval_id)
    state = approval_state(approval, now)
    if state != "valid":
        return False, "APPROVAL_REVOKED" if state == "revoked" else "APPROVAL_EXPIRED", f"Approval {state}"
    if current_native_source_hash(run.issue_id) != approval.native_source_hash:
        return False, "NATIVE_SOURCE_CHANGED", "Native title/description changed after approval"
    # Server-side policy is the only source of rights; repo content cannot extend it (AC27).
    if action not in (approval.allowed_actions or []):
        return False, "ACTION_NOT_ALLOWED", f"Action '{action}' is not allowed by the approval"
    paths = detail.get("paths") or []
    if paths:
        if not isinstance(paths, list):
            return False, "VALIDATION_FAILED", "paths must be a list"
        scope = approval.repository_scope or []
        binding_id = detail.get("binding_id")
        if binding_id:
            scope = [s for s in scope if s.get("binding_id") == str(binding_id)]
        allowed = [p for s in scope for p in s.get("allowed_paths", [])]
        bad = [p for p in paths if not _path_allowed(p, allowed)]
        if bad:
            return False, "PATH_NOT_ALLOWED", f"Paths outside the approved scope: {bad[:5]}"
    try:
        spend = int(detail.get("spend_minor") or 0)
    except (TypeError, ValueError):
        return False, "VALIDATION_FAILED", "spend_minor must be an integer"
    if spend < 0:
        return False, "VALIDATION_FAILED", "spend_minor must be >= 0"
    max_spend = int((approval.limits or {}).get("max_spend_minor") or 0)
    if run.spend_minor + spend > max_spend:
        return False, "BUDGET_EXCEEDED", "Spend limit exceeded"
    max_seconds = int((approval.limits or {}).get("max_seconds") or 0)
    started = run.started_at or run.created_at
    if max_seconds and (now - started).total_seconds() >= max_seconds:
        return False, "TIME_LIMIT_EXCEEDED", "Run exceeded its time limit"
    return True, "", ""


def perform_action(run, principal, data):
    """Controlled action gate. Every decision is logged as a RunAction; rejections raise 409."""
    now = timezone.now()
    with transaction.atomic():
        run = ExecutionRun.objects.select_for_update().select_related("project").get(pk=run.pk)
        accepted, code, message = evaluate_action(run, principal, data, now)
        try:
            fencing = int(data.get("fencing_token"))
        except (TypeError, ValueError):
            fencing = -1
        detail = data.get("detail") if isinstance(data.get("detail"), dict) else {}
        RunAction.objects.create(
            issue=run.issue,
            run=run,
            action=str(data.get("action") or "")[:32],
            fencing_token=fencing,
            accepted=accepted,
            reason=code,
            detail=detail,
        )
        if accepted:
            spend = int(detail.get("spend_minor") or 0)
            if spend:
                run.spend_minor += spend
            if run.status == ExecutionRun.Status.CLAIMED:
                run.status = ExecutionRun.Status.RUNNING
            run.last_heartbeat_at = now
            run.save(update_fields=["spend_minor", "status", "last_heartbeat_at", "updated_at"])
    if not accepted:
        status_code = 403 if code == "PERMISSION_DENIED" else 422 if code == "VALIDATION_FAILED" else 409
        raise GateRejected(message, code=code, status_code=status_code)
    return {"accepted": True, "action": data.get("action")}


def record_evidence(run, principal, data):
    if run.status == ExecutionRun.Status.CANCELLED:
        raise Conflict("Run was cancelled", code="RUN_CANCELLED")
    _require_run_start(principal, run)
    name = str(data.get("name") or "").strip()
    kind = str(data.get("kind") or "").strip()
    if not name or not kind:
        raise ValidationFailed("kind and name are required")
    result = data.get("result") or Evidence.Result.UNKNOWN
    if result not in {c for c, _ in Evidence.Result.choices}:
        raise ValidationFailed("invalid result")
    runner_kind = run.runner.kind if run.runner_id else "local"
    trust = Evidence.Trust.LOCAL_SELF_REPORT if runner_kind == "local" else Evidence.Trust.RUNNER_REPORTED
    binding_id = data.get("repository_binding_id")
    if binding_id and not RepositoryBinding.objects.filter(id=binding_id, project_id=run.project_id).exists():
        raise ValidationFailed("Unknown repository binding", code="BINDING_NOT_FOUND")
    criterion_ids = data.get("criterion_ids") or []
    if not isinstance(criterion_ids, list):
        raise ValidationFailed("criterion_ids must be a list")
    evidence = Evidence.objects.create(
        issue=run.issue,
        kind=kind[:32],
        name=name[:255],
        source=f"runner:{run.runner_id or 'human'}",
        trust=trust,
        result=result,
        repository_binding_id=binding_id or None,
        commit_sha=str(data.get("commit_sha") or "")[:64],
        artifact_ref=str(data.get("artifact_ref") or "")[:500],
        criterion_ids=[str(c) for c in criterion_ids],
        run=run,
        occurred_at=timezone.now(),
        url=str(data.get("url") or "")[:1000],
        detail=data.get("detail") if isinstance(data.get("detail"), dict) else {},
    )
    return evidence


# ---------------------------------------------------------------------------
# cancel / revocation (FR-G06, FR-B07, FR-I07)
# ---------------------------------------------------------------------------
def cancel_runs(runs_qs, reason, principal=None):
    """Cancel runs: block further actions and invalidate run tokens. Returns count."""
    now = timezone.now()
    runs = list(runs_qs.select_related(None))
    for run in runs:
        ExecutionRun.objects.filter(pk=run.pk).update(
            status=ExecutionRun.Status.CANCELLED,
            cancel_requested_at=now,
            run_token_hash="",
            run_token_expires_at=now,
            pause_reason=str(reason)[:64],
            finished_at=now,
            updated_at=now,
        )
        events.emit(
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            issue_id=run.issue_id,
            event_type="run.cancelled",
            aggregate_type="run",
            aggregate_id=run.id,
            actor_kind=principal.kind if principal else "system",
            actor_id=principal.id if principal else "system",
            deduplication_key=f"run.cancelled:{run.id}",
            payload={"runId": str(run.id), "reason": reason},
        )
    return len(runs)


def cancel_run(run, principal, reason="cancelled"):
    with transaction.atomic():
        run = ExecutionRun.objects.select_for_update().get(pk=run.pk)
        if run.status not in TERMINAL_RUN_STATUSES:
            cancel_runs(ExecutionRun.objects.filter(pk=run.pk), reason, principal)
        events.audit(
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            issue_id=run.issue_id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="run.cancelled",
            target_type="execution_run",
            target_id=run.id,
            detail={"reason": reason},
        )
    return ExecutionRun.objects.get(pk=run.pk)


def _revoke_claims(claims_qs, reason, principal=None):
    now = timezone.now()
    claim_ids = list(claims_qs.values_list("id", flat=True))
    if claim_ids:
        Claim.objects.filter(id__in=claim_ids).update(status=Claim.Status.REVOKED, released_at=now, updated_at=now)
    cancel_runs(ExecutionRun.objects.filter(claim_id__in=claim_ids, status__in=ACTIVE_RUN_STATUSES), reason, principal)
    return len(claim_ids)


def _emit_access_revoked(workspace_id, project_id, reason, detail):
    events.emit(
        workspace_id=workspace_id,
        project_id=project_id,
        event_type="access.revoked",
        aggregate_type="project",
        aggregate_id=project_id,
        actor_kind="system",
        actor_id="system",
        payload={"reason": reason, **detail},
    )


def revoke_for_project(project, reason="project_archived"):
    """Archive/delete: revoke active claims and cancel runs in the project (FR-B07)."""
    with transaction.atomic():
        claims = Claim.objects.filter(project_id=project.id, status=Claim.Status.ACTIVE)
        count = _revoke_claims(claims, reason)
        cancelled = cancel_runs(
            ExecutionRun.objects.filter(project_id=project.id, status__in=ACTIVE_RUN_STATUSES), reason
        )
        if count or cancelled:
            _emit_access_revoked(project.workspace_id, project.id, reason, {"claims": count, "runs": cancelled})
    return count


def revoke_for_member(user, project, reason="membership_revoked"):
    """Membership deactivation: revoke that member's claims/runs in the project (FR-I07)."""
    with transaction.atomic():
        claims = Claim.objects.filter(project_id=project.id, holder=user, status=Claim.Status.ACTIVE)
        count = _revoke_claims(claims, reason)
        cancelled = cancel_runs(
            ExecutionRun.objects.filter(project_id=project.id, responsible=user, status__in=ACTIVE_RUN_STATUSES),
            reason,
        )
        if count or cancelled:
            _emit_access_revoked(
                project.workspace_id, project.id, reason, {"memberId": str(user.id), "claims": count, "runs": cancelled}
            )
    return count


def pause_runs_for_scope_change(issue_id, new_native_hash):
    """Pause active runs whose approval no longer matches the native source (J05)."""
    runs = ExecutionRun.objects.filter(
        issue_id=issue_id, status__in=("queued", "claimed", "running", "waiting")
    ).exclude(approval__native_source_hash=new_native_hash)
    return runs.update(status=ExecutionRun.Status.WAITING, pause_reason="scope_changed", updated_at=timezone.now())


def expire_leases():
    return expire_stale_claims()
