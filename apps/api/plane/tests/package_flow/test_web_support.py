# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Read endpoints added for the web UI: ``GET P/uploads/``, ``GET P/uploads/candidates``,
``GET P/work-items/{id}/claims`` (ACL, scan/format state, lease/heartbeat projection)."""

import pytest
from django.utils import timezone

from plane.db.models import FileAsset
from plane.package_flow.models import Claim, ExtensionActivation
from plane.package_flow.services import knowledge

from .conftest import human_client_for
from .pkg_support import Pkg


def _asset(world, project, name, issue=None, entity_type="ISSUE_ATTACHMENT"):
    return FileAsset.objects.create(
        attributes={"name": name, "type": "text/plain"},
        asset=f"u/{name}",
        workspace=world.workspace,
        project=project,
        issue=issue,
        entity_type=entity_type,
    )


def _register(client, world, project, asset, monkeypatch, content):
    monkeypatch.setattr(knowledge, "read_asset_bytes", lambda a, limit=None: content)
    r = client.post(f"{world.base(project)}/uploads/{asset.id}/register", {"filename": asset.attributes["name"]},
                    format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.unit
class TestUploadList:
    def setup_project(self, world):
        alice, outsider = world.member(), world.member()
        project = world.project(identifier="UPL", members=[(alice, 15)])
        world.enable(project)
        return project, alice, outsider

    def test_lists_registered_uploads_with_scan_and_format(self, world, monkeypatch):
        project, alice, _ = self.setup_project(world)
        client = human_client_for(alice)
        clean = _register(client, world, project, _asset(world, project, "notes.md"), monkeypatch, b"# hello")
        bad = _register(
            client, world, project, _asset(world, project, "tool.exe"), monkeypatch, b"MZ\x90\x00binary"
        )
        r = client.get(f"{world.base(project)}/uploads/")
        assert r.status_code == 200, r.content
        rows = {row["id"]: row for row in r.json()["results"]}
        assert rows[clean["id"]]["scan_status"] == "clean"
        assert rows[clean["id"]]["format_support"] == "native_edit"
        assert rows[clean["id"]]["name"] == "notes.md"
        # Quarantined files are listed and clearly marked, without extracted text.
        assert rows[bad["id"]]["scan_status"] == "quarantined"
        assert rows[bad["id"]]["has_extracted_text"] is False
        only_bad = client.get(f"{world.base(project)}/uploads/?scan_status=quarantined").json()["results"]
        assert [row["id"] for row in only_bad] == [bad["id"]]

    def test_non_members_get_404_and_history_readable_when_disabled(self, world, monkeypatch):
        project, alice, outsider = self.setup_project(world)
        _register(human_client_for(alice), world, project, _asset(world, project, "a.txt"), monkeypatch, b"hi")
        assert human_client_for(outsider).get(f"{world.base(project)}/uploads/").status_code == 404
        ExtensionActivation.objects.filter(workspace=world.workspace, project=project).update(is_enabled=False)
        assert human_client_for(alice).get(f"{world.base(project)}/uploads/").status_code == 200

    def test_candidates_are_unregistered_native_assets(self, world, monkeypatch):
        project, alice, _ = self.setup_project(world)
        client = human_client_for(alice)
        world.grant(alice, "package.edit", project)
        issue = world.issue(project)
        registered = _asset(world, project, "done.txt", issue=issue)
        pending = _asset(world, project, "pending.txt", issue=issue)
        _asset(world, project, "avatar.png", entity_type="USER_AVATAR")
        _register(client, world, project, registered, monkeypatch, b"x")
        r = client.get(f"{world.base(project)}/uploads/candidates")
        assert r.status_code == 200, r.content
        ids = [c["asset_id"] for c in r.json()["results"]]
        assert ids == [str(pending.id)]
        assert r.json()["results"][0]["name"] == "pending.txt"
        by_issue = client.get(f"{world.base(project)}/uploads/candidates?issue_id={issue.id}").json()["results"]
        assert [c["asset_id"] for c in by_issue] == [str(pending.id)]


@pytest.mark.unit
class TestClaimList:
    def test_lists_claims_with_heartbeat_and_holder(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        Claim.objects.filter(id=claim["id"]).update(last_heartbeat_at=timezone.now())
        r = pkg.human.get(f"{pkg.wi}/claims")
        assert r.status_code == 200, r.content
        rows = r.json()["results"]
        assert [row["id"] for row in rows] == [claim["id"]]
        row = rows[0]
        assert row["status"] == "active" and row["runner_name"] == "runner"
        assert row["last_heartbeat_at"] is not None and row["lease_expires_at"]
        assert row["holder_id"] == str(world.owner.id)
        assert pkg.human.get(f"{pkg.wi}/claims?status=released").json()["results"] == []

    def test_claims_require_project_membership(self, world):
        pkg = Pkg(world)
        outsider = world.member()
        assert human_client_for(outsider).get(f"{pkg.wi}/claims").status_code == 404


@pytest.mark.unit
def test_cors_preflight_allows_idempotency_key(world):
    """The web app sends ``Idempotency-Key`` on writes; a split-origin preflight must allow it."""
    from rest_framework.test import APIClient

    project = world.project()
    response = APIClient().options(
        f"{world.base(project)}/work-items/{project.id}/profile/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type, idempotency-key",
    )
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "idempotency-key" in allowed
