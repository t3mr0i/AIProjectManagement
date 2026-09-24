# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Helpers shared by the package/approval/execution tests (real native rows, real endpoints)."""

from uuid import uuid4

from plane.package_flow.models import Capability, IntegrationConnection, RepositoryBinding

from .conftest import human_client_for, runner_client_for

COMMIT = "a" * 40

READY_PROFILE = {
    "intent": "Avoid manual re-assembly of the filtered selection",
    "outcome": "Filtered records can be exported as CSV",
    "criteria": [{"text": "Export only contains permitted, filtered rows", "verification": "integration test"}],
    "scope": {"in_scope": ["CSV export of the list view"], "touches": ["export"]},
}


class Pkg:
    """One enabled project with an owner that holds all execution capabilities."""

    def __init__(self, world, *, package_type="code"):
        self.world = world
        self.project = world.project()
        world.enable(self.project)
        for cap in (
            Capability.PACKAGE_APPROVE_EXECUTION,
            Capability.RUN_START,
            Capability.RUN_CANCEL,
            Capability.REVIEW_ACCEPT_OUTCOME,
        ):
            world.grant(world.owner, cap, self.project)
        self.issue = world.issue(self.project, name="Export filtered data", description_html="<p>Export</p>")
        self.human = human_client_for(world.owner)
        self.base = world.base(self.project)
        self.wi = f"{self.base}/work-items/{self.issue.id}"
        self.package_type = package_type
        self.binding = make_binding(world, self.project)

    def activate(self):
        r = self.human.post(f"{self.wi}/profile", {"package_type": self.package_type}, format="json")
        assert r.status_code in (200, 201), r.content
        return r.json()

    def make_ready(self, **extra):
        self.activate()
        body = {**READY_PROFILE, **extra}
        r = self.human.patch(f"{self.wi}/profile", body, format="json")
        assert r.status_code == 200, r.content
        return r.json()

    def revision(self):
        r = self.human.post(f"{self.wi}/revisions", {}, format="json")
        assert r.status_code in (200, 201), r.content
        return r.json()

    def approval_body(self, revision_id, **extra):
        body = {
            "revision_id": revision_id,
            "repository_scope": [
                {
                    "binding_id": str(self.binding.id),
                    "base_commit": COMMIT,
                    "target_branch": "main",
                    "allowed_paths": ["src/export/**", "tests/export/**"],
                }
            ],
            "allowed_actions": ["prepare_worktree", "edit_allowed_files", "create_commit", "push_work_branch"],
            "limits": {"max_seconds": 3600, "max_spend_minor": 1000, "currency": "EUR"},
        }
        body.update(extra)
        return body

    def approve(self, **extra):
        self.make_ready()
        rev = self.revision()
        r = self.human.post(f"{self.wi}/execution-approvals", self.approval_body(rev["id"], **extra), format="json")
        assert r.status_code == 201, r.content
        return r.json()

    def runner(self, owner=None, name="runner"):
        runner, token = self.world.runner(owner or self.world.owner, name=name)
        return runner, runner_client_for(token)

    def claim(self, client, **body):
        return client.post(f"{self.wi}/claims", body, format="json")

    def start(self, client, approval_id, claim_id, mode="agent"):
        return client.post(
            f"{self.wi}/runs", {"approval_id": approval_id, "claim_id": claim_id, "mode": mode}, format="json"
        )

    def running(self):
        """Approved package with a runner-held claim and a started run."""
        approval = self.approve()
        runner, rc = self.runner()
        claim = self.claim(rc).json()
        r = self.start(rc, approval["id"], claim["id"])
        assert r.status_code == 201, r.content
        body = r.json()
        return approval, rc, claim, body["run"], body["run_token"]


def make_binding(world, project):
    conn = IntegrationConnection.objects.create(
        workspace=world.workspace, provider="gitlab", instance_url="https://gitlab.example.test"
    )
    return RepositoryBinding.objects.create(
        workspace=world.workspace,
        project=project,
        connection=conn,
        external_id=uuid4().hex[:8],
        path_with_namespace="group/repo",
    )


def action(rc, run_id, token, fencing, name, **detail):
    return rc.post(
        f"/api/package-flow/runs/{run_id}/actions",
        {"action": name, "fencing_token": fencing, "detail": detail},
        format="json",
        HTTP_X_RUN_TOKEN=token,
    )
