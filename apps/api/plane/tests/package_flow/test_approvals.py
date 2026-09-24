# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.db.models import Issue
from plane.package_flow.models import AuditEntry, DomainEvent, ExecutionApproval, ExecutionRun, PackageProfile

from .conftest import human_client_for
from .pkg_support import Pkg


@pytest.mark.unit
class TestApprovals:
    def test_human_approval_sets_approved_revision_and_audits(self, world):
        pkg = Pkg(world)
        approval = pkg.approve()
        assert approval["state"] == "valid"
        assert approval["policy_version"] == "pf-policy-1"
        profile = PackageProfile.objects.get(issue=pkg.issue)
        assert str(profile.approved_revision_id) == approval["revision_id"]
        ev = DomainEvent.objects.get(event_type="package.execution.approved", issue_id=pkg.issue.id)
        assert ev.actor_kind == "human" and ev.actor_id == str(world.owner.id)
        assert AuditEntry.objects.filter(action="execution.approved", target_id=approval["id"]).exists()
        obj = ExecutionApproval.objects.get(id=approval["id"])
        assert obj.expires_at > timezone.now() + timedelta(hours=71)
        assert len(obj.native_source_hash) == 64

    def test_ac03_agent_cannot_approve(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        _, rc = pkg.runner()  # owner holds package.approve_execution, but authenticates as runner
        body = pkg.approval_body(rev["id"], kind="human", actor_kind="human", approved_by={"kind": "human"})
        r = rc.post(f"{pkg.wi}/execution-approvals", body, format="json")
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        # Bot users are agents even with a session.
        bot = world.member(is_bot=True)
        world.add_project_member(pkg.project, bot, 15)
        world.grant(bot, "package.approve_execution", pkg.project)
        r = human_client_for(bot).post(f"{pkg.wi}/execution-approvals", body, format="json")
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        assert not ExecutionApproval.objects.exists()

    def test_member_without_capability_cannot_approve(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        member = world.member()
        world.add_project_member(pkg.project, member, 15)
        r = human_client_for(member).post(f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"]), format="json")
        assert r.status_code == 403 and r.json()["code"] == "PERMISSION_DENIED"

    def test_stale_revision_rejected(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        r1 = pkg.revision()
        pkg.human.patch(f"{pkg.wi}/profile", {"outcome": "changed"}, format="json")
        pkg.revision()
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", pkg.approval_body(r1["id"]), format="json")
        assert r.status_code == 409 and r.json()["code"] == "REVISION_STALE"

    def test_native_description_change_makes_revision_stale(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        Issue.all_objects.filter(id=pkg.issue.id).update(description_html="<p>new intent</p>")
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"]), format="json")
        assert r.status_code == 409 and r.json()["code"] == "REVISION_STALE"

    def test_ac27_merge_not_an_allowed_action(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        body = pkg.approval_body(rev["id"], allowed_actions=["create_commit", "merge"])
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", body, format="json")
        assert r.status_code == 422 and r.json()["code"] == "ACTION_NOT_ALLOWED"

    def test_code_package_requires_repository_scope(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        r = pkg.human.post(
            f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"], repository_scope=[]), format="json"
        )
        assert r.status_code == 422

    def test_invalid_base_commit_rejected(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        body = pkg.approval_body(rev["id"])
        body["repository_scope"][0]["base_commit"] = "main"
        assert pkg.human.post(f"{pkg.wi}/execution-approvals", body, format="json").status_code == 422

    def test_revoke_returns_package_to_draft_and_cancels_runs(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = pkg.human.post(
            f"{pkg.wi}/execution-approvals/{approval['id']}/revoke", {"reason": "scope unclear"}, format="json"
        )
        assert r.status_code == 200, r.content
        assert r.json()["state"] == "revoked"
        assert ExecutionRun.objects.get(id=run["id"]).status == "cancelled"
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert s["lifecycle"] == "draft"
        assert AuditEntry.objects.filter(action="execution.revoked").exists()
        # A new claim is not possible with the revoked approval.
        r = pkg.claim(rc, approval_id=approval["id"])
        assert r.status_code == 409 and r.json()["code"] == "APPROVAL_REVOKED"

    def test_expired_approval_cannot_start(self, world):
        pkg = Pkg(world)
        approval = pkg.approve()
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        ExecutionApproval.objects.filter(id=approval["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        r = pkg.start(rc, approval["id"], claim["id"])
        assert r.status_code == 409 and r.json()["code"] == "APPROVAL_EXPIRED"

    def test_ac04_new_draft_revision_does_not_replace_running_revision(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        pkg.human.patch(f"{pkg.wi}/profile", {"outcome": "much bigger outcome"}, format="json")
        new_rev = pkg.revision()
        assert new_rev["number"] == 2
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert str(run_obj.revision_id) == approval["revision_id"]
        manifest = rc.get(f"/api/package-flow/runs/{run['id']}/manifest", HTTP_X_RUN_TOKEN=token).json()["manifest"]
        assert manifest["revisionId"] == approval["revision_id"]
        prof = pkg.human.get(f"{pkg.wi}/profile").json()
        assert prof["working_revision_id"] == new_rev["id"]
        assert prof["approved_revision_id"] == approval["revision_id"]

    def test_approval_idempotency(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        body = pkg.approval_body(rev["id"])
        r1 = pkg.human.post(f"{pkg.wi}/execution-approvals", body, format="json", HTTP_IDEMPOTENCY_KEY="a1")
        r2 = pkg.human.post(f"{pkg.wi}/execution-approvals", body, format="json", HTTP_IDEMPOTENCY_KEY="a1")
        assert r1.json()["id"] == r2.json()["id"]
        assert ExecutionApproval.objects.count() == 1
