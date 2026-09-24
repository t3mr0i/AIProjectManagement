# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.package_flow.capabilities import has_capability
from plane.package_flow.models import AuditEntry, CapabilityGrant, ExtensionActivation

from .conftest import human_client_for, runner_client_for


@pytest.mark.unit
class TestActivation:
    def test_workspace_and_project_activation_audited(self, world):
        project = world.project()
        c = human_client_for(world.owner)
        r = c.get(f"{world.ws_base()}/activation/")
        assert r.status_code == 200 and r.json()["workspace_enabled"] is False
        r = c.put(f"{world.ws_base()}/activation/", {"is_enabled": True, "reason": "pilot"}, format="json")
        assert r.status_code == 200 and r.json()["workspace_enabled"] is True
        r = c.put(f"{world.base(project)}/activation/", {"is_enabled": False, "reason": "not yet"}, format="json")
        assert r.status_code == 200, r.content
        body = c.get(f"{world.ws_base()}/activation/").json()
        assert body["projects"] == [{"project_id": str(project.id), "is_enabled": False}]
        assert AuditEntry.objects.filter(action="extension.activation_changed").count() == 2
        assert c.put(f"{world.ws_base()}/activation/", {"is_enabled": "yes"}, format="json").status_code == 422

    def test_non_admin_and_agent_cannot_activate(self, world):
        member = world.member(role=15)
        r = human_client_for(member).put(f"{world.ws_base()}/activation/", {"is_enabled": True}, format="json")
        assert r.status_code == 403
        _, token = world.runner(world.owner)
        r = runner_client_for(token).put(f"{world.ws_base()}/activation/", {"is_enabled": True}, format="json")
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        assert not ExtensionActivation.objects.filter(is_enabled=True).exists()


@pytest.mark.unit
class TestGrants:
    def test_grant_and_revoke_capability(self, world):
        member = world.member(role=15)
        project = world.project(members=[(member, 15)])
        c = human_client_for(world.owner)
        body = {"member_id": str(member.id), "capability": "run.start", "project_id": str(project.id)}
        r = c.post(f"{world.ws_base()}/capability-grants/", body, format="json")
        assert r.status_code == 201, r.content
        assert has_capability(member, world.workspace.id, project.id, "run.start")
        assert c.post(f"{world.ws_base()}/capability-grants/", body, format="json").json()["code"] == "GRANT_EXISTS"
        assert len(c.get(f"{world.ws_base()}/capability-grants/").json()["results"]) == 1
        r = c.delete(f"{world.ws_base()}/capability-grants/{r.json()['id']}/")
        assert r.status_code == 204
        assert not has_capability(member, world.workspace.id, project.id, "run.start")
        actions = set(AuditEntry.objects.values_list("action", flat=True))
        assert {"capability.granted", "capability.revoked"} <= actions

    def test_grant_validation(self, world):
        c = human_client_for(world.owner)
        member = world.member()
        r = c.post(
            f"{world.ws_base()}/capability-grants/", {"member_id": str(member.id), "capability": "god"}, format="json"
        )
        assert r.status_code == 422
        from .conftest import make_user

        stranger = make_user()
        r = c.post(
            f"{world.ws_base()}/capability-grants/",
            {"member_id": str(stranger.id), "capability": "run.start"},
            format="json",
        )
        assert r.status_code == 404

    def test_member_cannot_grant_itself(self, world):
        member = world.member(role=15)
        r = human_client_for(member).post(
            f"{world.ws_base()}/capability-grants/",
            {"member_id": str(member.id), "capability": "package.approve_execution"},
            format="json",
        )
        assert r.status_code == 403
        assert not CapabilityGrant.objects.exists()


@pytest.mark.unit
class TestCapabilitiesMeAndAudit:
    def test_capabilities_me(self, world):
        world.enable()
        project = world.project()
        world.grant(world.owner, "run.start", project)
        c = human_client_for(world.owner)
        body = c.get(f"{world.ws_base()}/capabilities/me/?project_id={project.id}").json()
        assert body["principal_kind"] == "human" and body["extension_enabled"] is True
        assert {"project.read", "package.edit", "run.start", "workspace.admin"} <= set(body["capabilities"])
        assert "package.approve_execution" not in body["capabilities"]
        other_ws_project = world.project()
        guest = world.member(role=5)
        r = human_client_for(guest).get(f"{world.ws_base()}/capabilities/me/?project_id={other_ws_project.id}")
        assert r.status_code == 404

    def test_audit_admin_only(self, world):
        c = human_client_for(world.owner)
        c.put(f"{world.ws_base()}/activation/", {"is_enabled": True}, format="json")
        r = c.get(f"{world.ws_base()}/audit/?action=extension.activation_changed")
        assert r.status_code == 200 and len(r.json()["results"]) == 1
        member = world.member(role=15)
        assert human_client_for(member).get(f"{world.ws_base()}/audit/").status_code == 403
