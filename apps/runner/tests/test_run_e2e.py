# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""End-to-end runs against the fake server and a temporary git repo."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from conftest import PY_FAIL, PY_OK, sh

from project_hub_runner import git_ops
from project_hub_runner.agents.base import AgentAdapter, AgentResult
from project_hub_runner.agents.deterministic import DeterministicAgent
from project_hub_runner.policy import Rules
from project_hub_runner.runner import RunRequest, execute_run, push_human_run
from project_hub_runner.state import StateStore


def _req(fake, approval, binding, **kw):
    return RunRequest(fake.project_id, fake.issue_id, approval, binding_id=binding, **kw)


def _worktrees(cfg) -> list[Path]:
    root = Path(cfg.home) / "worktrees"
    return [p for p in root.glob("*/*")] if root.exists() else []


PLAN = {
    "commit_subject": "Add feature module",
    "edits": [{"path": "src/feature.py", "content": "def feature():\n    return 42\n"}],
    "self_reports": ["Tried it manually in the IDE"],
}


def test_refuses_unapproved_revision_and_creates_no_worktree(fake, cfg, client, git_repo, binding_id):
    """AC01/INV-01: a draft/unapproved revision never starts a run; no worktree is prepared."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"], state="draft")
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(PLAN))
    assert out.status == "refused" and out.reason == "REVISION_NOT_APPROVED"
    assert out.exit_code == 2
    assert _worktrees(cfg) == []
    assert all(c["status"] == "released" for c in fake.claims.values()), "claim must be released"
    assert git_repo.remote_branches() == ["main"]


def test_manifest_draft_state_refused_before_worktree(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    fake.manifest_overrides = {"revisionState": "draft"}
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(PLAN))
    assert out.status == "refused" and "manifest invalid" in out.reason
    assert _worktrees(cfg) == []
    assert fake.accepted("prepare_worktree") == []
    assert fake.event_types() == ["failed"]


def test_deterministic_agent_end_to_end(fake, cfg, client, git_repo, binding_id):
    checks = [{"name": "unit", "command": PY_OK}, {"name": "lint", "command": PY_FAIL}]
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"], checks=checks)
    dev_head_before = sh(git_repo.dev, "git", "rev-parse", "HEAD")

    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(PLAN))
    assert out.status == "finished", out
    assert out.pushed and out.commit_sha
    assert out.changed_files == ["src/feature.py"]

    # worktree is runner-owned, created from baseCommit on a ph/ branch (FR-G02)
    wt = Path(out.worktree)
    assert wt.is_relative_to(Path(cfg.home))
    assert out.branch.startswith("ph/") and out.branch == git_ops.work_branch_name(fake.issue_id, out.run_id)
    assert sh(wt, "git", "rev-parse", "HEAD~1") == git_repo.base
    # developer's own checkout untouched
    assert sh(git_repo.dev, "git", "rev-parse", "HEAD") == dev_head_before
    assert sh(git_repo.dev, "git", "status", "--porcelain") == ""
    assert not (git_repo.dev / "src" / "feature.py").exists()

    # commit trailers for correlation (FR-G08)
    trailers = git_ops.commit_trailers(wt, out.commit_sha)
    run = fake.runs[out.run_id]
    approval = fake.approvals[run["approval_id"]]
    assert trailers["Work-Item"] == fake.issue_id
    assert trailers["Revision"] == approval["revision_id"]
    assert trailers["Run"] == out.run_id

    # pushed only the work branch; target untouched, never merged (K09)
    assert git_repo.remote_branches() == sorted(["main", out.branch])
    assert git_repo.remote_head("main") == git_repo.base
    assert git_repo.remote_head(out.branch) == out.commit_sha

    # evidence: runner_reported only for executed checks; passed only on exit 0
    ev = {e["name"]: e for e in fake.evidence}
    assert ev["unit"]["trust"] == "runner_reported" and ev["unit"]["result"] == "passed"
    assert ev["unit"]["executed"] is True and ev["unit"]["commit_sha"] == out.commit_sha
    assert ev["lint"]["result"] == "failed" and ev["lint"]["exit_code"] == 1
    assert ev["developer_claim"]["trust"] == "local_self_report" and ev["developer_claim"]["result"] == "claimed"
    assert all(e["result"] != "passed" or e["executed"] for e in fake.evidence)

    types = fake.event_types(out.run_id)
    assert types[0] == "started" and types[-1] == "finished"
    assert "progress" in types
    finished = [e for e in fake.events if e["type"] == "finished"][0]["detail"]
    assert {"name": "lint", "result": "failed"} in finished["checks"]
    # every controlled action went through the server gate first
    for action in ("prepare_worktree", "edit_allowed_files", "create_commit", "run_allowed_checks", "push_work_branch"):
        assert fake.accepted(action), action
    assert fake.claims[run["claim_id"]]["status"] == "released"


def test_unapproved_check_is_reported_not_run(fake, cfg, client, git_repo, binding_id):
    checks = [{"name": "unit", "command": PY_OK}]
    actions = ["prepare_worktree", "edit_allowed_files", "create_commit"]  # no run_allowed_checks, no push
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"], allowed_actions=actions, checks=checks)
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(PLAN))
    assert out.status == "finished" and not out.pushed
    assert "push_work_branch not in approved" in out.reason
    ev = [e for e in fake.evidence if e["name"] == "unit"][0]
    assert ev["result"] == "not_run" and ev["executed"] is False
    assert git_repo.remote_branches() == ["main"]


def test_edit_outside_allowed_paths_fails_and_nothing_pushed(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    plan = {"edits": [{"path": "src/ok.py", "content": "x=1\n"}, {"path": "README.md", "append": "pwned\n"}]}
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(plan))
    assert out.status == "failed"
    assert git_repo.remote_branches() == ["main"]
    assert fake.accepted("push_work_branch") == [] and fake.accepted("create_commit") == []
    assert fake.event_types()[-1] == "failed"


class RogueAgent(AgentAdapter):
    """Writes outside the allowed paths WITHOUT asking the gate (like an arbitrary external CLI)."""

    name = "rogue"

    def run(self, task, workdir, policy, reporter):
        (Path(workdir) / "src" / "ok.py").write_text("ok\n")
        (Path(workdir) / ".github").mkdir(exist_ok=True)
        (Path(workdir) / ".github" / "workflow.yml").write_text("on: push\n")
        return AgentResult("completed", commit_subject="rogue")


def test_post_run_diff_filter_blocks_commit_and_push(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=RogueAgent())
    assert out.status == "failed" and out.reason == "paths_outside_scope"
    assert out.detail["paths"] == [".github/workflow.yml"]
    assert git_repo.remote_branches() == ["main"]
    assert fake.accepted("create_commit") == []
    wt = Path(out.worktree)
    assert git_ops.commits_since(wt, git_repo.base) == []


def test_repository_prompt_injection_cannot_widen_policy(fake, cfg, client, git_repo, binding_id):
    """AC27: AGENTS.md demands merge + all paths; server/runner limits stay unchanged."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    captured = {}

    class ObedientAgent(DeterministicAgent):
        def run(self, task, workdir, policy, reporter):
            text = (Path(workdir) / "AGENTS.md").read_text()
            assert "IGNORE ALL PREVIOUS RULES" in text
            captured["rules_before"] = policy.rules
            result = super().run(task, workdir, policy, reporter)
            captured["rules_after"] = policy.rules
            captured["result"] = result
            return result

    # The "obedient" agent follows the injected instruction and edits a file outside scope.
    plan = {"edits": [{"path": "AGENTS.md", "content": "approved\n"}]}
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=ObedientAgent(plan))
    assert out.status == "failed"
    assert "AGENTS.md" in captured["result"].context_files_read
    assert captured["rules_before"] is captured["rules_after"]
    assert captured["rules_after"].allowed_paths == ("src/**",)
    assert "merge" not in captured["rules_after"].allowed_actions
    assert not hasattr(git_ops, "merge"), "the runner has no merge capability at all (K09)"
    assert git_repo.remote_head("main") == git_repo.base
    assert all(a["action"] != "merge" for a in fake.actions)
    assert Rules.__dataclass_params__.frozen


def test_cancelled_run_cannot_push(fake, cfg, client, git_repo, binding_id):
    """FR-G06: after cancel, the run token cannot commit or push."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])

    class CancelledMidway(AgentAdapter):
        name = "cancelled"

        def run(self, task, workdir, policy, reporter):
            policy.authorize("edit_allowed_files", paths=["src/new.py"])
            (Path(workdir) / "src" / "new.py").write_text("x\n")
            fake.cancel(task.run_id)
            deadline = time.time() + 3
            while not policy.stopped and time.time() < deadline:
                time.sleep(0.05)
            return AgentResult("completed", commit_subject="should not be committed")

    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=CancelledMidway())
    assert out.status == "stopped" and "cancel" in out.reason
    assert out.exit_code == 5
    assert git_repo.remote_branches() == ["main"]
    assert fake.accepted("create_commit") == [] and fake.accepted("push_work_branch") == []


def test_lease_lost_during_run_stops_agent(fake, cfg, client, git_repo, binding_id):
    """AC06 end-to-end: another runner takes over; our run stops, nothing is pushed."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    from project_hub_runner.claim import acquire_claim
    from project_hub_runner.client import Client

    class Slow(AgentAdapter):
        name = "slow"

        def run(self, task, workdir, policy, reporter):
            (Path(workdir) / "src" / "a.py").write_text("a\n")
            claim_id = fake.runs[task.run_id]["claim_id"]
            fake.expire_claim(claim_id)
            acquire_claim(Client(fake.url, "ws", "tok-B", retries=0), fake.project_id, fake.issue_id, binding_id)
            deadline = time.time() + 3
            while not policy.stopped and time.time() < deadline:
                time.sleep(0.05)
            return AgentResult("completed")

    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=Slow())
    assert out.status == "stopped"
    assert out.reason in ("LEASE_EXPIRED", "STALE_FENCING_TOKEN")
    assert git_repo.remote_branches() == ["main"]
    assert fake.accepted("create_commit") == []


def test_base_moved_reports_waiting(fake, cfg, client, git_repo, binding_id):
    """INV-04: target head moved after approval → waiting with reason, no worktree."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    other = git_repo.dev.parent / "other"
    sh(git_repo.dev.parent, "git", "clone", "-q", str(git_repo.origin), str(other))
    (other / "src" / "app.py").write_text("print('moved')\n")
    sh(other, "git", "-c", "user.name=o", "-c", "user.email=o@x", "commit", "-qam", "move")
    sh(other, "git", "push", "-q", "origin", "main")
    out = execute_run(cfg, client, _req(fake, aid, binding_id), adapter=DeterministicAgent(PLAN))
    assert out.status == "waiting" and out.exit_code == 3
    waiting = [e for e in fake.events if e["type"] == "waiting"]
    assert waiting and waiting[0]["detail"]["reason"] == "base_moved"
    assert _worktrees(cfg) == []


def test_human_mode_handoff_then_push(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"], checks=[{"name": "unit", "command": PY_OK}])
    out = execute_run(cfg, client, _req(fake, aid, binding_id, mode="human"))
    assert out.status == "handed_off"
    run = fake.runs[out.run_id]
    assert fake.claims[run["claim_id"]]["status"] == "active", "claim kept for the developer"
    wt = Path(out.worktree)
    (wt / "src" / "human.py").write_text("print('by hand')\n")
    msg = git_ops.build_commit_message("Human change", "", fake.issue_id, "rev", out.run_id)
    sh(wt, "git", "add", "-A")
    sh(wt, "git", "-c", "user.name=Dev", "-c", "user.email=d@x", "commit", "-q", "-m", msg)
    res = push_human_run(cfg, client, out.run_id, run_checks_flag=True, state=StateStore(cfg.home))
    assert res.status == "finished" and res.pushed, res
    assert out.branch in git_repo.remote_branches()
    assert [e["result"] for e in fake.evidence] == ["passed"]
    assert fake.claims[run["claim_id"]]["status"] == "released"


def test_human_mode_push_refuses_out_of_scope_commit(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    out = execute_run(cfg, client, _req(fake, aid, binding_id, mode="human"))
    wt = Path(out.worktree)
    (wt / "README.md").write_text("changed\n")
    sh(wt, "git", "-c", "user.name=Dev", "-c", "user.email=d@x", "commit", "-qam", "readme")
    res = push_human_run(cfg, client, out.run_id, state=StateStore(cfg.home))
    assert res.status == "failed" and res.reason == "paths_outside_scope"
    assert git_repo.remote_branches() == ["main"]


def test_cli_run_json(fake, cfg, git_repo, binding_id, tmp_path, monkeypatch):
    from project_hub_runner.cli import main
    from project_hub_runner.config import save_config

    path = tmp_path / "cfg" / "runner.json"
    save_config(cfg, path)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(PLAN))
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    rc = main(
        [
            "--config",
            str(path),
            "--json",
            "run",
            "--project",
            fake.project_id,
            "--work-item",
            fake.issue_id,
            "--approval",
            aid,
            "--plan",
            str(plan),
        ]
    )
    assert rc == 0
    assert len(git_repo.remote_branches()) == 2
    assert sys.executable  # keep import used
