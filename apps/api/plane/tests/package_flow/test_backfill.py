# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from io import StringIO

import pytest
from django.core.management import call_command

from plane.db.models import Issue, Workspace
from plane.package_flow.capabilities import is_extension_enabled
from plane.package_flow.models import ExtensionActivation, PackageProfile

from .conftest import World


def _run(*args):
    out = StringIO()
    call_command("package_flow_backfill", *args, stdout=out)
    return dict(line.split(": ") for line in out.getvalue().strip().splitlines())


@pytest.mark.unit
class TestBackfill:
    def test_fr_b04_backfill_idempotent_and_disabled(self, world):
        project = world.project()
        issue = world.issue(project)
        World()
        World()
        before = list(Issue.all_objects.values_list("id", "name", "project_id").order_by("id"))
        stats = _run("--batch-size", "1")
        n = Workspace.objects.count()
        assert int(stats["workspaces_scanned"]) == n
        assert int(stats["activation_rows_created"]) == n
        assert int(stats["packages_created"]) == 0
        assert ExtensionActivation.objects.filter(project__isnull=True, is_enabled=False).count() == n
        # Rerun is a no-op.
        stats = _run()
        assert int(stats["activation_rows_created"]) == 0 and int(stats["already_present"]) == n
        assert ExtensionActivation.objects.count() == n
        # Native rows untouched, no issue converted.
        assert list(Issue.all_objects.values_list("id", "name", "project_id").order_by("id")) == before
        assert not PackageProfile.objects.exists()
        assert not is_extension_enabled(world.workspace.id, project.id)
        assert issue.id  # native issue still usable

    def test_activate_workspace(self, world):
        stats = _run("--activate-workspace", world.workspace.slug)
        assert int(stats["activated"]) == 1
        assert is_extension_enabled(world.workspace.id)
        assert int(_run("--activate-workspace", world.workspace.slug)["activated"]) == 0

    def test_dry_run_writes_nothing(self, world):
        stats = _run("--dry-run")
        assert int(stats["activation_rows_created"]) == 1
        assert not ExtensionActivation.objects.exists()
