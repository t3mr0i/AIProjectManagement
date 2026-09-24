# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Per-category retention (PRD §15.3, FR-I08, FR-C04).

Categories are configured separately. ``None`` means keep. Deletion is a hard
delete and cascades to derived data: search rows vanish and decision source
snapshots receive a ``[source deleted]`` tombstone while the decision keeps
its own confirmed text — deleted confidential data is not exposed through
hidden copies.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..errors import ValidationFailed
from ..models import (
    AIProposal,
    AuditEntry,
    ClarificationSession,
    ExecutionRun,
    InboundEvent,
    Message,
    RetentionPolicy,
    RunAction,
)
from . import search
from .events import audit

CATEGORIES = ("messages", "ai_outputs", "raw_events", "run_logs", "exports", "audit")
TERMINAL_RUN_STATES = ("failed", "cancelled", "finished")


def get_policies(workspace):
    rows = {p.category: p for p in RetentionPolicy.objects.filter(workspace=workspace, project__isnull=True)}
    return [{"category": c, "retain_days": rows[c].retain_days if c in rows else None} for c in CATEGORIES]


def set_policies(user, workspace, policies):
    for p in policies or []:
        category = p.get("category")
        if category not in CATEGORIES:
            raise ValidationFailed(f"Unknown retention category {category}")
        days = p.get("retain_days")
        if days is not None and (not isinstance(days, int) or days < 1):
            raise ValidationFailed("retain_days must be a positive integer or null")
    with transaction.atomic():
        for p in policies or []:
            row = RetentionPolicy.objects.filter(
                workspace=workspace, project__isnull=True, category=p["category"]
            ).first()
            if row is None:
                RetentionPolicy.objects.create(
                    workspace=workspace, category=p["category"], retain_days=p.get("retain_days")
                )
            else:
                row.retain_days = p.get("retain_days")
                row.save(update_fields=["retain_days", "updated_at"])
        audit(
            workspace_id=workspace.id,
            action="retention.updated",
            target_type="workspace",
            target_id=workspace.id,
            actor=user,
            detail={"policies": policies},
        )
    return get_policies(workspace)


def _purge_messages(workspace, cutoff):
    from .conversations import purge_message

    msgs = list(Message.all_objects.filter(workspace=workspace, created_at__lt=cutoff))
    for m in msgs:
        purge_message(m)
    return len(msgs)


def _purge_ai_outputs(workspace, cutoff):
    n, _ = AIProposal.all_objects.filter(workspace=workspace, created_at__lt=cutoff).delete()
    c, _ = ClarificationSession.all_objects.filter(
        workspace=workspace, updated_at__lt=cutoff, status__in=["closed", "checkpoint"]
    ).delete()
    ai_msgs = list(Message.all_objects.filter(workspace=workspace, author_kind="ai", created_at__lt=cutoff))
    for m in ai_msgs:
        search.remove_document("message", m.id)
    Message.all_objects.filter(pk__in=[m.pk for m in ai_msgs]).delete()
    return n + c + len(ai_msgs)


def _purge_raw_events(workspace, cutoff):
    n, _ = (
        InboundEvent.all_objects.filter(workspace=workspace, created_at__lt=cutoff)
        .exclude(status=InboundEvent.Status.RECEIVED)
        .delete()
    )
    return n


def _purge_run_logs(workspace, cutoff):
    runs = ExecutionRun.all_objects.filter(workspace=workspace, status__in=TERMINAL_RUN_STATES)
    n, _ = RunAction.all_objects.filter(run__in=runs, created_at__lt=cutoff).delete()
    return n


def _purge_audit(workspace, cutoff):
    n, _ = AuditEntry.objects.filter(workspace=workspace, created_at__lt=cutoff).delete()
    return n


def _purge_exports(workspace, cutoff):
    from .exports import purge_expired

    return purge_expired(workspace, cutoff=cutoff)


PURGERS = {
    "messages": _purge_messages,
    "ai_outputs": _purge_ai_outputs,
    "raw_events": _purge_raw_events,
    "run_logs": _purge_run_logs,
    "exports": _purge_exports,
    "audit": _purge_audit,
}


def apply(workspace, *, user=None, now=None):
    now = now or timezone.now()
    result = {}
    for policy in get_policies(workspace):
        days = policy["retain_days"]
        if days is None:
            deleted = 0
            if policy["category"] == "exports":
                # Expired export bundles are always removed, independent of a retention period.
                from .exports import purge_expired

                deleted = purge_expired(workspace, now=now)
            result[policy["category"]] = {"retain_days": None, "deleted": deleted}
            continue
        cutoff = now - timedelta(days=days)
        with transaction.atomic():
            deleted = PURGERS[policy["category"]](workspace, cutoff)
        result[policy["category"]] = {"retain_days": days, "deleted": deleted, "cutoff": cutoff}
    audit(
        workspace_id=workspace.id,
        action="retention.applied",
        target_type="workspace",
        target_id=workspace.id,
        actor=user,
        actor_kind="human" if user else "system",
        detail={k: v["deleted"] for k, v in result.items()},
    )
    return result
