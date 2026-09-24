# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery tasks of the package-flow extension (discovered by ``app.autodiscover_tasks``).

Tasks are thin wrappers around idempotent service functions so a retried or
duplicated task never duplicates business effects (INV-07).
"""

from celery import shared_task


@shared_task(name="plane.package_flow.tasks.process_inbound_event", bind=True, max_retries=5, default_retry_delay=30)
def process_inbound_event(self, event_id):
    from plane.package_flow.services.integrations import process_inbound_event as process

    status = process(event_id)
    return status


@shared_task(name="plane.package_flow.tasks.reconcile_connection")
def reconcile_connection(connection_id):
    from plane.package_flow.services.integrations import reconcile_connection as reconcile

    return reconcile(connection_id)


@shared_task(name="plane.package_flow.tasks.reconcile_all_connections")
def reconcile_all_connections():
    """Periodic safety net: replay backlog and poll providers for every active connection."""
    from plane.package_flow.models import IntegrationConnection
    from plane.package_flow.services.integrations import reconcile_connection as reconcile

    results = {}
    for connection_id in (
        IntegrationConnection.objects.filter(deleted_at__isnull=True)
        .exclude(status=IntegrationConnection.Status.DISABLED)
        .values_list("id", flat=True)
    ):
        try:
            results[str(connection_id)] = reconcile(connection_id).get("status")
        except Exception as exc:  # noqa: BLE001 - one bad connection must not stop the sweep
            results[str(connection_id)] = f"error:{type(exc).__name__}"
    return results


@shared_task(name="plane.package_flow.tasks.push_external_fields")
def push_external_fields(link_id, op_id):
    """Bounded outbound tracker write (I12); idempotent per recorded op id."""
    from plane.package_flow.services.integrations import execute_push

    return execute_push(link_id, op_id)


@shared_task(name="plane.package_flow.tasks.expire_leases")
def expire_leases():
    """Periodic lease expiry for runner claims (FR-G04)."""
    from plane.package_flow.services.execution import expire_leases as expire

    result = expire()
    return result if isinstance(result, (int, str, list, dict, type(None))) else str(result)
