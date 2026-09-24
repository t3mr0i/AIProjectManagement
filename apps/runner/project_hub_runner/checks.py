# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Execute approved checks (``run_allowed_checks``).

Only checks listed in the server manifest can run, with their fixed argv
from the manifest. A repository file cannot add or alter a check (AC27).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .errors import ActionsStopped, PolicyViolation
from .reporter import CheckResult
from .sandbox import run_process, scrub_env


def run_check(
    gate,
    name: str,
    workdir: str | Path,
    log_dir: str | Path | None = None,
    env_passthrough: Iterable[str] = (),
    sandbox_prefix: Iterable[str] = (),
) -> CheckResult:
    spec = gate.rules.check(name)
    if spec is None:
        return CheckResult(name, [], executed=False, exit_code=None, reason="not in approved checks")
    if not gate.rules.action_allowed("run_allowed_checks"):
        return CheckResult(
            name, list(spec.command), executed=False, exit_code=None, reason="run_allowed_checks not allowed"
        )
    try:
        gate.authorize("run_allowed_checks", detail={"check": name, "command": list(spec.command)})
    except (PolicyViolation, ActionsStopped) as exc:
        return CheckResult(name, list(spec.command), executed=False, exit_code=None, reason=str(exc))
    timeout = gate.remaining_seconds()
    if spec.timeout_seconds:
        timeout = min(timeout, spec.timeout_seconds)
    log_path = None
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"check-{name}.log"
    argv = list(spec.command) if spec.trusted else [*sandbox_prefix, *spec.command]
    res = run_process(argv, workdir, scrub_env(env_passthrough), timeout, stop=gate.stop, log_path=log_path)
    executed = res.exit_code is not None or res.timed_out
    reason = ""
    if res.stopped:
        reason = f"stopped: {res.stopped}"
        executed = False
    elif res.exit_code is None and not res.timed_out:
        reason = res.output_tail
    return CheckResult(
        name=name,
        command=list(spec.command),
        executed=executed,
        exit_code=res.exit_code,
        timed_out=res.timed_out,
        duration_s=res.duration_s,
        output_tail=res.output_tail,
        reason=reason,
    )
