# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Requirement tests not covered elsewhere: PF04, PF14/FR-B14, FR-I01, FR-E05."""

import importlib

import pytest
from django.db import migrations

from plane.package_flow.ai.context import assemble_context
from plane.package_flow.models import IntegrationConnection

from .pkg_support import Pkg


@pytest.mark.unit
def test_pf04_extension_migration_is_additive():
    """PF04 / FR-B04: the extension migration only creates pf_* tables/constraints; it never alters native tables."""
    module = importlib.import_module("plane.package_flow.migrations.0001_initial")
    allowed = (migrations.CreateModel, migrations.AddConstraint, migrations.AddField, migrations.AddIndex)
    for op in module.Migration.operations:
        assert isinstance(op, allowed), f"non-additive operation {type(op).__name__}"
        if isinstance(op, migrations.CreateModel):
            assert op.options.get("db_table", "").startswith("pf_"), op.name
    # Native app is only a dependency, never a migration target.
    assert all(
        dep[0] in ("db", "__setting__") or "AUTH_USER_MODEL" in str(dep) for dep in module.Migration.dependencies
    )


@pytest.mark.contract
class TestOneIssueOneNavigationTarget:
    def test_pf14_fr_b14_package_row_is_the_native_issue(self, world):
        """PF14 / FR-B14: package list and native issue API expose the same identity and project context."""
        pkg = Pkg(world)
        pkg.activate()
        rows = pkg.human.get(f"{pkg.base}/packages/?view=all").json()
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        row = next(r for r in rows if r["work_item_id"] == str(pkg.issue.id))
        assert row["project_id"] == str(pkg.project.id)
        assert row["sequence_id"] == pkg.issue.sequence_id
        native = pkg.human.get(
            f"/api/workspaces/{world.workspace.slug}/projects/{pkg.project.id}/issues/{pkg.issue.id}/"
        )
        assert native.status_code == 200, native.content
        assert native.json()["id"] == str(pkg.issue.id)
        assert native.json()["name"] == row["name"]
        # A normal issue without profile still works natively and is not listed as a package.
        plain = world.issue(pkg.project, name="Plain issue")
        listing = pkg.human.get(f"{pkg.base}/packages/?view=all").json()
        listing = listing.get("results", listing) if isinstance(listing, dict) else listing
        ids = {r["work_item_id"] for r in listing}
        assert str(plain.id) not in ids
        assert (
            pkg.human.get(
                f"/api/workspaces/{world.workspace.slug}/projects/{pkg.project.id}/issues/{plain.id}/"
            ).status_code
            == 200
        )


@pytest.mark.contract
def test_fr_i01_native_operation_without_external_tracker(world):
    """FR-I01: packages and roadmap work natively with no Jira/Linear/Azure Boards connection."""
    pkg = Pkg(world, package_type="analysis")
    assert not IntegrationConnection.objects.filter(
        workspace=world.workspace, provider__in=["jira", "linear", "azure_devops"]
    ).exists()
    pkg.make_ready()
    rev = pkg.revision()
    r = pkg.human.post(
        f"{pkg.wi}/execution-approvals",
        {
            "revision_id": rev["id"],
            "allowed_actions": ["edit_allowed_files"],
            "limits": {"max_seconds": 600, "max_spend_minor": 0, "currency": "EUR"},
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    status = pkg.human.get(f"{pkg.wi}/status").json()
    assert status["phase"] == "ready"
    roadmap = pkg.human.get(f"{world.ws_base()}/roadmap/")
    assert roadmap.status_code == 200, roadmap.content


@pytest.mark.unit
def test_fr_e05_selection_reference_detects_stale_version(world, human_client):
    """FR-E05: a selected message is passed with a stable versioned reference; an edited source is marked stale."""
    from plane.package_flow.models import Conversation, ConversationParticipant, Message, MessageVersion

    project = world.project()
    conv = Conversation.objects.create(workspace=world.workspace, project=project, kind="project", title="general")
    ConversationParticipant.objects.create(conversation=conv, member=world.owner)
    msg = Message.objects.create(conversation=conv, workspace=world.workspace, author=world.owner, body="Use CSV")
    MessageVersion.objects.create(message=msg, version=1, body="Use CSV")
    selection = [{"type": "message", "id": str(msg.id), "version": 1}]
    fresh = assemble_context(
        requester=world.owner, workspace_id=world.workspace.id, audience_ids=[world.owner.id], selection=selection
    )
    msg.body, msg.version = "Use XLSX", 2
    msg.save()
    MessageVersion.objects.create(message=msg, version=2, body="Use XLSX")
    stale = assemble_context(
        requester=world.owner, workspace_id=world.workspace.id, audience_ids=[world.owner.id], selection=selection
    )

    def entries(result):
        data = result if isinstance(result, dict) else getattr(result, "__dict__", {})
        return data.get("allowed") or data.get("visible") or []

    fresh_entry, stale_entry = entries(fresh)[0], entries(stale)[0]
    assert fresh_entry.get("stale") is False
    assert stale_entry.get("stale") is True
