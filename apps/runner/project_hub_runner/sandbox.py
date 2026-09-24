# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Subprocess execution for untrusted repository code / external agents.

What this module DOES enforce (stdlib only):

* working directory = the runner-owned worktree;
* environment scrubbed to an allowlist — runner token, run token and any
  platform credential are never passed (``PLANE_*``, ``PH_RUNNER_*`` … are
  dropped even if an operator lists them);
* wall-clock timeout, and immediate kill of the whole process group when the
  run is stopped (fencing lost, cancelled, time limit);
* output captured to a runner-owned log file, only a tail is reported.

What it does NOT enforce (INV-10, honest limit): network egress, filesystem
reads outside the worktree, CPU/memory. The Python standard library cannot
sandbox a process. Those are delegated to the OS/container: configure
``sandbox_prefix`` (e.g. ``["firejail", "--net=none", "--"]``,
``["bwrap", ...]`` or run the whole runner in a container with
``--network none``). :func:`enforcement_report` states what is in effect so
the run events show the actual enforcement boundary.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

BASE_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "TZ",
)
# Never forwarded, whatever the operator configures.
_FORBIDDEN = re.compile(r"(PLANE|PROJECT_HUB|PH_RUNNER|RUNNER_TOKEN|RUN_TOKEN|PH_RUN_TOKEN)", re.IGNORECASE)


def scrub_env(
    passthrough: Iterable[str] = (),
    extra: dict[str, str] | None = None,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    source = dict(os.environ if source is None else source)
    allowed = set(BASE_ENV_ALLOWLIST) | {p for p in passthrough if p}
    env = {k: v for k, v in source.items() if k in allowed and not _FORBIDDEN.search(k)}
    env.setdefault("PATH", os.defpath)
    for k, v in (extra or {}).items():
        env[k] = v
    return env


@dataclass
class ProcessResult:
    argv: list[str]
    exit_code: int | None
    timed_out: bool
    stopped: str | None
    duration_s: float
    output_tail: str
    log_path: str | None


def _kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue


def _feed(pipe, text: str) -> None:
    try:
        pipe.write(text.encode("utf-8"))
        pipe.close()
    except (BrokenPipeError, OSError, ValueError):
        pass


def run_process(
    argv: Sequence[str],
    cwd: str | Path,
    env: dict[str, str],
    timeout: float,
    stop=None,
    log_path: str | Path | None = None,
    stdin_text: str | None = None,
    tail_bytes: int = 4000,
    poll: float = 0.1,
) -> ProcessResult:
    """Run ``argv`` in its own process group; kill on timeout or when ``stop`` is set."""
    start = time.monotonic()
    # Always write to a file (never a PIPE): a chatty child cannot deadlock on a full pipe.
    log_fh = open(log_path, "w+b") if log_path else tempfile.TemporaryFile()  # noqa: SIM115
    out_target = log_fh
    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=out_target,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        log_fh.close()
        return ProcessResult(list(argv), None, False, None, 0.0, f"could not start: {exc}", str(log_path or ""))
    if stdin_text is not None and proc.stdin:
        # Feed stdin from a thread so a child that never reads cannot block the timeout loop.
        threading.Thread(target=_feed, args=(proc.stdin, stdin_text), daemon=True).start()
    timed_out, stopped = False, None
    deadline = start + max(0.0, timeout)
    try:
        while True:
            if proc.poll() is not None:
                break
            if stop is not None and stop.is_set():
                stopped = stop.reason or "stopped"
                _kill_group(proc)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _kill_group(proc)
                break
            time.sleep(poll)
        proc.wait(timeout=10)
        log_fh.flush()
        log_fh.seek(0, os.SEEK_END)
        size = log_fh.tell()
        log_fh.seek(max(0, size - tail_bytes))
        data = log_fh.read()
    finally:
        log_fh.close()
    tail = data[-tail_bytes:].decode("utf-8", "replace")
    exit_code = None if (timed_out or stopped) else proc.returncode
    return ProcessResult(
        list(argv), exit_code, timed_out, stopped, time.monotonic() - start, tail, str(log_path) if log_path else None
    )


def enforcement_report(sandbox_prefix: Sequence[str] = ()) -> dict[str, str]:
    return {
        "paths": "post-run diff filter + server action gate (enforced)",
        "actions": "server action gate + local mirror (enforced)",
        "time": "wall-clock timeout, process-group kill (enforced)",
        "env": "allowlist, platform credentials removed (enforced)",
        "network": f"delegated to OS sandbox: {sandbox_prefix[0]}" if sandbox_prefix else "NOT enforced by runner",
        "filesystem_reads": f"delegated to OS sandbox: {sandbox_prefix[0]}" if sandbox_prefix else "NOT enforced",
        "spend": "agent-reported only (post hoc)",
    }
