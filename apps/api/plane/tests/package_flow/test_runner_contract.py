# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract between the backend and the external runner package (apps/runner).

Verifies the runner-facing additions (heartbeat extras, ``runner/me``, evidence
trust downgrade) and that the runner's own parsing/hash/error mapping accepts
what the real backend emits.
"""

import sys
from pathlib import Path

import pytest

from plane.package_flow.models import Evidence, ExecutionApproval, ExecutionRun, RunAction

from .pkg_support import Pkg, action

RUNNER_SRC = Path(__file__).resolve().parents[4] / "runner"
if str(RUNNER_SRC) not in sys.path:
    sys.path.insert(0, str(RUNNER_SRC))

from project_hub_runner.errors import (  # noqa: E402
    ActionRejected,
    ClaimHeld,
    NativeSourceChanged,
    RunCancelled,
    StaleFencingToken,
    error_for,
)
from project_hub_runner.manifest import canonical_hash, parse_manifest  # noqa: E402
from project_hub_runner.policy import Rules  # noqa: E402

HB = "/api/package-flow/claims/{}/heartbeat"


def _hb(rc, claim, **extra):
    return rc.post(HB.format(claim["id"]), {"fencing_token": claim["fencing_token"], **extra}, format="json")


@pytest.mark.unit
class TestRunnerContract:
    def test_manifest_hash_and_shape_accepted_by_runner(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        body = rc.get(f"/api/package-flow/runs/{run['id']}/manifest", HTTP_X_RUN_TOKEN=token).json()
        assert canonical_hash(body["manifest"]) == body["manifest_hash"]
        m = parse_manifest(
            body,
            expected_run_id=run["id"],
            expected_work_item_id=str(pkg.issue.id),
            expected_project_id=str(pkg.project.id),
            expected_claim_id=claim["id"],
            expected_fencing_token=claim["fencing_token"],
        )
        assert m.approval.id == approval["id"]
        assert m.task.intent and m.task.criteria
        rules = Rules.from_manifest(m)
        assert rules.binding_id == str(pkg.binding.id)
        assert rules.allowed_paths == ("src/export/**", "tests/export/**")
        # a tampered manifest is refused by the runner
        body["manifest"]["allowedActions"].append("open_merge_request")
        with pytest.raises(Exception, match="hash"):
            parse_manifest(body)

    def test_heartbeat_extras_and_cancel_signal(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = _hb(rc, claim, lease_seconds=120)
        assert r.status_code == 200, r.content
        data = r.json()
        assert data["lease_seconds"] == 120
        assert data["cancel_requested"] is False and data["run_id"] == run["id"]
        assert data["fencing_token"] == claim["fencing_token"]
        r = pkg.human.post(f"{pkg.base}/runs/{run['id']}/cancel", {}, format="json")
        assert r.status_code == 202
        data = _hb(rc, claim).json()
        assert data["cancel_requested"] is True and data["run_status"] == "cancelled"
        # the cancelled run token cannot act; the runner maps the error to a stop
        r = action(rc, run["id"], token, claim["fencing_token"], "push_work_branch")
        assert isinstance(error_for(r.status_code, r.json()), RunCancelled)

    def test_runner_me(self, world):
        pkg = Pkg(world)
        runner, rc = pkg.runner(name="ci-runner")
        r = rc.get("/api/package-flow/runner/me")
        assert r.status_code == 200, r.content
        me = r.json()
        assert me["id"] == str(runner.id) and me["name"] == "ci-runner"
        assert me["workspace_slug"] == world.workspace.slug and me["principal_kind"] == "agent"
        assert "token" not in me
        assert pkg.human.get("/api/package-flow/runner/me").status_code == 404

    def test_evidence_trust_can_only_be_downgraded(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        runner = ExecutionRun.objects.get(id=run["id"]).runner
        runner.kind = "customer"
        runner.save(update_fields=["kind"])
        url = f"/api/package-flow/runs/{run['id']}/evidence"
        base = {"kind": "check", "name": "unit", "result": "passed", "fencing_token": claim["fencing_token"]}
        r = rc.post(url, base, format="json", HTTP_X_RUN_TOKEN=token)
        assert r.status_code == 201 and r.json()["trust"] == "runner_reported"
        r = rc.post(
            url,
            {
                **base,
                "kind": "self_report",
                "name": "developer_claim",
                "result": "unknown",
                "trust": "local_self_report",
            },
            format="json",
            HTTP_X_RUN_TOKEN=token,
        )
        assert r.json()["trust"] == "local_self_report"
        # a local runner cannot upgrade
        runner.kind = "local"
        runner.save(update_fields=["kind"])
        r = rc.post(url, {**base, "trust": "runner_reported"}, format="json", HTTP_X_RUN_TOKEN=token)
        assert r.json()["trust"] == "local_self_report"
        assert Evidence.objects.filter(run_id=run["id"]).count() == 3

    def test_error_codes_map_to_runner_exceptions(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        _, rc2 = pkg.runner(name="B")
        r = pkg.claim(rc2)
        assert isinstance(error_for(r.status_code, r.json()), ClaimHeld)
        r = action(rc, run["id"], token, claim["fencing_token"], "edit_allowed_files", paths=["README.md"])
        assert isinstance(error_for(r.status_code, r.json()), ActionRejected)
        r = action(rc, run["id"], token, claim["fencing_token"] - 1, "create_commit")
        assert isinstance(error_for(r.status_code, r.json()), StaleFencingToken)
        pkg.issue.description_html = "<p>Changed after approval</p>"
        pkg.issue.save()
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        # The native-hook pauses the run (RUN_PAUSED) before the gate recomputes the source hash;
        # both make the runner stop all further actions.
        assert r.json()["code"] in ("RUN_PAUSED", "NATIVE_SOURCE_CHANGED")
        assert isinstance(error_for(r.status_code, r.json()), (NativeSourceChanged, RunCancelled))


GOOD_CHECK = {"name": "unit", "command": ["pytest", "-q"], "trusted": False}


@pytest.mark.unit
class TestApprovalChecks:
    @pytest.mark.parametrize(
        "checks",
        [
            "pytest",
            [{"name": "Bad Name", "command": ["x"]}],
            [{"name": "unit", "command": "pytest -q"}],
            [{"name": "unit", "command": []}],
            [{"name": "unit", "command": ["ok", 3]}],
            [{"name": "unit", "command": ["x"], "trusted": "yes"}],
            [GOOD_CHECK, GOOD_CHECK],
            [{"name": f"c{i}", "command": ["x"]} for i in range(21)],
        ],
    )
    def test_invalid_checks_rejected(self, world, checks):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"], checks=checks), format="json")
        assert r.status_code == 422, r.content
        assert not ExecutionApproval.objects.filter(issue_id=pkg.issue.id).exists()

    def test_checks_in_rest_shape_and_manifest_not_in_contract(self, world):
        pkg = Pkg(world)
        approval = pkg.approve(
            checks=[GOOD_CHECK, {"name": "lint", "command": ["ruff", "check"]}],
            allowed_actions=["prepare_worktree", "edit_allowed_files", "run_allowed_checks", "create_commit"],
        )
        assert approval["checks"] == [GOOD_CHECK, {"name": "lint", "command": ["ruff", "check"], "trusted": False}]
        assert "checks" not in approval["contract"]  # 1.1.0 schema has additionalProperties:false
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        body = pkg.start(rc, approval["id"], claim["id"]).json()
        run, token = body["run"], body["run_token"]
        m = rc.get(f"/api/package-flow/runs/{run['id']}/manifest", HTTP_X_RUN_TOKEN=token).json()
        assert [c["name"] for c in m["manifest"]["checks"]] == ["unit", "lint"]
        assert canonical_hash(m["manifest"]) == m["manifest_hash"]  # checks are covered by the hash
        parsed = parse_manifest(m)
        assert parsed.checks[0].command == ("pytest", "-q")

        f = claim["fencing_token"]
        r = action(rc, run["id"], token, f, "run_allowed_checks", check="unit", command=["pytest", "-q"])
        assert r.status_code == 200, r.content
        r = action(rc, run["id"], token, f, "run_allowed_checks", check="deploy", command=["./deploy.sh"])
        assert r.status_code == 409 and r.json()["code"] == "CHECK_NOT_ALLOWED"
        assert isinstance(error_for(r.status_code, r.json()), ActionRejected)
        r = action(rc, run["id"], token, f, "run_allowed_checks", check="unit", command=["pytest", "-q", "--pdb"])
        assert r.status_code == 409 and r.json()["code"] == "CHECK_NOT_ALLOWED"
        rows = RunAction.objects.filter(run_id=run["id"], action="run_allowed_checks")
        assert [a.accepted for a in rows.order_by("created_at")] == [True, False, False]

    def test_no_checks_approved_rejects_any_check(self, world):
        pkg = Pkg(world)
        approval = pkg.approve(
            allowed_actions=["prepare_worktree", "edit_allowed_files", "run_allowed_checks", "create_commit"]
        )
        assert approval["checks"] == []
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        body = pkg.start(rc, approval["id"], claim["id"]).json()
        r = action(rc, body["run"]["id"], body["run_token"], claim["fencing_token"], "run_allowed_checks", check="unit")
        assert r.status_code == 409 and r.json()["code"] == "CHECK_NOT_ALLOWED"
