# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run a configured external coding-agent CLI (e.g. ``claude -p``) as a subprocess.

* cwd = the runner-owned worktree;
* env scrubbed to an allowlist (+ operator ``env_passthrough``); runner and
  run tokens and platform credentials are never passed;
* timeout = remaining ``limits.maxSeconds``; the process group is killed on
  timeout, cancellation or fencing loss;
* the prompt (approved task text) is passed on stdin and as ``PH_TASK_FILE``;
* the command comes from local operator configuration, never from the repo.

Network isolation is NOT enforced here (INV-10): the stdlib cannot sandbox a
process. Configure ``sandbox_prefix`` or run the runner in a container with
networking disabled. The post-run diff filter in the orchestrator enforces
allowedPaths regardless of what the agent did: violating files fail the run
and nothing is committed or pushed.

Spend: if the agent writes ``{"spend_minor": N}`` to ``PH_SPEND_FILE`` it is
accounted against ``limits.maxSpendMinor`` (agent-reported, post hoc).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ..errors import ActionsStopped, FencingLost, PolicyViolation, RunCancelled
from ..sandbox import run_process, scrub_env
from .base import AgentAdapter, AgentResult, TaskSpec


class ExternalCommandAgent(AgentAdapter):
    name = "external_command"

    def __init__(
        self,
        argv: Sequence[str],
        log_dir: str | Path,
        env_passthrough: Sequence[str] = (),
        sandbox_prefix: Sequence[str] = (),
        prompt_via_stdin: bool = True,
        source_env: dict[str, str] | None = None,
    ):
        if not argv:
            raise ValueError("external agent command is empty; set agent_command in runner.json or --agent-command")
        self.argv = list(argv)
        self.log_dir = Path(log_dir)
        self.env_passthrough = list(env_passthrough)
        self.sandbox_prefix = list(sandbox_prefix)
        self.prompt_via_stdin = prompt_via_stdin
        self._source_env = source_env
        self.last_env: dict[str, str] | None = None

    def build_env(self, task: TaskSpec, task_file: Path, spend_file: Path) -> dict[str, str]:
        return scrub_env(
            self.env_passthrough,
            extra={
                "PH_TASK_FILE": str(task_file),
                "PH_SPEND_FILE": str(spend_file),
                "PH_WORK_ITEM_ID": task.work_item_id,
                "PH_REVISION_ID": task.revision_id,
                "PH_RUN_ID": task.run_id,
            },
            source=self._source_env,
        )

    def run(self, task: TaskSpec, workdir: Path, policy, reporter) -> AgentResult:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        task_file = self.log_dir / "task.json"
        spend_file = self.log_dir / "spend.json"
        prompt = task.prompt()
        task_file.write_text(json.dumps({"prompt": prompt, "task": task.__dict__}, indent=2, default=list))
        try:
            policy.authorize("edit_allowed_files", detail={"agent": self.name, "command": self.argv[0]})
        except PolicyViolation as exc:
            return AgentResult("failed", reason="policy_violation", summary=str(exc))
        except (ActionsStopped, FencingLost, RunCancelled) as exc:
            return AgentResult("stopped", reason=str(exc))
        env = self.build_env(task, task_file, spend_file)
        self.last_env = env
        reporter.progress("agent_running", f"external agent {Path(self.argv[0]).name}")
        res = run_process(
            [*self.sandbox_prefix, *self.argv],
            cwd=workdir,
            env=env,
            timeout=policy.remaining_seconds(),
            stop=policy.stop,
            log_path=self.log_dir / "agent.log",
            stdin_text=prompt if self.prompt_via_stdin else None,
        )
        spend = _read_spend(spend_file)
        if spend:
            policy.record_spend(spend, source=self.name)
        questions = [
            line.split("QUESTION:", 1)[1].strip() for line in res.output_tail.splitlines() if "QUESTION:" in line
        ]
        if res.stopped:
            return AgentResult("stopped", reason=res.stopped, summary=res.output_tail[-1000:], spend_minor=spend)
        if res.timed_out:
            policy.stop.trigger("time_limit")
            return AgentResult("failed", reason="timeout", summary=res.output_tail[-1000:], spend_minor=spend)
        if policy.stopped:
            return AgentResult("stopped", reason=policy.stop.reason or "stopped", spend_minor=spend)
        if res.exit_code != 0:
            return AgentResult(
                "failed", reason=f"agent_exit_{res.exit_code}", summary=res.output_tail[-1000:], spend_minor=spend
            )
        return AgentResult(
            "waiting" if questions else "completed",
            summary=res.output_tail[-1000:],
            commit_subject=task.title or "Project Hub change",
            questions=questions,
            spend_minor=spend,
        )


def _read_spend(path: Path) -> int:
    try:
        data = json.loads(path.read_text())
        return max(0, int(data.get("spend_minor", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0
