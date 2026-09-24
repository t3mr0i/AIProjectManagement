# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Write an integrity snapshot of native + extension rows (PF04, PF12).

Each row is reduced to a sha256 digest of its identity-relevant fields so that
restores/upgrades can be compared with tools/project-hub/verify_restore.py
without exporting content.
"""

import hashlib
import json

from django.core.management.base import BaseCommand

from plane.db.models import Cycle, Issue, Module, Page, Project, State, Workspace
from plane.package_flow import models as pf

TABLES = {
    "workspaces": (Workspace.all_objects.all(), ["id", "slug"]),
    "projects": (Project.all_objects.all(), ["id", "workspace_id", "identifier"]),
    "states": (State.all_objects.all(), ["id", "project_id", "group"]),
    "issues": (Issue.all_objects.all(), ["id", "project_id", "workspace_id", "sequence_id"]),
    "cycles": (Cycle.all_objects.all(), ["id", "project_id"]),
    "modules": (Module.all_objects.all(), ["id", "project_id"]),
    "pages": (Page.all_objects.all(), ["id", "workspace_id"]),
    "pf_profiles": (pf.PackageProfile.all_objects.all(), ["id", "issue_id", "approved_revision_id"]),
    "pf_revisions": (pf.PackageRevision.all_objects.all(), ["id", "issue_id", "number", "content_hash"]),
    "pf_approvals": (
        pf.ExecutionApproval.all_objects.all(),
        ["id", "issue_id", "revision_id", "revision_hash", "approved_by_id", "revoked_at"],
    ),
    "pf_deliveries": (pf.Delivery.all_objects.all(), ["id", "issue_id", "stage", "commit_sha", "environment"]),
    "pf_decisions": (pf.Decision.all_objects.all(), ["id", "issue_id", "status", "text"]),
    "pf_review_approvals": (pf.ReviewApproval.all_objects.all(), ["id", "issue_id", "head_sha", "kind"]),
}


def digest(values):
    return hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()[:16]


class Command(BaseCommand):
    help = "Write a content-free integrity snapshot for restore/upgrade verification"

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True)

    def handle(self, *args, **options):
        snapshot = {"tables": {}}
        for name, (qs, fields) in TABLES.items():
            # deleted_at is included so soft deletion also counts as a change.
            snapshot["tables"][name] = {str(row[0]): digest(row) for row in qs.values_list(*fields, "deleted_at")}
        with open(options["out"], "w") as fh:
            json.dump(snapshot, fh, indent=1)
        total = sum(len(v) for v in snapshot["tables"].values())
        self.stdout.write(f"snapshot written: {total} rows in {len(TABLES)} tables")
