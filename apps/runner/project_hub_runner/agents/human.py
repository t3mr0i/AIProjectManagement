# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Human mode: the runner prepares the worktree and hands over to the developer's IDE.

The developer edits in the runner-owned worktree with their IDE, commits,
and uses ``ph-runner report`` / ``ph-runner push`` (VS Code tasks and
JetBrains External Tools in ``apps/runner/ide/`` call exactly these).
Nothing is observed beyond what the developer reports through the runner
(INV-09: no hidden monitoring of private working directories).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from .base import AgentAdapter, AgentResult, TaskSpec


class HumanAdapter(AgentAdapter):
    name = "human"

    def __init__(self, out: TextIO | None = None):
        self.out = out or sys.stdout

    def run(self, task: TaskSpec, workdir: Path, policy, reporter) -> AgentResult:
        run = task.run_id
        print(
            "\n".join(
                [
                    "",
                    f"Worktree ready: {workdir}",
                    f"Task: {task.title or '(untitled)'}  (work item {task.work_item_id}, revision {task.revision_id})",
                    f"Allowed paths: {', '.join(task.allowed_paths)}",
                    "",
                    "Next steps:",
                    f"  1. open {workdir} in your IDE (not your usual checkout)",
                    f"  2. keep the lease alive:  ph-runner heartbeat --run {run} --watch",
                    f"  3. report progress/questions:  ph-runner report --run {run} --progress 'implementing'",
                    "  4. commit your changes in the worktree",
                    f"  5. hand over:  ph-runner push --run {run} [--run-checks]",
                    "",
                ]
            ),
            file=self.out,
        )
        reporter.progress("handed_off", "developer works in IDE", force=True)
        return AgentResult("handed_off", summary="worktree prepared for human mode")
