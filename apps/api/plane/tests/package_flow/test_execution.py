# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from plane.package_flow.models import (
    CapabilityGrant,
    Claim,
    Evidence,
    ExecutionApproval,
    ExecutionRun,
    FencingCounter,
    RunAction,
    RunnerProfile,
)
from plane.package_flow.principal import AGENT, Principal, hash_token
from plane.package_flow.services import execution as ex

from .conftest import human_client_for, runner_client_for
from .pkg_support import Pkg, action


@pytest.mark.unit
class TestRunners:
    def test_register_runner_token_shown_once_and_hashed(self, world):
        world.enable()
        c = human_client_for(world.owner)
        r = c.post(f"{world.ws_base()}/runners/", {"name": "laptop", "kind": "local"}, format="json")
        assert r.status_code == 201, r.content
        token = r.json()["token"]
        runner = RunnerProfile.objects.get(id=r.json()["id"])
        assert runner.token_hash == hash_token(token) and token not in runner.token_hash
        listing = c.get(f"{world.ws_base()}/runners/").json()["results"]
        assert "token" not in listing[0]
        # Token authenticates as agent.
        who = runner_client_for(token).get(f"{world.ws_base()}/capabilities/me/").json()
        assert who["principal_kind"] == "agent"
        assert "package.approve_execution" not in who["capabilities"]

    def test_runner_cannot_register_runner(self, world):
        world.enable()
        _, token = world.runner(world.owner)
        r = runner_client_for(token).post(f"{world.ws_base()}/runners/", {"name": "x"}, format="json")
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"

    def test_deactivated_runner_is_rejected(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        runner_id = Claim.objects.get(id=claim["id"]).runner_id
        r = pkg.human.delete(f"{world.ws_base()}/runners/{runner_id}/")
        assert r.status_code == 204
        assert Claim.objects.get(id=claim["id"]).status == "revoked"
        assert ExecutionRun.objects.get(id=run["id"]).status == "cancelled"
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        assert r.status_code in (401, 403)


@pytest.mark.unit
class TestClaims:
    def test_ac05_second_exclusive_claim_conflicts(self, world):
        pkg = Pkg(world)
        pkg.approve()
        _, rc1 = pkg.runner(name="A")
        _, rc2 = pkg.runner(name="B")
        r1 = pkg.claim(rc1)
        r2 = pkg.claim(rc2)
        assert r1.status_code == 201, r1.content
        assert r2.status_code == 409 and r2.json()["code"] == "CLAIM_HELD"
        holder = r2.json()["detail"]["holder"]
        assert holder["runner_name"] == "A" and holder["claim_id"] == r1.json()["id"]
        assert Claim.objects.filter(status="active").count() == 1

    def test_collaborative_claims_allowed(self, world):
        pkg = Pkg(world)
        pkg.approve()
        _, rc1 = pkg.runner()
        _, rc2 = pkg.runner()
        assert pkg.claim(rc1, exclusive=False).status_code == 201
        assert pkg.claim(rc2, exclusive=False).status_code == 201

    def test_ac06_stale_fencing_token_rejected(self, world):
        pkg = Pkg(world)
        approval, rc_a, claim_a, run_a, token_a = pkg.running()
        # Runner A's lease expires; runner B takes over with a newer fencing token.
        Claim.objects.filter(id=claim_a["id"]).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        _, rc_b = pkg.runner(name="B")
        r = pkg.claim(rc_b)
        assert r.status_code == 201, r.content
        claim_b = r.json()
        assert claim_b["fencing_token"] > claim_a["fencing_token"]
        r = action(rc_a, run_a["id"], token_a, claim_a["fencing_token"], "push_work_branch")
        assert r.status_code == 409 and r.json()["code"] == "STALE_FENCING_TOKEN"
        r = rc_a.post(
            f"/api/package-flow/claims/{claim_a['id']}/heartbeat",
            {"fencing_token": claim_a["fencing_token"]},
            format="json",
        )
        assert r.status_code == 409 and r.json()["code"] == "STALE_FENCING_TOKEN"
        rejected = RunAction.objects.filter(run_id=run_a["id"], accepted=False)
        assert rejected.exists()

    def test_heartbeat_and_release(self, world):
        pkg = Pkg(world)
        pkg.approve()
        _, rc = pkg.runner()
        claim = pkg.claim(rc, lease_seconds=60).json()
        before = Claim.objects.get(id=claim["id"]).lease_expires_at
        r = rc.post(
            f"/api/package-flow/claims/{claim['id']}/heartbeat",
            {"fencing_token": claim["fencing_token"], "lease_seconds": 600},
            format="json",
        )
        assert r.status_code == 200, r.content
        assert Claim.objects.get(id=claim["id"]).lease_expires_at > before
        r = rc.post(f"/api/package-flow/claims/{claim['id']}/heartbeat", {"fencing_token": 999}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "STALE_FENCING_TOKEN"
        r = rc.post(
            f"/api/package-flow/claims/{claim['id']}/release", {"fencing_token": claim["fencing_token"]}, format="json"
        )
        assert r.status_code == 200 and r.json()["status"] == "released"
        assert pkg.claim(rc).status_code == 201

    def test_other_runner_cannot_touch_claim(self, world):
        pkg = Pkg(world)
        pkg.approve()
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        _, rc2 = pkg.runner()
        r = rc2.post(
            f"/api/package-flow/claims/{claim['id']}/release", {"fencing_token": claim["fencing_token"]}, format="json"
        )
        assert r.status_code == 404

    def test_expire_leases_command(self, world):
        from django.core.management import call_command

        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        Claim.objects.filter(id=claim["id"]).update(lease_expires_at=timezone.now() - timedelta(seconds=5))
        call_command("package_flow_expire_leases")
        assert Claim.objects.get(id=claim["id"]).status == "expired"
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert (run_obj.status, run_obj.pause_reason) == ("waiting", "lease_expired")

    def test_runner_bound_approval(self, world):
        pkg = Pkg(world)
        bound, _ = pkg.runner(name="bound")
        pkg.approve(runner_profile_id=str(bound.id))
        _, other = pkg.runner(name="other")
        r = pkg.claim(other)
        assert r.status_code == 403 and r.json()["code"] == "RUNNER_NOT_ALLOWED"


@pytest.mark.django_db(transaction=True)
def test_ac05_concurrent_exclusive_claims():
    from .conftest import World

    world = World()
    pkg = Pkg(world)
    pkg.approve()
    runners = [pkg.runner(name=f"r{i}")[0] for i in range(2)]
    results, barrier = [], threading.Barrier(2)

    def attempt(runner):
        try:
            barrier.wait()
            principal = Principal(user=runner.owner, kind=AGENT, runner=runner, via="runner")
            from plane.db.models import Issue

            issue = Issue.all_objects.select_related("project").get(id=pkg.issue.id)
            try:
                results.append(("ok", ex.create_claim(issue, principal, {}).fencing_token))
            except Exception as exc:  # noqa: BLE001
                results.append(("err", getattr(exc, "code", repr(exc))))
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(r,)) for r in runners]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r[0] for r in results) == ["err", "ok"], results
    assert [r[1] for r in results if r[0] == "err"] == ["CLAIM_HELD"]
    assert Claim.objects.filter(status="active", exclusive=True).count() == 1
    assert FencingCounter.objects.get().value >= 1


@pytest.mark.unit
class TestRuns:
    def test_run_start_returns_immutable_manifest(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        assert token.startswith("prt_")
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert run_obj.run_token_hash == hash_token(token)
        r = rc.get(f"/api/package-flow/runs/{run['id']}/manifest", HTTP_X_RUN_TOKEN=token)
        assert r.status_code == 200, r.content
        manifest = r.json()["manifest"]
        assert manifest["workItemId"] == str(pkg.issue.id)
        assert manifest["workspaceId"] == str(world.workspace.id)
        assert manifest["projectId"] == str(pkg.project.id)
        assert manifest["approvalId"] == approval["id"]
        assert manifest["revisionHash"] == approval["revision_hash"]
        assert manifest["allowedActions"] == approval["allowed_actions"]
        assert manifest["repositoryScope"][0]["allowedPaths"] == ["src/export/**", "tests/export/**"]
        assert rc.get(f"/api/package-flow/runs/{run['id']}/manifest").status_code == 403
        assert rc.get(f"/api/package-flow/runs/{run['id']}/manifest", HTTP_X_RUN_TOKEN="wrong").status_code == 403
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert (s["lifecycle"], s["phase"]) == ("active", "build")
        assert len(pkg.human.get(f"{pkg.wi}/runs").json()["results"]) == 1

    def test_run_requires_claim_of_same_principal(self, world):
        pkg = Pkg(world)
        approval = pkg.approve()
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        _, rc2 = pkg.runner()
        r = pkg.start(rc2, approval["id"], claim["id"])
        assert r.status_code == 409 and r.json()["code"] == "CLAIM_INVALID"
        r = pkg.start(rc, approval["id"], None)
        assert r.status_code == 409 and r.json()["code"] == "CLAIM_INVALID"

    def test_one_active_run_per_claim(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = pkg.start(rc, approval["id"], claim["id"])
        assert r.status_code == 409 and r.json()["code"] == "RUN_ALREADY_ACTIVE"

    def test_run_events_lifecycle(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        url = f"/api/package-flow/runs/{run['id']}/events"
        f = claim["fencing_token"]
        assert (
            rc.post(url, {"type": "started", "fencing_token": f}, format="json", HTTP_X_RUN_TOKEN=token).json()[
                "status"
            ]
            == "running"
        )
        r = rc.post(
            url, {"type": "progress", "fencing_token": f, "detail": {"pct": 40}}, format="json", HTTP_X_RUN_TOKEN=token
        )
        assert r.json()["progress"] == {"pct": 40}
        r = rc.post(url, {"type": "bogus", "fencing_token": f}, format="json", HTTP_X_RUN_TOKEN=token)
        assert r.status_code == 422
        r = rc.post(
            url, {"type": "finished", "fencing_token": f, "detail": {"ok": True}}, format="json", HTTP_X_RUN_TOKEN=token
        )
        assert r.json()["status"] == "finished"
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert s["phase"] == "review"

    def test_accepted_action_and_evidence(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = action(
            rc,
            run["id"],
            token,
            claim["fencing_token"],
            "edit_allowed_files",
            paths=["src/export/csv.py", "tests/export/test_csv.py"],
            spend_minor=100,
        )
        assert r.status_code == 200, r.content
        assert r.json()["accepted"] is True
        assert ExecutionRun.objects.get(id=run["id"]).spend_minor == 100
        r = rc.post(
            f"/api/package-flow/runs/{run['id']}/evidence",
            {"kind": "test", "name": "pytest", "result": "passed", "criterion_ids": ["C-1"]},
            format="json",
            HTTP_X_RUN_TOKEN=token,
        )
        assert r.status_code == 201, r.content
        ev = Evidence.objects.get(id=r.json()["id"])
        assert ev.trust == "local_self_report" and ev.issue_id == pkg.issue.id

    def test_ac27_repo_content_cannot_expand_rights(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        f = claim["fencing_token"]
        # A document in the repo told the agent to merge directly: server-side policy wins.
        r = action(rc, run["id"], token, f, "merge")
        assert r.status_code == 409 and r.json()["code"] == "ACTION_NOT_ALLOWED"
        r = action(rc, run["id"], token, f, "open_merge_request")  # not in this approval
        assert r.json()["code"] == "ACTION_NOT_ALLOWED"
        r = action(rc, run["id"], token, f, "edit_allowed_files", paths=[".gitlab-ci.yml"])
        assert r.status_code == 409 and r.json()["code"] == "PATH_NOT_ALLOWED"
        r = action(rc, run["id"], token, f, "edit_allowed_files", paths=["src/export/../../secrets.env"])
        assert r.json()["code"] == "PATH_NOT_ALLOWED"
        # The agent cannot approve its own execution either.
        r = rc.post(
            f"{pkg.wi}/execution-approvals", {"revision_id": approval["revision_id"], "kind": "human"}, format="json"
        )
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        assert RunAction.objects.filter(run_id=run["id"], accepted=False).count() == 4

    def test_budget_and_time_limits(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        f = claim["fencing_token"]
        r = action(rc, run["id"], token, f, "create_commit", spend_minor=2000)
        assert r.status_code == 409 and r.json()["code"] == "BUDGET_EXCEEDED"
        ExecutionRun.objects.filter(id=run["id"]).update(started_at=timezone.now() - timedelta(hours=2))
        r = action(rc, run["id"], token, f, "create_commit")
        assert r.status_code == 409 and r.json()["code"] == "TIME_LIMIT_EXCEEDED"

    def test_fr_g06_cancelled_run_token_cannot_push(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = pkg.human.post(f"{pkg.base}/runs/{run['id']}/cancel", {"reason": "stop"}, format="json")
        assert r.status_code == 202, r.content
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert run_obj.status == "cancelled" and run_obj.cancel_requested_at is not None
        assert run_obj.run_token_hash == ""
        r = action(rc, run["id"], token, claim["fencing_token"], "push_work_branch")
        assert r.status_code == 403 and r.json()["code"] == "RUN_TOKEN_INVALID"

    def test_cancel_requires_capability(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        member = world.member()
        world.add_project_member(pkg.project, member, 15)
        r = human_client_for(member).post(f"{pkg.base}/runs/{run['id']}/cancel", {}, format="json")
        assert r.status_code == 403

    def test_ac14_capability_revocation_without_relogin(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        CapabilityGrant.objects.filter(member=world.owner, capability="run.start").update(deleted_at=timezone.now())
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        assert r.status_code == 403 and r.json()["code"] == "PERMISSION_DENIED"

    def test_revoked_approval_blocks_action(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        ExecutionApproval.objects.filter(id=approval["id"]).update(revoked_at=timezone.now())
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        assert r.status_code == 409 and r.json()["code"] == "APPROVAL_REVOKED"

    def test_pf05_agent_run_needs_approval_even_when_started(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        started = world.state(pkg.project, name="In Progress", group="started")
        from plane.db.models import Issue

        Issue.all_objects.filter(id=pkg.issue.id).update(state=started, is_draft=False)
        _, rc = pkg.runner()
        r = pkg.claim(rc)
        assert r.status_code == 409 and r.json()["code"] == "REVISION_NOT_APPROVED"
