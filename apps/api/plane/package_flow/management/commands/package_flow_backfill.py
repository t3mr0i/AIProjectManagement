# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Idempotent, batched extension backfill (FR-B04, MIGRATION §2).

* Ensures one *disabled* workspace-level ``ExtensionActivation`` row per workspace.
* ``--activate-workspace <slug>`` explicitly enables one workspace (audited).
* Never converts issues to packages; native rows are only read.
* Re-running is a no-op.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from plane.db.models import Workspace
from plane.package_flow.models import ExtensionActivation
from plane.package_flow.services import events


class Command(BaseCommand):
    help = "Create missing (disabled) Project Hub activation rows; optionally activate one workspace."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--activate-workspace", dest="activate", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        stats = run_backfill(
            batch_size=options["batch_size"], activate_slug=options["activate"], dry_run=options["dry_run"]
        )
        for key, value in stats.items():
            self.stdout.write(f"{key}: {value}")


def run_backfill(batch_size=500, activate_slug=None, dry_run=False):
    batch_size = max(1, int(batch_size))
    stats = {
        "workspaces_scanned": 0,
        "activation_rows_created": 0,
        "already_present": 0,
        "activated": 0,
        "packages_created": 0,
    }
    last_id = None
    while True:
        qs = Workspace.objects.filter(deleted_at__isnull=True).order_by("id")
        if last_id is not None:
            qs = qs.filter(id__gt=last_id)
        batch = list(qs.values_list("id", flat=True)[:batch_size])
        if not batch:
            break
        last_id = batch[-1]
        stats["workspaces_scanned"] += len(batch)
        existing = set(
            ExtensionActivation.objects.filter(
                workspace_id__in=batch, project__isnull=True, deleted_at__isnull=True
            ).values_list("workspace_id", flat=True)
        )
        missing = [ws_id for ws_id in batch if ws_id not in existing]
        stats["already_present"] += len(existing)
        if missing and not dry_run:
            with transaction.atomic():
                created = ExtensionActivation.objects.bulk_create(
                    [
                        ExtensionActivation(workspace_id=ws_id, project=None, is_enabled=False, reason="backfill")
                        for ws_id in missing
                    ],
                    ignore_conflicts=True,
                )
            stats["activation_rows_created"] += len(created)
        elif missing:
            stats["activation_rows_created"] += len(missing)

    if activate_slug:
        workspace = Workspace.objects.filter(slug=activate_slug, deleted_at__isnull=True).first()
        if workspace is None:
            raise CommandError(f"Workspace '{activate_slug}' not found")
        row = ExtensionActivation.objects.filter(
            workspace=workspace, project__isnull=True, deleted_at__isnull=True
        ).first()
        if row is not None and not row.is_enabled and not dry_run:
            with transaction.atomic():
                ExtensionActivation.objects.filter(pk=row.pk).update(is_enabled=True, reason="backfill activation")
                events.audit(
                    workspace_id=workspace.id,
                    actor=None,
                    actor_kind="system",
                    action="extension.activation_changed",
                    target_type="extension_activation",
                    target_id=row.id,
                    detail={"is_enabled": True, "previous": False, "reason": "backfill activation"},
                )
            stats["activated"] = 1
    return stats
