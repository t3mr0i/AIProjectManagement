# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""``ph-runner`` command line (FR-G03: one CLI contract for all IDE workflows).

Exit codes: 0 ok · 1 error · 2 refused/invalid · 3 waiting/claim held ·
4 failed (policy/workspace) · 5 stopped (fencing lost / cancelled) ·
6 server unreachable (state unknown).
"""

from __future__ import annotations

import argparse
import json
import shlex
import signal
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .claim import ClaimHandle, StopSignal, Supervisor, acquire_claim, heartbeat_once, release_claim
from .client import Client
from .config import default_config_path, load_config, login, mask_token
from .errors import ApiError, ClaimHeld, FencingLost, NotFound, RunCancelled, RunnerError, ServerUnreachable
from .runner import (
    EXIT_OK,
    EXIT_STOPPED,
    EXIT_UNREACHABLE,
    RunRequest,
    cancel_checker,
    execute_run,
    outcome_dict,
    push_human_run,
    resume_session,
    server_run_status,
)
from .state import StateStore


def _print(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, default=str))
    elif isinstance(data, dict):
        for k, v in data.items():
            print(f"{k}: {v}")
    else:
        print(data)


def _ctx(args):
    cfg = load_config(default_config_path() if not args.config else Path(args.config))
    return cfg, Client.from_config(cfg), StateStore(cfg.home)


# ------------------------------------------------------------------ commands


def cmd_login(args) -> int:
    path = login(
        args.server,
        args.workspace,
        args.token,
        path=Path(args.config) if args.config else None,
        allow_insecure_http=args.insecure_http,
        runner_home=args.runner_home or "",
    )
    print(f"saved runner config to {path} (mode 0600)")
    return EXIT_OK


def cmd_whoami(args) -> int:
    cfg, client, _ = _ctx(args)
    info: dict[str, Any] = {"server": cfg.server, "workspace": cfg.workspace, "token": mask_token(cfg.token)}
    try:
        info["server_identity"] = client.whoami()
    except NotFound:
        info["server_identity"] = "not supported by this server (config only)"
    except ServerUnreachable as exc:
        info["server_identity"] = f"unknown (server unreachable: {exc})"
        _print(info, args.json)
        return EXIT_UNREACHABLE
    _print(info, args.json)
    return EXIT_OK


def cmd_claim(args) -> int:
    cfg, client, state = _ctx(args)
    try:
        claim = acquire_claim(
            client,
            args.project,
            args.work_item,
            args.repo or None,
            not args.shared,
            args.lease_seconds or cfg.lease_seconds,
        )
    except ClaimHeld as exc:
        _print({"status": "claim_held", "holder": exc.holder}, args.json)
        return exc.exit_code
    state.save_claim(claim.id, claim.to_state())
    _print({"status": "claimed", **claim.to_state()}, args.json)
    if not args.hold:
        return EXIT_OK
    return _hold(client, claim, state, cfg.heartbeat_interval, release_on_exit=True)


def _hold(client, claim: ClaimHandle, state: StateStore, interval: float, release_on_exit: bool, cancel=None) -> int:
    stop = StopSignal()
    sup = Supervisor(client, claim, stop, interval=interval or None, cancel_check=cancel)
    sup.start()
    signal.signal(signal.SIGTERM, lambda *_: stop.trigger("terminated"))
    print("holding lease (Ctrl-C to stop)…", file=sys.stderr)
    try:
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        stop.trigger("interrupted")
    sup.halt()
    reason = stop.reason or ""
    if release_on_exit and reason in ("interrupted", "terminated"):
        release_claim(client, claim)
        state.delete("claims", claim.id)
        return EXIT_OK
    print(f"stopped: {reason}", file=sys.stderr)
    return EXIT_OK if reason in ("interrupted", "terminated") else EXIT_STOPPED


def _claim_from(args, state: StateStore) -> tuple[ClaimHandle, dict[str, Any] | None]:
    if getattr(args, "run", None):
        saved = state.load_run(args.run)
        if not saved:
            raise RunnerError(f"no local state for run {args.run}")
        return ClaimHandle.from_state(saved["claim"]), saved
    saved_claim = state.load_claim(args.claim) if args.claim else None
    if not saved_claim:
        raise RunnerError("pass --claim ID or --run ID of a claim/run started by this runner")
    return ClaimHandle.from_state(saved_claim), None


def cmd_heartbeat(args) -> int:
    cfg, client, state = _ctx(args)
    claim, saved = _claim_from(args, state)
    if args.watch:
        cancel = cancel_checker(client, saved["project_id"], saved["work_item_id"], saved["run_id"]) if saved else None
        return _hold(client, claim, state, cfg.heartbeat_interval, release_on_exit=False, cancel=cancel)
    try:
        resp = heartbeat_once(client, claim)
    except FencingLost as exc:
        _print({"status": "lost", "code": exc.code}, args.json)
        return EXIT_STOPPED
    _print({"status": "ok", **(resp or {})}, args.json)
    return EXIT_OK


def cmd_release(args) -> int:
    _, client, state = _ctx(args)
    claim, saved = _claim_from(args, state)
    ok = release_claim(client, claim)
    state.delete("claims", claim.id)
    if saved:
        state.update("runs", saved["run_id"], local_status="released")
    _print({"released": ok, "claim_id": claim.id}, args.json)
    return EXIT_OK if ok else EXIT_UNREACHABLE


def cmd_cancel_check(args) -> int:
    _, client, state = _ctx(args)
    saved = state.load_run(args.run)
    if not saved:
        raise RunnerError(f"no local state for run {args.run}")
    status = server_run_status(client, saved)
    _print(status, args.json)
    if status["status"] == "unknown":
        return EXIT_UNREACHABLE
    return EXIT_STOPPED if status["status"] == "cancelled" else EXIT_OK


def cmd_report(args) -> int:
    cfg, client, state = _ctx(args)
    session, _ = resume_session(cfg, client, state, args.run)
    r = session.reporter
    try:
        if args.progress:
            r.progress(args.progress, args.message or "", force=True)
        if args.question:
            r.question(args.question)
        if args.waiting:
            r.waiting(args.waiting)
        if args.self_report:
            head = None
            saved = state.load_run(args.run) or {}
            if saved.get("worktree"):
                from .git_ops import rev_parse

                head = rev_parse(saved["worktree"], "HEAD")
            r.self_report(args.self_report, head)
    except (FencingLost, RunCancelled) as exc:
        _print({"status": "stopped", "code": exc.code}, args.json)
        return EXIT_STOPPED
    _print({"sent": len(r.sent), "unsent": [u.get("error") for u in r.unsent]}, args.json)
    return EXIT_OK if not r.unsent else EXIT_UNREACHABLE


def cmd_push(args) -> int:
    cfg, client, state = _ctx(args)
    outcome = push_human_run(cfg, client, args.run, run_checks_flag=args.run_checks, state=state)
    _print(outcome_dict(outcome), args.json)
    return outcome.exit_code


def cmd_status(args) -> int:
    _, client, state = _ctx(args)
    runs = state.list("runs")
    if args.run:
        runs = [r for r in runs if r.get("run_id") == args.run]
    rows = []
    worst = EXIT_OK
    for saved in runs:
        s = server_run_status(client, saved)
        if s["status"] == "unknown":
            worst = EXIT_UNREACHABLE
            last_at = s.get("last_confirmed_at")
            s["note"] = (
                "server unreachable: current state UNKNOWN; last confirmed "
                f"{s.get('last_confirmed_status')!r} at "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(last_at)) if last_at else 'never'} (stale)"
            )
        else:
            state.update("runs", saved["run_id"], last_server_status=s["status"], last_server_contact_at=time.time())
        s.pop("server", None)
        s.update(
            {
                "local_status": saved.get("local_status"),
                "worktree": saved.get("worktree"),
                "branch": saved.get("branch"),
            }
        )
        rows.append(s)
    if args.json:
        _print(rows, True)
    else:
        if not rows:
            print("no runs started by this runner")
        for s in rows:
            line = f"{s['run_id']}  server={s['status']}  local={s['local_status']}  branch={s.get('branch')}"
            print(line + (f"\n  {s['note']}" if s.get("note") else ""))
    return worst


def cmd_run(args) -> int:
    cfg, client, state = _ctx(args)
    req = RunRequest(
        project_id=args.project,
        work_item_id=args.work_item,
        approval_id=args.approval,
        binding_id=args.repo or None,
        repo_path=args.repo_path,
        remote=args.remote,
        mode=args.mode,
        adapter=args.adapter,
        push=not args.no_push,
        exclusive=not args.shared,
        lease_seconds=args.lease_seconds,
        claim_id=args.claim,
        fetch=not args.no_fetch,
    )
    agent_command = shlex.split(args.agent_command) if args.agent_command else None
    outcome = execute_run(cfg, client, req, plan_path=args.plan, agent_command=agent_command, state=state)
    _print(outcome_dict(outcome), args.json)
    return outcome.exit_code


# -------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ph-runner", description="Project Hub external runner")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", help="config file (default ~/.config/project-hub/runner.json or $PH_RUNNER_CONFIG)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="store server URL, workspace and runner token (0600)")
    s.add_argument("--server", required=True)
    s.add_argument("--workspace", required=True)
    s.add_argument("--token", required=True, help="runner token from W/runners/ registration (shown once)")
    s.add_argument("--runner-home", help="runner-owned directory for worktrees/state/logs")
    s.add_argument("--insecure-http", action="store_true", help="allow plain http to a non-local server")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("whoami", help="show configured identity")
    s.set_defaults(func=cmd_whoami)

    s = sub.add_parser("claim", help="atomically claim a work item (/repo unit)")
    s.add_argument("--project", required=True)
    s.add_argument("--work-item", required=True)
    s.add_argument("--repo", help="repository binding id")
    s.add_argument("--shared", action="store_true", help="explicitly collaborative (non-exclusive) claim")
    s.add_argument("--lease-seconds", type=int)
    s.add_argument("--hold", action="store_true", help="keep heartbeating in the foreground until Ctrl-C")
    s.set_defaults(func=cmd_claim)

    s = sub.add_parser("run", help="claim → start run → manifest → worktree → adapter → evidence → push")
    s.add_argument("--project", required=True)
    s.add_argument("--work-item", required=True)
    s.add_argument("--approval", required=True, help="execution approval id")
    s.add_argument("--repo", help="repository binding id (required if the approval spans several repos)")
    s.add_argument("--repo-path", help="local clone used as object store (default: bindings in config)")
    s.add_argument("--remote", help="git remote for the work branch (default origin)")
    s.add_argument("--mode", choices=["agent", "human"], default="agent")
    s.add_argument("--adapter", choices=["deterministic", "external"], default="deterministic")
    s.add_argument("--plan", help="deterministic agent plan (JSON)")
    s.add_argument("--agent-command", help="external agent command, e.g. 'claude -p' (overrides config)")
    s.add_argument("--claim", help="reuse a claim from `ph-runner claim`")
    s.add_argument("--shared", action="store_true")
    s.add_argument("--lease-seconds", type=int)
    s.add_argument("--no-push", action="store_true")
    s.add_argument("--no-fetch", action="store_true", help="do not fetch the target branch before the base check")
    s.set_defaults(func=cmd_run)

    for name, helptext in (("heartbeat", "renew a lease"), ("release", "release a claim")):
        s = sub.add_parser(name, help=helptext)
        g = s.add_mutually_exclusive_group(required=True)
        g.add_argument("--claim")
        g.add_argument("--run")
        if name == "heartbeat":
            s.add_argument("--watch", action="store_true", help="keep renewing until stopped/cancelled")
            s.set_defaults(func=cmd_heartbeat)
        else:
            s.set_defaults(func=cmd_release)

    s = sub.add_parser("cancel-check", help="exit 5 if the run was cancelled, 6 if unknown")
    s.add_argument("--run", required=True)
    s.set_defaults(func=cmd_cancel_check)

    s = sub.add_parser("report", help="report progress / question / waiting / self-report for a run")
    s.add_argument("--run", required=True)
    s.add_argument("--progress", metavar="PHASE")
    s.add_argument("--message")
    s.add_argument("--question")
    s.add_argument("--waiting", metavar="REASON")
    s.add_argument("--self-report", metavar="TEXT", help="developer claim (trust: local_self_report)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("push", help="human mode: verify commits against policy, push work branch, finish")
    s.add_argument("--run", required=True)
    s.add_argument("--run-checks", action="store_true", help="run approved checks first (runner_reported)")
    s.set_defaults(func=cmd_push)

    s = sub.add_parser("status", help="runs started by this runner, as confirmed by the server")
    s.add_argument("--run")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ServerUnreachable as exc:
        print(f"error: server unreachable — state unknown ({exc})", file=sys.stderr)
        return EXIT_UNREACHABLE
    except ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
