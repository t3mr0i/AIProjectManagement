# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Integration connections, webhook inbox, reconciliation and tracker sync.

Requirement refs: FR-I02..FR-I06, FR-B10, INV-07, INV-08, PRD §12.3,
MIGRATION §4.

Guarantees
* Webhook ingress authenticates against the *connection row*; the workspace
  always comes from that row — never from the payload.
* An ``InboundEvent`` is durably inserted before the ack. ``(connection,
  external_event_id)`` is unique: a redelivery answers ``duplicate: true`` and
  is never reprocessed.
* Processing is idempotent and callable synchronously (tests) or as the celery
  task ``plane.package_flow.tasks.process_inbound_event``.
* Webhook secrets are stored encrypted (Fernet, key derived from SECRET_KEY),
  never returned by the API and never logged.
* Field ownership (FR-I03): external-owned fields are applied to the native
  Issue; platform-owned fields changed externally create a ``SyncConflict``.
  Our own write echoes are recognized by the operation correlation in
  ``ExternalLink.observed_fields["_last_op"]``; a *different* concurrent
  external value in the same window becomes a conflict, not a silent drop.
"""

import json
import logging
import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.license.utils.encryption import decrypt_data, encrypt_data

from ..adapters import get_adapter
from ..adapters.base import (
    ISSUE_UPDATED,
    PARTIAL,
    SUPPORTED,
    UNKNOWN,
    CapabilityUnsupported,
    NormalizedEvent,
    ProviderContext,
    RepoRef,
    TransportError,
    parse_time,
)
from ..errors import Conflict, DomainError, NotFound, ValidationFailed
from ..models import (
    AIProposal,
    ExternalLink,
    InboundEvent,
    IntegrationConnection,
    Provider,
    RepositoryBinding,
    SyncConflict,
)
from . import events

logger = logging.getLogger("plane.package_flow.integrations")

PLATFORM = "platform"
EXTERNAL = "external"
OWNERSHIP_VALUES = (PLATFORM, EXTERNAL)

# canonical tracker field -> native Issue attribute (only these may be applied)
_NATIVE_ATTR = {"priority": "priority", "title": "name"}
# Observed only, never mapped to native state or execution rights (AC02, FR-B05).
OBSERVE_ONLY_FIELDS = {"status"}
PLANE_PRIORITIES = {"urgent", "high", "medium", "low", "none"}

MAX_ATTEMPTS = 8
DISABLED = IntegrationConnection.Status.DISABLED
ACTIVE = IntegrationConnection.Status.ACTIVE
OFFLINE = IntegrationConnection.Status.OFFLINE
DEGRADED = IntegrationConnection.Status.DEGRADED


def stale_after() -> timedelta:
    return timedelta(seconds=int(getattr(settings, "PACKAGE_FLOW_SYNC_STALE_SECONDS", 3600)))


def echo_window() -> timedelta:
    return timedelta(seconds=int(getattr(settings, "PACKAGE_FLOW_ECHO_WINDOW_SECONDS", 600)))


def overlap_window() -> timedelta:
    return timedelta(seconds=int(getattr(settings, "PACKAGE_FLOW_RECONCILE_OVERLAP_SECONDS", 300)))


# ---------------------------------------------------------------------------
# Secrets / credentials
# ---------------------------------------------------------------------------


def encrypt_secret(secret: str) -> str:
    return encrypt_data(secret) if secret else ""


def decrypt_secret(stored: str) -> str:
    return decrypt_data(stored) if stored else ""


def resolve_token(connection) -> str:
    """Resolve ``credential_ref``. Supported: ``env:<VAR>``. Vault refs are not implemented."""
    ref = connection.credential_ref or ""
    if ref.startswith("env:"):
        return os.environ.get(ref[4:], "")
    return ""


def provider_context(connection) -> ProviderContext:
    return ProviderContext(
        instance_url=connection.instance_url,
        token=resolve_token(connection),
        instance_type=connection.instance_type,
        edition=connection.edition,
    )


def declaration_for(connection, adapter=None):
    adapter = adapter or get_adapter(connection.provider)
    return adapter.declare(instance_type=connection.instance_type, edition=connection.edition)


# ---------------------------------------------------------------------------
# Connections CRUD
# ---------------------------------------------------------------------------


def serialize_connection(c) -> dict:
    return {
        "id": str(c.id),
        "workspace_id": str(c.workspace_id),
        "provider": c.provider,
        "instance_url": c.instance_url,
        "instance_type": c.instance_type,
        "edition": c.edition,
        "display_name": c.display_name,
        "status": c.status,
        "capabilities": c.capabilities,
        "webhook_secret_configured": bool(c.webhook_secret),
        "credential_configured": bool(c.credential_ref),
        "last_successful_sync_at": c.last_successful_sync_at.isoformat() if c.last_successful_sync_at else None,
        "last_error": c.last_error,
        "backlog_count": c.backlog_count,
        "field_ownership": c.field_ownership,
        "webhook_path": f"/api/package-flow/webhooks/{c.id}/",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _validate_ownership(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or any(v not in OWNERSHIP_VALUES for v in value.values()):
        raise ValidationFailed("field_ownership must map field names to 'platform' or 'external'")
    return {str(k): v for k, v in value.items()}


def _validate_secret(provider, secret):
    if secret in (None, ""):
        return ""
    if not isinstance(secret, str) or not (16 <= len(secret) <= 100):
        raise ValidationFailed("webhook_secret must be a string of 16..100 characters")
    if provider == Provider.AZURE_DEVOPS and ":" not in secret:
        raise ValidationFailed("Azure DevOps webhook_secret must be '<user>:<password>' (basic auth)")
    return encrypt_secret(secret)


def _validate_url(url):
    try:
        URLValidator(schemes=["https", "http"])(url or "")
    except DjangoValidationError:
        raise ValidationFailed("instance_url must be a valid http(s) URL") from None
    return url.rstrip("/")


def create_connection(workspace, user, data) -> IntegrationConnection:
    provider = data.get("provider")
    if provider not in Provider.values:
        raise ValidationFailed("Unknown provider", detail={"allowed": list(Provider.values)})
    instance_url = _validate_url(data.get("instance_url"))
    existing = IntegrationConnection.objects.filter(
        workspace=workspace, provider=provider, instance_url=instance_url, deleted_at__isnull=True
    ).first()
    if existing is not None:
        raise Conflict(
            "A connection for this provider instance already exists; reconnect it instead",
            code="CONNECTION_EXISTS",
            detail={"connection_id": str(existing.id)},
        )
    c = IntegrationConnection(
        workspace=workspace,
        provider=provider,
        instance_url=instance_url,
        instance_type=data.get("instance_type") or "cloud",
        edition=data.get("edition") or "",
        display_name=data.get("display_name") or "",
        webhook_secret=_validate_secret(provider, data.get("webhook_secret")),
        credential_ref=data.get("credential_ref") or "",
        field_ownership=_validate_ownership(data.get("field_ownership")),
        created_by=user,
    )
    c.capabilities = declaration_for(c).capabilities
    c.save()
    events.audit(
        workspace_id=workspace.id,
        action="integration.connected",
        target_type="integration_connection",
        target_id=c.id,
        actor=user,
        detail={"provider": provider, "instance_url": instance_url},
    )
    return c


def update_connection(c, user, data) -> IntegrationConnection:
    changed = []
    for key in ("display_name", "edition", "instance_type", "credential_ref"):
        if key in data:
            setattr(c, key, data.get(key) or "")
            changed.append(key)
    if "webhook_secret" in data:
        c.webhook_secret = _validate_secret(c.provider, data.get("webhook_secret"))
        changed.append("webhook_secret")
    if "field_ownership" in data:
        c.field_ownership = _validate_ownership(data.get("field_ownership"))
        changed.append("field_ownership")
    if "edition" in data or "instance_type" in data:
        c.capabilities = declaration_for(c).capabilities
        changed.append("capabilities")
    reconnect = False
    if "status" in data:
        new_status = data.get("status")
        if new_status not in (ACTIVE, DISABLED):
            raise ValidationFailed("status can only be set to 'active' or 'disabled'")
        if new_status == DISABLED and c.status != DISABLED:
            c.save()
            return disconnect_connection(c, user)
        if new_status == ACTIVE and c.status != ACTIVE:
            reconnect = c.status == DISABLED
            c.status = ACTIVE
            changed.append("status")
    c.updated_by = user
    c.save()
    if reconnect:
        # Existing mappings are reused — no new links, no duplicate issues (FR-I05).
        ExternalLink.objects.filter(connection=c, sync_state="disconnected").update(sync_state="stale")
        events.audit(
            workspace_id=c.workspace_id,
            action="integration.reconnected",
            target_type="integration_connection",
            target_id=c.id,
            actor=user,
        )
    if changed:
        events.audit(
            workspace_id=c.workspace_id,
            action="integration.updated",
            target_type="integration_connection",
            target_id=c.id,
            actor=user,
            detail={
                "fields": [f for f in changed if f != "webhook_secret"]
                + (["webhook_secret(set)"] if "webhook_secret" in changed else [])
            },
        )
    return c


def disconnect_connection(c, user) -> IntegrationConnection:
    """Disable the connection; keep mappings as ``disconnected`` (FR-I06: native IDs preserved)."""
    c.status = DISABLED
    c.updated_by = user
    c.save(update_fields=["status", "updated_by", "updated_at"])
    count = ExternalLink.objects.filter(connection=c, deleted_at__isnull=True).update(sync_state="disconnected")
    events.audit(
        workspace_id=c.workspace_id,
        action="integration.disconnected",
        target_type="integration_connection",
        target_id=c.id,
        actor=user,
        detail={"links_marked_disconnected": count},
    )
    return c


def is_stale(c, now=None) -> bool:
    now = now or timezone.now()
    return c.last_successful_sync_at is not None and (now - c.last_successful_sync_at) > stale_after()


def backlog(c) -> int:
    return InboundEvent.objects.filter(
        connection=c, status__in=(InboundEvent.Status.RECEIVED, InboundEvent.Status.FAILED)
    ).count()


def connection_health(c) -> dict:
    stale = is_stale(c)
    status = c.status
    if status == ACTIVE and stale:
        status = "stale"
    degraded = status != ACTIVE
    affected = []
    if degraded:
        affected = sorted(k for k, v in (c.capabilities or {}).items() if v in (SUPPORTED, PARTIAL))
    count = backlog(c)
    return {
        "connection_id": str(c.id),
        "provider": c.provider,
        "status": status,
        "last_successful_sync_at": c.last_successful_sync_at.isoformat() if c.last_successful_sync_at else None,
        "backlog_count": count,
        "affected_capabilities": affected,
        "last_error": c.last_error,
        "live": not degraded,
        "statement": (
            "live provider state"
            if not degraded
            else "last known state only — provider data may be outdated since last successful sync"
        ),
    }


def offline_info(connections) -> list:
    """Connections that are offline/degraded/disabled or stale (AC23)."""
    now = timezone.now()
    out = []
    for c in connections:
        if c.status in (OFFLINE, DEGRADED, DISABLED) or is_stale(c, now):
            out.append(
                {
                    "connection_id": str(c.id),
                    "provider": c.provider,
                    "status": c.status if c.status != ACTIVE else "stale",
                    "last_successful_sync_at": c.last_successful_sync_at.isoformat()
                    if c.last_successful_sync_at
                    else None,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Webhook ingress
# ---------------------------------------------------------------------------


class InvalidSignature(DomainError):
    status_code = 401
    code = "INVALID_SIGNATURE"


def ingest_webhook(connection_id, headers, body: bytes):
    """Authenticate, durably store, ack. Returns ``(http_status, response_body)``."""
    c = IntegrationConnection.objects.filter(id=connection_id, deleted_at__isnull=True).first()
    if c is None or c.status == DISABLED:
        raise NotFound("Connection not found")
    adapter = get_adapter(c.provider)
    if not adapter.verify_webhook(headers, body or b"", decrypt_secret(c.webhook_secret)):
        logger.info("package_flow webhook rejected: bad signature (connection=%s)", c.id)
        raise InvalidSignature("Webhook signature invalid")
    try:
        payload = json.loads((body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValidationFailed("Webhook body is not valid JSON") from None
    if not isinstance(payload, dict):
        raise ValidationFailed("Webhook body must be a JSON object")
    delivery = adapter.delivery_id(headers, payload)[:255]
    try:
        normalized = adapter.normalize(headers, payload)
        event_type = ",".join(sorted({n.kind for n in normalized}))[:128] or UNKNOWN
        occurred = next((n.occurred_at for n in normalized if n.occurred_at), None)
    except Exception:  # noqa: BLE001 - store anyway; processing will surface the error
        event_type, occurred = "unparsed", None
    try:
        with transaction.atomic():
            ev = InboundEvent.objects.create(
                connection=c,
                workspace_id=c.workspace_id,  # never from the payload
                external_event_id=delivery,
                event_type=event_type,
                occurred_at=occurred,
                payload={"headers": adapter.persistable_headers(headers), "body": payload},
            )
    except IntegrityError:
        existing = InboundEvent.objects.filter(connection=c, external_event_id=delivery).first()
        return 200, {"accepted": True, "duplicate": True, "event_id": str(existing.id) if existing else None}
    schedule_processing(ev.id)
    return 202, {"accepted": True, "duplicate": False, "event_id": str(ev.id)}


def schedule_processing(event_id):
    if getattr(settings, "PACKAGE_FLOW_INLINE_TASKS", False):
        process_inbound_event(event_id)
        return

    def _enqueue():
        try:
            from plane.package_flow.tasks import process_inbound_event as task

            task.delay(str(event_id))
        except Exception:  # noqa: BLE001 - broker down: fall back to synchronous processing
            logger.warning("package_flow: broker enqueue failed, processing inbound event inline")
            try:
                process_inbound_event(event_id)
            except Exception:  # noqa: BLE001
                logger.exception("package_flow: inline processing failed (event stays in backlog)")

    transaction.on_commit(_enqueue)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


def normalized_from_inbound(adapter, ev) -> list:
    payload = ev.payload or {}
    if "polled" in payload:
        data = dict(payload["polled"])
        data["occurred_at"] = parse_time(data.get("occurred_at"))
        return [NormalizedEvent(**data)]
    return adapter.normalize(payload.get("headers") or {}, payload.get("body") or {})


def process_inbound_event(event_id):
    """Idempotently process one stored inbound event. Returns the final status."""
    from .delivery import handle_code_event

    with transaction.atomic():
        ev = InboundEvent.objects.select_for_update().filter(pk=event_id).first()
        if ev is None:
            return None
        if ev.status in (InboundEvent.Status.PROCESSED, InboundEvent.Status.IGNORED, InboundEvent.Status.DUPLICATE):
            return ev.status
        c = IntegrationConnection.objects.filter(pk=ev.connection_id).first()
        if c is None or c.deleted_at is not None or c.status == DISABLED:
            return ev.status  # stays in backlog until reconnect + reconcile
        adapter = get_adapter(c.provider)
        ev.attempts += 1
        try:
            with transaction.atomic():
                handled = False
                for n in normalized_from_inbound(adapter, ev):
                    if n.kind == UNKNOWN:
                        continue
                    if n.kind == ISSUE_UPDATED:
                        handled = apply_external_issue_update(c, n) or handled
                    else:
                        handled = handle_code_event(c, n, inbound=ev, adapter=adapter) or handled
            ev.status = InboundEvent.Status.PROCESSED if handled else InboundEvent.Status.IGNORED
            ev.error = ""
            ev.processed_at = timezone.now()
        except Exception as exc:  # noqa: BLE001 - recorded, retried by reconciliation
            ev.status = InboundEvent.Status.FAILED
            ev.error = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.warning("package_flow inbound event %s failed: %s", ev.id, type(exc).__name__)
        ev.save(update_fields=["status", "attempts", "processed_at", "error", "updated_at"])
        now = timezone.now()
        if ev.status == InboundEvent.Status.FAILED:
            IntegrationConnection.objects.filter(pk=c.pk).update(last_error=ev.error[:1000], backlog_count=backlog(c))
        else:
            IntegrationConnection.objects.filter(pk=c.pk).update(last_successful_sync_at=now, backlog_count=backlog(c))
        return ev.status


def reconcile_connection(connection_id) -> dict:
    """Replay unprocessed inbox, poll provider since watermark − overlap, mark gaps (FR-I04/05)."""
    c = IntegrationConnection.objects.filter(pk=connection_id, deleted_at__isnull=True).first()
    if c is None:
        raise NotFound("Connection not found")
    if c.status == DISABLED:
        return {"status": "disabled", "replayed": 0, "failed": 0, "polled": 0, "gaps": []}
    replayed = failed = polled = 0
    for ev_id in (
        InboundEvent.objects.filter(
            connection=c,
            status__in=(InboundEvent.Status.RECEIVED, InboundEvent.Status.FAILED),
            attempts__lt=MAX_ATTEMPTS,
        )
        .order_by("created_at")
        .values_list("id", flat=True)[:500]
    ):
        status = process_inbound_event(ev_id)
        replayed += 1
        failed += int(status == InboundEvent.Status.FAILED)

    adapter = get_adapter(c.provider)
    decl = declaration_for(c, adapter)
    gaps, poll_error = [], ""
    started = timezone.now()
    if decl.level("reconcile") in (SUPPORTED, PARTIAL) and decl.level("read_merge_requests") in (SUPPORTED, PARTIAL):
        watermark = parse_time((c.sync_cursor or {}).get("watermark"))
        since = watermark - overlap_window() if watermark else None
        ctx = provider_context(c)
        seen = set()
        for binding in RepositoryBinding.objects.filter(connection=c, is_active=True, deleted_at__isnull=True):
            if binding.external_id in seen:
                continue
            seen.add(binding.external_id)
            try:
                polled_events = adapter.list_merge_requests(
                    ctx, RepoRef(binding.external_id, binding.path_with_namespace), updated_after=since, limit=50
                )
            except CapabilityUnsupported:
                break
            except TransportError as exc:
                poll_error = str(exc)[:500]
                gaps.append({"repository": binding.path_with_namespace, "since": since.isoformat() if since else None})
                continue
            for n in polled_events:
                try:
                    with transaction.atomic():
                        ev = InboundEvent.objects.create(
                            connection=c,
                            workspace_id=c.workspace_id,
                            external_event_id=n.external_event_id[:255],
                            event_type=n.kind,
                            occurred_at=n.occurred_at,
                            payload={"polled": n.to_dict()},
                        )
                except IntegrityError:
                    continue  # already seen within the overlap window
                polled += 1
                failed += int(process_inbound_event(ev.id) == InboundEvent.Status.FAILED)

    updates = {"backlog_count": backlog(c)}
    if poll_error:
        updates.update(status=DEGRADED, last_error=poll_error)
        with transaction.atomic():
            events.emit(
                workspace_id=c.workspace_id,
                event_type="integration.stale",
                aggregate_type="integration",
                aggregate_id=c.id,
                actor_kind="system",
                actor_id="reconciler",
                payload={
                    "connectionId": str(c.id),
                    "gaps": gaps,
                    "lastSuccessfulSyncAt": c.last_successful_sync_at.isoformat()
                    if c.last_successful_sync_at
                    else None,
                },
                deduplication_key=f"integration.stale:{c.id}:{started:%Y%m%d%H}",
                source_kind="platform",
                summary=f"{c.provider} integration degraded",
            )
    elif failed == 0:
        updates.update(
            last_successful_sync_at=started,
            sync_cursor={"watermark": started.isoformat(), "overlap_seconds": int(overlap_window().total_seconds())},
            last_error="",
        )
        if c.status in (OFFLINE, DEGRADED):
            updates["status"] = ACTIVE
            with transaction.atomic():
                events.emit(
                    workspace_id=c.workspace_id,
                    event_type="integration.recovered",
                    aggregate_type="integration",
                    aggregate_id=c.id,
                    actor_kind="system",
                    actor_id="reconciler",
                    payload={"connectionId": str(c.id)},
                    summary=f"{c.provider} integration recovered",
                )
    IntegrationConnection.objects.filter(pk=c.pk).update(**updates)
    if not poll_error and failed == 0:
        ExternalLink.objects.filter(connection=c, sync_state="stale").update(sync_state="ok")
    return {
        "status": updates.get("status", c.status),
        "replayed": replayed,
        "failed": failed,
        "polled": polled,
        "gaps": gaps,
    }


def schedule_reconcile(connection_id):
    if getattr(settings, "PACKAGE_FLOW_INLINE_TASKS", False):
        return reconcile_connection(connection_id)

    def _enqueue():
        try:
            from plane.package_flow.tasks import reconcile_connection as task

            task.delay(str(connection_id))
        except Exception:  # noqa: BLE001
            logger.warning("package_flow: broker enqueue failed, reconciling inline")
            try:
                reconcile_connection(connection_id)
            except Exception:  # noqa: BLE001
                logger.exception("package_flow: inline reconciliation failed")

    transaction.on_commit(_enqueue)
    return None


# ---------------------------------------------------------------------------
# Tracker field sync (FR-I03, PRD §12.3)
# ---------------------------------------------------------------------------


def field_owner(link, field) -> str:
    ownership = {**(link.connection.field_ownership or {}), **(link.field_ownership or {})}
    return ownership.get(field, PLATFORM)


def _within(at_iso, window, now) -> bool:
    at = parse_time(at_iso)
    return at is not None and (now - at) <= window


def record_outbound_op(link, fields, op_id=None) -> str:
    """Remember our own write so its webhook echo is recognized (not a loop, not a conflict).

    Provider write-back itself is not implemented by the adapters yet (write_work_items
    is at most ``partial``); callers record the op when they push a platform-owned value.
    """
    op_id = op_id or str(uuid.uuid4())
    observed = dict(link.observed_fields or {})
    observed["_last_op"] = {"op_id": op_id, "fields": dict(fields), "at": timezone.now().isoformat()}
    link.observed_fields = observed
    link.save(update_fields=["observed_fields", "updated_at"])
    return op_id


def apply_external_issue_update(connection, n) -> bool:
    links = list(
        ExternalLink.objects.select_for_update()
        .select_related("connection")
        .filter(
            connection=connection,
            object_type="issue",
            external_id=n.external_issue_id,
            workspace_id=connection.workspace_id,
            deleted_at__isnull=True,
        )
    )
    handled = False
    for link in links:
        if link.sync_state == "disconnected":
            continue
        _apply_to_link(link, n)
        handled = True
    return handled


def _apply_to_link(link, n):
    from plane.db.models import Issue

    issue = Issue.all_objects.filter(pk=link.issue_id, deleted_at__isnull=True).first()
    if issue is None:
        return
    now = timezone.now()
    occurred = n.occurred_at or now
    observed = dict(link.observed_fields or {})
    field_at = dict(observed.get("_field_at") or {})
    last_op = observed.get("_last_op") or {}
    op_fields = last_op.get("fields") or {}
    in_window = bool(last_op) and _within(last_op.get("at"), echo_window(), now)
    applied, conflict_created = [], False
    for field, value in (n.fields or {}).items():
        prev_at = parse_time(field_at.get(field))
        if prev_at and occurred < prev_at:
            continue  # late/out-of-order delivery must not regress the observation
        observed[field] = value
        field_at[field] = occurred.isoformat()
        is_echo = bool(n.operation_correlation and n.operation_correlation == last_op.get("op_id")) or (
            in_window and field in op_fields and op_fields[field] == value
        )
        if is_echo or field in OBSERVE_ONLY_FIELDS or field not in _NATIVE_ATTR:
            continue
        if field == "priority" and value not in PLANE_PRIORITIES:
            continue
        attr = _NATIVE_ATTR[field]
        native_value = getattr(issue, attr)
        if value == native_value:
            continue
        concurrent = in_window and field in op_fields and op_fields[field] != value
        if field_owner(link, field) == EXTERNAL and not concurrent:
            setattr(issue, attr, value)
            applied.append(attr)
            continue
        if SyncConflict.objects.filter(link=link, field=field, status="open", external_value=value).exists():
            continue
        SyncConflict.objects.create(
            issue=issue,
            link=link,
            field=field,
            platform_value=native_value,
            external_value=value,
            platform_changed_at=parse_time(last_op.get("at")) if concurrent else issue.updated_at,
            external_changed_at=occurred,
        )
        conflict_created = True
    observed["_field_at"] = field_at
    if applied:
        issue.save(update_fields=[*applied, "updated_at"])
    link.observed_fields = observed
    link.last_synced_at = now
    update_fields = ["observed_fields", "last_synced_at", "updated_at"]
    if conflict_created:
        link.sync_state = "conflict"
        update_fields.append("sync_state")
    elif link.sync_state in ("stale",):
        link.sync_state = "ok"
        update_fields.append("sync_state")
    link.save(update_fields=update_fields)


def propose_or_apply_field(issue, field, value, *, principal, source="platform", reason=""):
    """Platform/AI write to a synced field (FR-I03, AC22).

    * field owned by an external tracker → never written; at most a proposal
    * agent/AI principal → always only a proposal
    * human on a platform-owned field → applied and recorded as outbound op
    """
    if field not in _NATIVE_ATTR:
        raise ValidationFailed("Field is not synchronizable", detail={"field": field})
    links = list(
        ExternalLink.objects.select_related("connection")
        .filter(issue=issue, object_type="issue", deleted_at__isnull=True)
        .exclude(sync_state="disconnected")
    )
    external_owner = next((lk for lk in links if field_owner(lk, field) == EXTERNAL), None)
    if external_owner is not None or not principal.is_human:
        proposal = AIProposal.objects.create(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            kind=AIProposal.Kind.PRIORITY_SUGGESTION if field == "priority" else AIProposal.Kind.DRAFT_EDIT,
            requested_by=principal.user,
            content={
                "field": field,
                "proposed_value": value,
                "current_value": getattr(issue, _NATIVE_ATTR[field]),
                "reason": reason,
                "source": source,
                "status": "proposed",
                "owner": (
                    f"external:{external_owner.connection.provider}" if external_owner is not None else "platform"
                ),
            },
        )
        return {"applied": False, "proposal_id": str(proposal.id), "owner": proposal.content["owner"]}
    setattr(issue, _NATIVE_ATTR[field], value)
    issue.save(update_fields=[_NATIVE_ATTR[field], "updated_at"])
    ops = [record_outbound_op(lk, {field: value}) for lk in links if lk.connection.status != DISABLED]
    return {"applied": True, "operation_ids": ops}


# ---------------------------------------------------------------------------
# External links & conflicts
# ---------------------------------------------------------------------------


def serialize_link(link) -> dict:
    observed = {k: v for k, v in (link.observed_fields or {}).items() if not k.startswith("_")}
    return {
        "id": str(link.id),
        "work_item_id": str(link.issue_id),
        "connection_id": str(link.connection_id),
        "provider": link.connection.provider,
        "object_type": link.object_type,
        "external_id": link.external_id,
        "external_key": link.external_key,
        "url": link.url,
        "represents_package": link.represents_package,
        "field_ownership": link.field_ownership,
        "observed_fields": observed,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "sync_state": link.sync_state,
    }


def create_external_link(issue, user, data) -> ExternalLink:
    connection = IntegrationConnection.objects.filter(
        id=data.get("connection_id"), workspace_id=issue.workspace_id, deleted_at__isnull=True
    ).first()
    if connection is None:
        raise NotFound("Connection not found")
    if connection.status == DISABLED:
        raise Conflict("Connection is disconnected", code="CONNECTION_DISABLED")
    object_type = data.get("object_type") or "issue"
    external_id = str(data.get("external_id") or "").strip()
    if not external_id:
        raise ValidationFailed("external_id is required")
    existing = ExternalLink.objects.filter(
        connection=connection, object_type=object_type, external_id=external_id, deleted_at__isnull=True
    ).first()
    if existing is not None:
        if existing.issue_id != issue.id:
            raise Conflict(
                "External object is already linked to another work item",
                code="EXTERNAL_LINK_EXISTS",
                detail={"work_item_id": str(existing.issue_id)},
            )
        return existing
    link = ExternalLink.objects.create(
        issue=issue,
        connection=connection,
        object_type=object_type,
        external_id=external_id,
        external_key=data.get("external_key") or "",
        url=data.get("url") or "",
        represents_package=bool(data.get("represents_package")),
        field_ownership=_validate_ownership(data.get("field_ownership")),
        created_by=user,
    )
    events.audit(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue_id=issue.id,
        action="integration.link_created",
        target_type="external_link",
        target_id=link.id,
        actor=user,
        detail={"provider": connection.provider, "object_type": object_type, "external_id": external_id},
    )
    return link


def serialize_conflict(c) -> dict:
    return {
        "id": str(c.id),
        "work_item_id": str(c.issue_id),
        "link_id": str(c.link_id) if c.link_id else None,
        "field": c.field,
        "platform": {
            "value": c.platform_value,
            "changed_at": c.platform_changed_at.isoformat() if c.platform_changed_at else None,
        },
        "external": {
            "value": c.external_value,
            "changed_at": c.external_changed_at.isoformat() if c.external_changed_at else None,
            "source": c.link.connection.provider if c.link_id else None,
        },
        "status": c.status,
        "resolution": c.resolution,
    }


def resolve_conflict(conflict, user, resolution) -> SyncConflict:
    if conflict.status != "open":
        raise Conflict("Conflict already resolved", code="CONFLICT_RESOLVED")
    if resolution not in ("keep_platform", "take_external"):
        raise ValidationFailed("resolution must be keep_platform or take_external")
    issue = conflict.issue
    if resolution == "take_external" and conflict.field in _NATIVE_ATTR:
        setattr(issue, _NATIVE_ATTR[conflict.field], conflict.external_value)
        issue.save(update_fields=[_NATIVE_ATTR[conflict.field], "updated_at"])
    elif resolution == "keep_platform" and conflict.link_id:
        # The platform value must be pushed back; record the op for echo detection.
        record_outbound_op(conflict.link, {conflict.field: conflict.platform_value})
    conflict.status = "resolved"
    conflict.resolution = resolution
    conflict.updated_by = user
    conflict.save(update_fields=["status", "resolution", "updated_by", "updated_at"])
    if conflict.link_id and not SyncConflict.objects.filter(link_id=conflict.link_id, status="open").exists():
        ExternalLink.objects.filter(pk=conflict.link_id, sync_state="conflict").update(sync_state="ok")
    events.audit(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue_id=issue.id,
        action="integration.conflict_resolved",
        target_type="sync_conflict",
        target_id=conflict.id,
        actor=user,
        detail={"field": conflict.field, "resolution": resolution},
    )
    return conflict


# ---------------------------------------------------------------------------
# Repositories & J01 import preview
# ---------------------------------------------------------------------------


def serialize_binding(b) -> dict:
    return {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "connection_id": str(b.connection_id),
        "provider": b.connection.provider,
        "instance_url": b.connection.instance_url,
        "external_id": b.external_id,
        "path_with_namespace": b.path_with_namespace,
        "default_branch": b.default_branch,
        "branch_rules": b.branch_rules,
        "capabilities": b.capabilities,
        "role": b.role,
        "is_active": b.is_active,
        "observed_commit": b.observed_commit,
    }


def bind_repository(project, user, data) -> RepositoryBinding:
    connection = IntegrationConnection.objects.filter(
        id=data.get("connection_id"), workspace_id=project.workspace_id, deleted_at__isnull=True
    ).first()
    if connection is None:
        raise NotFound("Connection not found")
    decl = declaration_for(connection)
    if decl.level("read_repository") not in (SUPPORTED, PARTIAL):
        raise Conflict(
            "Provider cannot read repositories", code="CAPABILITY_MISSING", detail={"capability": "read_repository"}
        )
    external_id = str(data.get("external_id") or "").strip()
    path = (data.get("path_with_namespace") or "").strip()
    if not external_id or not path:
        raise ValidationFailed("external_id and path_with_namespace are required")
    if RepositoryBinding.objects.filter(
        project=project, connection=connection, external_id=external_id, deleted_at__isnull=True
    ).exists():
        raise Conflict("Repository already bound", code="REPOSITORY_EXISTS")
    binding = RepositoryBinding.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        connection=connection,
        external_id=external_id,
        path_with_namespace=path,
        default_branch=data.get("default_branch") or "main",
        branch_rules=data.get("branch_rules") or {},
        role=data.get("role") or "",
        capabilities=decl.capabilities,
        created_by=user,
    )
    events.audit(
        workspace_id=project.workspace_id,
        project_id=project.id,
        action="integration.repository_bound",
        target_type="repository_binding",
        target_id=binding.id,
        actor=user,
        detail={"connection_id": str(connection.id), "external_id": external_id, "path": path},
    )
    return binding


SPEC_HINTS = ("openspec/", "specs/", "spec/", "docs/adr/", "adr/")
SPEC_NAMES = ("spec.md", "prd.md", "requirements.md", "design.md", "proposal.md", "tasks.md")


def _is_spec_path(path: str) -> bool:
    lower = path.lower()
    return (
        any(lower.startswith(h) or f"/{h}" in lower for h in SPEC_HINTS)
        or lower.rsplit("/", 1)[-1] in SPEC_NAMES
        or lower.endswith(".feature")
    )


def import_preview(project, data) -> dict:
    """J01: observed metadata + proposals for one commit. No writes, no events (FR-W07)."""
    connection = IntegrationConnection.objects.filter(
        id=data.get("connection_id"), workspace_id=project.workspace_id, deleted_at__isnull=True
    ).first()
    if connection is None:
        raise NotFound("Connection not found")
    if connection.status == DISABLED:
        raise Conflict("Connection is disconnected", code="CONNECTION_DISABLED")
    adapter = get_adapter(connection.provider)
    ctx = provider_context(connection)
    repo = RepoRef(str(data.get("external_id") or ""), data.get("path_with_namespace") or "")
    if not repo.external_id and not repo.path_with_namespace:
        raise ValidationFailed("external_id is required")
    try:
        meta = adapter.fetch_repository(ctx, repo)
    except CapabilityUnsupported as exc:
        raise Conflict(str(exc), code="CAPABILITY_MISSING", detail={"capability": exc.capability}) from None
    except TransportError:
        raise DomainError("Provider unreachable", code="PROVIDER_UNAVAILABLE", status_code=502) from None
    if not meta.get("ok"):
        raise NotFound("Repository not found at provider")
    commit = data.get("commit") or meta.get("head_commit") or ""
    items = [
        {
            "kind": "repository",
            "status": "observed",
            "commit": commit,
            "external_id": meta.get("external_id"),
            "path_with_namespace": meta.get("path_with_namespace"),
            "default_branch": meta.get("default_branch"),
        }
    ]
    uncertainties = []
    try:
        paths = (
            adapter.list_tree(
                ctx, RepoRef(meta.get("external_id") or repo.external_id, meta.get("path_with_namespace") or ""), commit
            )
            if commit
            else []
        )
    except (CapabilityUnsupported, TransportError):
        paths = []
        uncertainties.append("file tree unavailable")
    for path in [p for p in paths if p and _is_spec_path(p)][:200]:
        items.append({"kind": "spec_file", "status": "observed", "path": path, "commit": commit})
        items.append(
            {
                "kind": "package_proposal",
                "status": "proposed",
                "source_path": path,
                "commit": commit,
                "note": "Derived from existing code/spec; a proposal, not a retroactive business approval.",
            }
        )
    try:
        mrs = adapter.list_merge_requests(
            ctx, RepoRef(meta.get("external_id") or repo.external_id, meta.get("path_with_namespace") or ""), limit=10
        )
    except (CapabilityUnsupported, TransportError):
        mrs = []
        uncertainties.append("merge requests unavailable")
    for mr in mrs:
        items.append(
            {
                "kind": "merge_request",
                "status": "observed",
                "external_id": mr.mr_external_id,
                "title": mr.mr_title,
                "state": mr.mr_state,
                "head_sha": mr.head_sha,
                # Historical activity keeps its original date (J01).
                "occurred_at": mr.occurred_at.isoformat() if mr.occurred_at else None,
                "work_item_references": mr.correlation,
            }
        )
    if len(paths) >= 100:
        uncertainties.append("file tree may be truncated (first page only)")
    return {
        "connection_id": str(connection.id),
        "commit": commit,
        "items": items,
        "uncertainties": uncertainties,
        "writes_performed": False,
    }
