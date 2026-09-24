# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Transactional outbox / domain event store (schema domain-event 1.1.0).

``emit`` must be called inside the same ``transaction.atomic`` block as the
business change. The unique ``(workspace, deduplication_key)`` constraint makes
redelivery idempotent (INV-07). Events are published after commit via
``transaction.on_commit`` so consumers never see half-saved rows.
"""

import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.package_flow.models import AuditEntry, DomainEvent

SCHEMA_VERSION = "1.1.0"

EVENT_TYPES = {
    "package.revision.created",
    "package.execution.approved",
    "run.claimed",
    "run.started",
    "run.finished",
    "run.cancelled",
    "review.approved",
    "git.merge.observed",
    "deployment.observed",
    "release.observed",
    "decision.published",
    "integration.stale",
    "access.revoked",
}

# Extension-internal event types (not part of the 1.1.0 transport enum; never exported as DomainEvent 1.1).
INTERNAL_EVENT_TYPES = {
    "package.profile.activated",
    "package.execution.revoked",
    "package.scope_changed",
    "run.heartbeat",
    "run.progress",
    "run.paused",
    "claim.released",
    "git.commit.observed",
    "git.mr.observed",
    "ci.check.observed",
    "review.invalidated",
    "delivery.rolled_back",
    "native.state.observed",
    "native.description.changed",
    "question.raised",
    "spec.exported",
    "spec.imported",
    "spec.published",
    "diagram.changed",
    "dependency.changed",
    "milestone.changed",
    "integration.recovered",
    "change_record.created",
}

HUMAN_ONLY_EVENTS = {"package.execution.approved", "review.approved"}


def emit(
    *,
    workspace_id,
    event_type,
    aggregate_type,
    aggregate_id,
    actor_kind,
    actor_id,
    payload=None,
    project_id=None,
    issue_id=None,
    occurred_at=None,
    correlation_id=None,
    causation_id=None,
    deduplication_key=None,
    source_kind="platform",
    source_id="plane",
    source_instance_id="local",
    summary="",
    is_fixture=False,
):
    """Persist one normalized event; returns (event, created)."""
    if event_type not in EVENT_TYPES and event_type not in INTERNAL_EVENT_TYPES:
        raise ValueError(f"Unknown event type {event_type}")
    if event_type in HUMAN_ONLY_EVENTS and actor_kind != "human":
        raise ValueError(f"{event_type} requires a human actor")
    now = timezone.now()
    event_id = uuid.uuid4()
    dedup = deduplication_key or f"{event_type}:{event_id}"
    try:
        with transaction.atomic():
            event = DomainEvent.objects.create(
                id=event_id,
                workspace_id=workspace_id,
                project_id=project_id,
                issue_id=issue_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                occurred_at=occurred_at or now,
                received_at=now,
                correlation_id=correlation_id or uuid.uuid4(),
                causation_id=causation_id,
                deduplication_key=dedup,
                source_kind=source_kind,
                source_id=source_id,
                source_instance_id=source_instance_id,
                actor_kind=actor_kind,
                actor_id=str(actor_id),
                payload=payload or {},
                summary=summary[:500],
                is_fixture=is_fixture,
            )
    except IntegrityError:
        existing = DomainEvent.objects.get(workspace_id=workspace_id, deduplication_key=dedup)
        return existing, False
    transaction.on_commit(lambda: _mark_published(event.id))
    return event, True


def _mark_published(event_id):
    DomainEvent.objects.filter(id=event_id, published_at__isnull=True).update(published_at=timezone.now())


def to_contract(event: DomainEvent) -> dict:
    """Serialize to DomainEvent 1.1.0 transport shape."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(event.id),
        "workspaceId": str(event.workspace_id),
        "eventType": event.event_type,
        "aggregateType": event.aggregate_type,
        "aggregateId": str(event.aggregate_id),
        "occurredAt": event.occurred_at.isoformat(),
        "receivedAt": event.received_at.isoformat(),
        "correlationId": str(event.correlation_id),
        "causationId": str(event.causation_id) if event.causation_id else None,
        "deduplicationKey": event.deduplication_key,
        "source": {"kind": event.source_kind, "id": event.source_id, "instanceId": event.source_instance_id},
        "actor": {"kind": event.actor_kind, "id": event.actor_id},
        "payload": event.payload,
    }


def audit(*, workspace_id, action, target_type, target_id, actor=None, actor_kind="human", project_id=None,
          issue_id=None, correlation_id=None, detail=None):
    return AuditEntry.objects.create(
        workspace_id=workspace_id,
        project_id=project_id,
        issue_id=issue_id,
        actor=actor,
        actor_kind=actor_kind,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        correlation_id=correlation_id,
        detail=detail or {},
    )
