# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run orchestration (J04/J05, FR-G05, FR-G06).

``claim → POST runs (approval) → manifest → worktree → adapter → diff filter
→ commit → checks/evidence → push work branch → finished``.

Every transition that has side effects checks the shared :class:`StopSignal`
first; once the fencing token is stale, the lease expired or the run was
cancelled, nothing further is executed (AC06, FR-G06).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import git_ops
from .agents.base import AgentAdapter, AgentResult, TaskSpec
from .checks import run_check
from .claim import ClaimHandle, StopSignal, Supervisor, acquire_claim, release_claim
from .config import RunnerConfig
from .errors import (
    ActionsStopped,
    ApiError,
    BaseMoved,
    ClaimHeld,
    FencingLost,
    GitError,
    ManifestInvalid,
    PolicyViolation,
    RunCancelled,
    RunnerError,
    RunRefused,
    ServerUnreachable,
    WorkspaceError,
)
from .manifest import Manifest, fetch_manifest, parse_checks
from .policy import PolicyGate, Rules
from .reporter import CheckResult, Reporter
from .sandbox import enforcement_report
from .state import StateStore
from .workspace import PreparedWorkspace, prepare_worktree

EXIT_OK, EXIT_ERROR, EXIT_REFUSED, EXIT_WAITING, EXIT_FAILED, EXIT_STOPPED, EXIT_UNREACHABLE = 0, 1, 2, 3, 4, 5, 6


@dataclass
class RunRequest:
    project_id: str
    work_item_id: str
    approval_id: str
    binding_id: str | None = None
    repo_path: str | None = None
    remote: str | None = None
    mode: str = "agent"  # agent | human
    adapter: str = "deterministic"
    push: bool = True
    exclusive: bool = True
    lease_seconds: int | None = None
    heartbeat_interval: float | None = None
    cancel_poll: bool = True
    fetch: bool = True
    claim_id: str | None = None  # reuse a claim from `ph-runner claim`


@dataclass
class RunOutcome:
    status: str
    exit_code: int
    run_id: str | None = None
    reason: str = ""
    commit_sha: str | None = None
    branch: str | None = None
    worktree: str | None = None
    pushed: bool = False
    changed_files: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def cancel_checker(client, project_id: str, work_item_id: str, run_id: str) -> Callable[[], bool]:
    def check() -> bool:
        for run in client.list_runs(project_id, work_item_id):
            if str(run.get("id")) == run_id:
                return run.get("status") == "cancelled" or bool(run.get("cancel_requested_at"))
        return False

    return check


class RunSession:
    """Everything bound to one server run: claim, token, gate, reporter, supervisor."""

    def __init__(self, cfg: RunnerConfig, client, claim: ClaimHandle, run_id: str, run_token: str, stop: StopSignal):
        self.cfg = cfg
        self.client = client
        self.claim = claim
        self.run_id = run_id
        self.run_token = run_token
        self.stop = stop
        self.reporter = Reporter(client, run_id, run_token, claim, stop)
        self.manifest: Manifest | None = None
        self.rules: Rules | None = None
        self.gate: PolicyGate | None = None

    def load_manifest(self, binding_id: str | None) -> None:
        self.manifest = fetch_manifest(
            self.client,
            self.run_id,
            self.run_token,
            expected_work_item_id=self.claim.work_item_id,
            expected_project_id=self.claim.project_id,
            expected_claim_id=self.claim.id,
            expected_fencing_token=self.claim.fencing_token,
        )
        self.rules = Rules.from_manifest(
            self.manifest, binding_id or self.claim.binding_id, tuple(parse_checks(self.cfg.checks))
        )
        self.gate = PolicyGate(self.rules, self.client, self.run_token, self.claim, self.stop)


def _adapter_for(
    cfg: RunnerConfig, req: RunRequest, log_dir: Path, plan_path: str | None, agent_command
) -> AgentAdapter:
    if req.mode == "human":
        from .agents.human import HumanAdapter

        return HumanAdapter()
    if req.adapter == "deterministic":
        from .agents.deterministic import DeterministicAgent, load_plan

        return DeterministicAgent(load_plan(plan_path) if plan_path else None)
    if req.adapter in ("external", "external_command"):
        from .agents.external_command import ExternalCommandAgent

        return ExternalCommandAgent(
            agent_command or cfg.agent_command, log_dir, cfg.env_passthrough, cfg.sandbox_prefix
        )
    raise RunnerError(f"unknown adapter {req.adapter!r}")


def execute_run(
    cfg: RunnerConfig,
    client,
    req: RunRequest,
    adapter: AgentAdapter | None = None,
    plan_path: str | None = None,
    agent_command: list[str] | None = None,
    state: StateStore | None = None,
    on_session: Callable[[RunSession], None] | None = None,
) -> RunOutcome:
    state = state or StateStore(cfg.home)
    stop = StopSignal()
    lease_seconds = req.lease_seconds or cfg.lease_seconds

    # 1. claim (atomic, AC05)
    try:
        if req.claim_id:
            saved = state.load_claim(req.claim_id)
            if not saved:
                return RunOutcome("refused", EXIT_REFUSED, reason=f"unknown local claim {req.claim_id}")
            claim = ClaimHandle.from_state(saved)
        else:
            claim = acquire_claim(
                client,
                req.project_id,
                req.work_item_id,
                req.binding_id,
                req.exclusive,
                lease_seconds,
                approval_id=req.approval_id,
            )
            state.save_claim(claim.id, claim.to_state())
    except ClaimHeld as exc:
        return RunOutcome("claim_held", EXIT_WAITING, reason=f"claim held by {exc.holder or 'another principal'}")
    except ServerUnreachable as exc:
        return RunOutcome("unknown", EXIT_UNREACHABLE, reason=f"server unreachable: {exc}")

    supervisor: Supervisor | None = None
    session: RunSession | None = None
    ws: PreparedWorkspace | None = None
    keep_claim = False
    outcome: RunOutcome

    def finish(o: RunOutcome) -> RunOutcome:
        if session is not None:
            state.update(
                "runs",
                session.run_id,
                local_status=o.status,
                reason=o.reason,
                commit_sha=o.commit_sha,
                pushed=o.pushed,
                unsent_events=len(session.reporter.unsent),
            )
        return o

    try:
        # 2. start run with the approval (server checks INV-01/INV-04; AC01)
        try:
            resp = client.start_run(
                req.project_id,
                req.work_item_id,
                req.approval_id,
                claim.id,
                mode=req.mode,
                agent_adapter=None if req.mode == "human" else req.adapter,
            )
        except RunRefused as exc:
            return RunOutcome("refused", EXIT_REFUSED, reason=exc.code)
        run = resp.get("run") or {}
        run_id = str(run.get("id") or resp.get("run_id") or "")
        run_token = str(resp.get("run_token") or "")
        if not run_id or not run_token:
            raise RunnerError(f"unexpected run response: {resp!r}")
        session = RunSession(cfg, client, claim, run_id, run_token, stop)
        state.save_run(
            run_id,
            {
                "run_id": run_id,
                "run_token": run_token,
                "claim": claim.to_state(),
                "project_id": req.project_id,
                "work_item_id": req.work_item_id,
                "approval_id": req.approval_id,
                "mode": req.mode,
                "adapter": req.adapter,
                "local_status": "starting",
                "last_server_status": run.get("status") or "queued",
                "last_server_contact_at": time.time(),
            },
        )
        if on_session:
            on_session(session)

        supervisor = Supervisor(
            client,
            claim,
            stop,
            interval=req.heartbeat_interval or cfg.heartbeat_interval or None,
            cancel_check=cancel_checker(client, req.project_id, req.work_item_id, run_id) if req.cancel_poll else None,
        )
        supervisor.start()

        # 3. manifest — refuse on any doubt (INV-01)
        try:
            session.load_manifest(req.binding_id)
        except ManifestInvalid as exc:
            session.reporter.failed("manifest_invalid", {"error": str(exc)})
            return finish(RunOutcome("refused", EXIT_REFUSED, run_id, reason=f"manifest invalid: {exc}"))
        gate, rules, reporter = session.gate, session.rules, session.reporter
        assert gate is not None and rules is not None and session.manifest is not None
        reporter.binding_id = rules.binding_id

        reporter.started(
            {
                "mode": req.mode,
                "adapter": req.adapter if req.mode == "agent" else "human",
                "policy_version": rules.policy_version,
                "enforcement": enforcement_report(cfg.sandbox_prefix),
            }
        )

        # 4. worktree — only now, for a valid run (FR-G02, INV-04)
        binding_cfg = cfg.binding(rules.binding_id)
        repo_path = req.repo_path or (binding_cfg.path if binding_cfg else None)
        remote = req.remote or (binding_cfg.remote if binding_cfg else "origin")
        if not repo_path:
            reporter.failed("no_local_clone", {"binding_id": rules.binding_id})
            return finish(
                RunOutcome("failed", EXIT_FAILED, run_id, reason=f"no local clone configured for {rules.binding_id}")
            )
        reporter.progress("preparing_worktree")
        try:
            ws = prepare_worktree(gate, repo_path, cfg.home, remote=remote, fetch=req.fetch)
        except BaseMoved as exc:
            reporter.waiting(
                "base_moved",
                {"base_commit": exc.base_commit, "current_head": exc.current_head, "target_branch": exc.target_branch},
            )
            return finish(RunOutcome("waiting", EXIT_WAITING, run_id, reason=str(exc)))
        state.update(
            "runs",
            run_id,
            worktree=str(ws.path),
            branch=ws.branch,
            remote=remote,
            base_commit=ws.base_commit,
            binding_id=rules.binding_id,
            target_branch=rules.target_branch,
            repo_path=str(ws.repo_path),
        )

        # 5. adapter
        task = TaskSpec.from_manifest(session.manifest, rules)
        log_dir = Path(cfg.home) / "logs" / run_id
        adapter = adapter or _adapter_for(cfg, req, log_dir, plan_path, agent_command)
        reporter.progress("working", f"adapter {adapter.name}")
        result: AgentResult = adapter.run(task, ws.path, gate, reporter)
        for q in result.questions:
            reporter.question(q)

        if result.status == "handed_off":
            keep_claim = True
            state.update("runs", run_id, local_status="handed_off")
            return finish(
                RunOutcome(
                    "handed_off", EXIT_OK, run_id, branch=ws.branch, worktree=str(ws.path), reason=result.summary
                )
            )
        if stop.is_set() or result.status == "stopped":
            raise ActionsStopped(stop.reason or result.reason or "stopped")
        if result.status == "waiting":
            reporter.waiting("question", {"questions": result.questions})
            return finish(
                RunOutcome("waiting", EXIT_WAITING, run_id, reason="agent asked a question", worktree=str(ws.path))
            )

        # 6. post-run diff filter: files outside allowedPaths fail the run, nothing pushed (AC27/FR-G06)
        changed = sorted(git_ops.changed_files(ws.path, rules.base_commit))
        bad = rules.disallowed_paths(changed)
        if bad:
            reporter.failed("paths_outside_scope", {"paths": bad})
            return finish(
                RunOutcome(
                    "failed",
                    EXIT_FAILED,
                    run_id,
                    reason="paths_outside_scope",
                    changed_files=changed,
                    worktree=str(ws.path),
                    detail={"paths": bad},
                )
            )
        if result.status == "failed":
            reporter.failed(result.reason or "agent_failed", {"summary": result.summary[-1000:]})
            return finish(
                RunOutcome(
                    "failed",
                    EXIT_FAILED,
                    run_id,
                    reason=result.reason or "agent_failed",
                    changed_files=changed,
                    worktree=str(ws.path),
                )
            )
        if not changed:
            reporter.finished({"result": "no_changes", "summary": result.summary[-500:]})
            return finish(RunOutcome("finished", EXIT_OK, run_id, reason="no_changes", worktree=str(ws.path)))

        # 7. commit with trailers (agent commits are squashed so every change carries them, FR-G08)
        reporter.progress("committing")
        if git_ops.commits_since(ws.path, rules.base_commit):
            git_ops.git(ws.path, "reset", "--soft", rules.base_commit)
        sha = git_ops.commit_all(gate, ws.path, result.commit_subject or task.title, result.commit_body)

        # 8. checks → evidence (runner_reported only for executed checks)
        check_results = run_checks(session, ws.path, result.checks, sha)
        for claim_text in result.self_reports:
            reporter.self_report(claim_text, sha)

        # 9. push work branch via server gate
        pushed = False
        push_note = ""
        if stop.is_set():
            raise ActionsStopped(stop.reason or "stopped")
        if req.push and rules.action_allowed("push_work_branch"):
            reporter.progress("pushing")
            git_ops.push_work_branch(gate, ws.path, remote, ws.branch)
            pushed = True
        elif req.push:
            push_note = "push_work_branch not in approved allowedActions"

        checks_summary = [{"name": c.name, "result": c.result} for c in check_results]
        reporter.finished(
            {
                "commit_sha": sha,
                "branch": ws.branch,
                "pushed": pushed,
                "push_note": push_note,
                "changed_files": changed,
                "checks": checks_summary,
            }
        )
        outcome = RunOutcome(
            "finished",
            EXIT_OK,
            run_id,
            commit_sha=sha,
            branch=ws.branch,
            worktree=str(ws.path),
            pushed=pushed,
            changed_files=changed,
            checks=checks_summary,
            reason=push_note,
        )
        return finish(outcome)

    except (ActionsStopped, FencingLost, RunCancelled) as exc:
        reason = stop.reason or getattr(exc, "code", None) or str(exc)
        stop.trigger(reason)
        _log(f"run stopped: {reason}. No further actions were taken.")
        if session is not None:
            session.reporter.failed("stopped", {"stop_reason": reason})
        return finish(RunOutcome("stopped", EXIT_STOPPED, session.run_id if session else None, reason=reason))
    except PolicyViolation as exc:
        if session is not None:
            session.reporter.failed("policy_violation", {"error": str(exc), "paths": exc.paths})
        return finish(
            RunOutcome(
                "failed",
                EXIT_FAILED,
                session.run_id if session else None,
                reason=f"policy_violation: {exc}",
                detail={"paths": exc.paths},
            )
        )
    except (WorkspaceError, GitError) as exc:
        if session is not None:
            session.reporter.failed("workspace_error", {"error": str(exc)})
        return finish(RunOutcome("failed", EXIT_FAILED, session.run_id if session else None, reason=str(exc)))
    except ServerUnreachable as exc:
        return finish(
            RunOutcome(
                "unknown", EXIT_UNREACHABLE, session.run_id if session else None, reason=f"server unreachable: {exc}"
            )
        )
    except ApiError as exc:
        if session is not None:
            session.reporter.failed("api_error", {"code": exc.code})
        return finish(RunOutcome("failed", EXIT_ERROR, session.run_id if session else None, reason=str(exc)))
    finally:
        if supervisor is not None:
            supervisor.halt()
            supervisor.join(timeout=5)
        if not keep_claim:
            release_claim(client, claim)
            state.delete("claims", claim.id)


def run_checks(session: RunSession, workdir: Path, names: list[str] | None, sha: str | None) -> list[CheckResult]:
    rules, gate, reporter, cfg = session.rules, session.gate, session.reporter, session.cfg
    assert rules is not None and gate is not None
    wanted = names if names is not None else [c.name for c in rules.checks]
    results: list[CheckResult] = []
    if wanted:
        reporter.progress("checks", f"{len(wanted)} check(s)")
    for name in wanted:
        if session.stop.is_set():
            break
        res = run_check(
            gate, name, workdir, Path(cfg.home) / "logs" / session.run_id, cfg.env_passthrough, cfg.sandbox_prefix
        )
        reporter.check_evidence(res, sha)
        results.append(res)
    return results


# --------------------------------------------------------------------------
# Human-mode follow-ups: report / push / status
# --------------------------------------------------------------------------


def resume_session(cfg: RunnerConfig, client, state: StateStore, run_id: str) -> tuple[RunSession, dict[str, Any]]:
    saved = state.load_run(run_id)
    if not saved:
        raise RunnerError(f"no local state for run {run_id} (only runs started by this runner can be resumed)")
    claim = ClaimHandle.from_state(saved["claim"])
    session = RunSession(cfg, client, claim, run_id, saved["run_token"], StopSignal())
    return session, saved


def push_human_run(
    cfg: RunnerConfig, client, run_id: str, run_checks_flag: bool = False, state: StateStore | None = None
) -> RunOutcome:
    """``ph-runner push``: validate the developer's commits against the policy, run checks, push, finish."""
    state = state or StateStore(cfg.home)
    session, saved = resume_session(cfg, client, state, run_id)
    try:
        session.load_manifest(saved.get("binding_id"))
        gate, rules, reporter = session.gate, session.rules, session.reporter
        assert gate is not None and rules is not None
        wt = Path(saved["worktree"])
        if git_ops.uncommitted_files(wt):
            return RunOutcome("refused", EXIT_REFUSED, run_id, reason="uncommitted changes in worktree; commit first")
        changed = sorted(git_ops.committed_files(wt, rules.base_commit))
        bad = rules.disallowed_paths(changed)
        if bad:
            reporter.failed("paths_outside_scope", {"paths": bad})
            return RunOutcome("failed", EXIT_FAILED, run_id, reason="paths_outside_scope", detail={"paths": bad})
        head = git_ops.rev_parse(wt, "HEAD")
        missing = [
            c
            for c in git_ops.commits_since(wt, rules.base_commit)
            if git_ops.commit_trailers(wt, c).get("Work-Item") != rules.work_item_id
        ]
        checks: list[CheckResult] = []
        if run_checks_flag:
            checks = run_checks(session, wt, None, head)
        git_ops.push_work_branch(gate, wt, saved.get("remote") or "origin", saved["branch"])
        summary = [{"name": c.name, "result": c.result} for c in checks]
        reporter.finished(
            {
                "commit_sha": head,
                "branch": saved["branch"],
                "pushed": True,
                "changed_files": changed,
                "checks": summary,
                "commits_without_trailers": missing,
            }
        )
        state.update("runs", run_id, local_status="finished", pushed=True, commit_sha=head)
        release_claim(client, session.claim)
        return RunOutcome(
            "finished",
            EXIT_OK,
            run_id,
            commit_sha=head,
            branch=saved["branch"],
            pushed=True,
            changed_files=changed,
            checks=summary,
        )
    except ManifestInvalid as exc:
        return RunOutcome("refused", EXIT_REFUSED, run_id, reason=f"manifest invalid: {exc}")
    except (ActionsStopped, FencingLost, RunCancelled) as exc:
        return RunOutcome("stopped", EXIT_STOPPED, run_id, reason=getattr(exc, "code", None) or str(exc))
    except PolicyViolation as exc:
        session.reporter.failed("policy_violation", {"error": str(exc), "paths": exc.paths})
        return RunOutcome("failed", EXIT_FAILED, run_id, reason=str(exc))
    except ServerUnreachable as exc:
        return RunOutcome("unknown", EXIT_UNREACHABLE, run_id, reason=f"server unreachable: {exc}")


def server_run_status(client, saved: dict[str, Any]) -> dict[str, Any]:
    """Ask the server for the run status. Unreachable → status 'unknown' + stale last-known value (FR-G07)."""
    try:
        runs = client.list_runs(saved["project_id"], saved["work_item_id"])
    except (ServerUnreachable, ApiError) as exc:
        return {
            "run_id": saved.get("run_id"),
            "status": "unknown",
            "stale": True,
            "last_confirmed_status": saved.get("last_server_status"),
            "last_confirmed_at": saved.get("last_server_contact_at"),
            "error": getattr(exc, "code", None) or str(exc),
        }
    for r in runs:
        if str(r.get("id")) == saved.get("run_id"):
            return {"run_id": saved["run_id"], "status": r.get("status"), "stale": False, "server": r}
    return {"run_id": saved.get("run_id"), "status": "not_found", "stale": False}


def outcome_dict(o: RunOutcome) -> dict[str, Any]:
    return asdict(o)
