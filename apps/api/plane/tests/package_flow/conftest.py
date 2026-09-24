# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared fixtures for Project Hub package-flow tests.

Uses real native Plane rows (Workspace, Project, members, State, Issue) —
never admin shortcuts (I01 acceptance). ``human_client`` logs in through the
Django session so the principal resolves as *human*; ``agent_client`` uses a
runner token so it resolves as *agent*.
"""

import secrets
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import Issue, Project, ProjectMember, State, User, Workspace, WorkspaceMember
from plane.package_flow.models import Capability, CapabilityGrant, ExtensionActivation, RunnerProfile
from plane.package_flow.principal import hash_token


def make_user(email=None, is_bot=False):
    user = User.objects.create(
        email=email or f"{uuid4().hex[:10]}@example.test",
        username=uuid4().hex[:12],
        first_name="Test",
        last_name="User",
        is_bot=is_bot,
    )
    user.set_password("pw-" + uuid4().hex)
    user.save()
    return user


class World:
    """Tiny builder for native Plane test data."""

    def __init__(self):
        self.owner = make_user()
        self.workspace = Workspace.objects.create(name="WS", slug=f"ws-{uuid4().hex[:8]}", owner=self.owner)
        WorkspaceMember.objects.create(workspace=self.workspace, member=self.owner, role=20)

    def project(self, name="Project", identifier=None, members=()):
        project = Project.objects.create(
            name=f"{name} {uuid4().hex[:4]}",
            identifier=identifier or uuid4().hex[:5].upper(),
            workspace=self.workspace,
            created_by=self.owner,
        )
        ProjectMember.objects.create(project=project, workspace=self.workspace, member=self.owner, role=20)
        for user, role in members:
            self.add_project_member(project, user, role)
        return project

    def member(self, role=15, email=None, is_bot=False):
        user = make_user(email=email, is_bot=is_bot)
        WorkspaceMember.objects.create(workspace=self.workspace, member=user, role=role)
        return user

    def add_project_member(self, project, user, role=15):
        if not WorkspaceMember.objects.filter(workspace=self.workspace, member=user).exists():
            WorkspaceMember.objects.create(workspace=self.workspace, member=user, role=role)
        return ProjectMember.objects.create(project=project, workspace=self.workspace, member=user, role=role)

    def state(self, project, name="Todo", group="unstarted"):
        return State.objects.create(name=name, group=group, project=project, workspace=self.workspace)

    def issue(self, project, name="Work item", is_draft=False, state=None, description_html="<p></p>"):
        state = state or self.state(project, name=f"S {uuid4().hex[:4]}")
        return Issue.objects.create(
            name=name,
            project=project,
            workspace=self.workspace,
            state=state,
            is_draft=is_draft,
            description_html=description_html,
        )

    def grant(self, user, capability, project=None):
        return CapabilityGrant.objects.create(
            workspace=self.workspace, project=project, member=user, capability=capability
        )

    def grant_all(self, user, project=None):
        for cap in Capability:
            if cap not in (Capability.WORKSPACE_ADMIN,):
                self.grant(user, cap.value, project)

    def enable(self, project=None):
        ExtensionActivation.objects.update_or_create(
            workspace=self.workspace, project=None, defaults={"is_enabled": True}
        )
        if project is not None:
            ExtensionActivation.objects.update_or_create(
                workspace=self.workspace, project=project, defaults={"is_enabled": True}
            )

    def runner(self, owner, name="runner"):
        token = "rt_" + secrets.token_urlsafe(24)
        profile = RunnerProfile.objects.create(
            workspace=self.workspace,
            name=name,
            owner=owner,
            token_hash=hash_token(token),
            token_prefix=token[:10],
        )
        return profile, token

    def base(self, project):
        return f"/api/workspaces/{self.workspace.slug}/projects/{project.id}/package-flow"

    def ws_base(self):
        return f"/api/workspaces/{self.workspace.slug}/package-flow"


@pytest.fixture
def world(db):
    return World()


def human_client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def runner_client_for(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Runner {token}")
    return client


@pytest.fixture
def human_client():
    return human_client_for


@pytest.fixture
def runner_client():
    return runner_client_for
