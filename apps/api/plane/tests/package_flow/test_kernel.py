# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.urls import path
from rest_framework.response import Response

from plane.package_flow.capabilities import has_capability
from plane.package_flow.models import Capability
from plane.package_flow.views.base import PackageFlowBaseView


class WhoAmI(PackageFlowBaseView):
    def get(self, request, slug):
        self.get_workspace(slug)
        return Response({"kind": self.principal.kind, "via": self.principal.via})


urlpatterns = [path("whoami/<str:slug>/", WhoAmI.as_view())]


@pytest.mark.unit
@pytest.mark.urls("plane.tests.package_flow.test_kernel")
class TestPrincipal:
    def test_session_user_is_human(self, world, human_client):
        r = human_client(world.owner).get(f"/whoami/{world.workspace.slug}/")
        assert r.status_code == 200, r.content
        assert r.json()["kind"] == "human"

    def test_runner_token_is_agent(self, world, runner_client):
        _, token = world.runner(world.owner)
        r = runner_client(token).get(f"/whoami/{world.workspace.slug}/")
        assert r.status_code == 200, r.content
        assert r.json()["kind"] == "agent"

    def test_bot_session_is_agent(self, world, human_client):
        bot = world.member(is_bot=True)
        r = human_client(bot).get(f"/whoami/{world.workspace.slug}/")
        assert r.json()["kind"] == "agent"

    def test_non_member_gets_404(self, world, human_client):
        from plane.tests.package_flow.conftest import make_user

        r = human_client(make_user()).get(f"/whoami/{world.workspace.slug}/")
        assert r.status_code == 404


@pytest.mark.unit
class TestCapabilities:
    def test_native_role_does_not_grant_execution(self, world):
        p = world.project()
        assert has_capability(world.owner, world.workspace.id, p.id, Capability.PACKAGE_EDIT)
        assert not has_capability(world.owner, world.workspace.id, p.id, Capability.PACKAGE_APPROVE_EXECUTION)
        world.grant(world.owner, Capability.PACKAGE_APPROVE_EXECUTION, p)
        assert has_capability(world.owner, world.workspace.id, p.id, Capability.PACKAGE_APPROVE_EXECUTION)

    def test_membership_revocation_removes_grant(self, world):
        from plane.db.models import ProjectMember

        u = world.member()
        p = world.project(members=[(u, 15)])
        world.grant(u, Capability.RUN_START, p)
        assert has_capability(u, world.workspace.id, p.id, Capability.RUN_START)
        ProjectMember.objects.filter(project=p, member=u).update(is_active=False)
        assert not has_capability(u, world.workspace.id, p.id, Capability.RUN_START)
        assert not has_capability(u, world.workspace.id, p.id, Capability.PROJECT_READ)

    def test_guest_never_gets_execution_even_with_grant(self, world):
        g = world.member(role=5)
        p = world.project(members=[(g, 5)])
        world.grant(g, Capability.RUN_START, p)
        assert not has_capability(g, world.workspace.id, p.id, Capability.RUN_START)
        assert not has_capability(g, world.workspace.id, p.id, Capability.PACKAGE_EDIT)
        assert has_capability(g, world.workspace.id, p.id, Capability.PROJECT_READ)
