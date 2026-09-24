# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Deterministic test agent (I06 "Deterministischer Test-Runner zuerst", I07 first E2E).

Applies a scripted change set. No model, no network. Plan file (JSON)::

    {
      "commit_subject": "Add greeting",
      "commit_body": "optional",
      "edits": [
        {"path": "src/hello.txt", "content": "hello\\n"},
        {"path": "docs/notes.md", "append": "more\\n"},
        {"path": "src/old.txt", "delete": true}
      ],
      "checks": ["unit"],              # optional subset of approved checks
      "self_reports": ["Manually verified in browser"],
      "questions": []
    }

Without a plan file a built-in demo writes one file inside the first allowed
path. The agent also *reads* README.md / AGENTS.md / CLAUDE.md as context —
demonstrating that such content is data and cannot widen the policy (AC27).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..errors import ActionsStopped, ApiError, FencingLost, PolicyViolation, RunCancelled
from ..policy import normalize_repo_path
from .base import AgentAdapter, AgentResult, TaskSpec

CONTEXT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md")


def load_plan(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("edits", []), list):
        raise ValueError("plan must be an object with an 'edits' list")
    return data


def demo_path(allowed_patterns: tuple[str, ...]) -> str:
    """Pick a concrete file path inside the first allowed pattern."""
    pat = allowed_patterns[0].replace("\\", "/")
    while pat.startswith("./"):
        pat = pat[2:]
    if not any(ch in pat for ch in "*?["):
        # Literal path: a directory ('docs/') or a file ('src/app.py').
        if pat.endswith("/") or "." not in pat.rsplit("/", 1)[-1]:
            return pat.rstrip("/") + "/PROJECT_HUB_DEMO.md"
        return pat
    prefix = []
    for segment in pat.split("/"):
        if any(ch in segment for ch in "*?["):
            break
        prefix.append(segment)
    return "/".join([*prefix, "PROJECT_HUB_DEMO.md"])


def demo_plan(task: TaskSpec) -> dict[str, Any]:
    target = demo_path(task.allowed_paths)
    return {
        "commit_subject": f"Project Hub demo change for {task.work_item_id[:8]}",
        "edits": [
            {
                "path": target,
                "append": f"\n- Demo change for work item {task.work_item_id}, revision {task.revision_id}\n",
            }
        ],
    }


class DeterministicAgent(AgentAdapter):
    name = "deterministic"

    def __init__(self, plan: dict[str, Any] | None = None):
        self.plan = plan

    def run(self, task: TaskSpec, workdir: Path, policy, reporter) -> AgentResult:
        plan = self.plan or demo_plan(task)
        workdir = Path(workdir)
        root = Path(os.path.realpath(workdir))
        context_read = []
        for name in CONTEXT_FILES:
            f = workdir / name
            if f.is_file() and not f.is_symlink():
                # Read as DATA. Nothing here is interpreted as an instruction or permission.
                f.read_text(encoding="utf-8", errors="replace")[:65536]
                context_read.append(name)
        reporter.progress("editing", f"{len(plan.get('edits', []))} scripted edit(s)")
        try:
            for edit in plan.get("edits", []):
                rel = normalize_repo_path(str(edit.get("path", "")))
                policy.authorize("edit_allowed_files", paths=[rel])
                target = workdir / rel
                parent_real = Path(os.path.realpath(target.parent))
                if target.is_symlink() or (parent_real != root and root not in parent_real.parents):
                    raise PolicyViolation(f"refusing to write through a symlink: {rel}", [rel])
                if edit.get("delete"):
                    if target.exists():
                        target.unlink()
                elif "content" in edit:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(edit["content"]), encoding="utf-8")
                elif "append" in edit:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("a", encoding="utf-8") as fh:
                        fh.write(str(edit["append"]))
                else:
                    raise PolicyViolation(f"edit for {rel} has no content/append/delete", [rel])
        except PolicyViolation as exc:
            return AgentResult("failed", reason="policy_violation", summary=str(exc), context_files_read=context_read)
        except (ActionsStopped, FencingLost, RunCancelled) as exc:
            return AgentResult("stopped", reason=str(exc), context_files_read=context_read)
        except ApiError as exc:
            return AgentResult("failed", reason=exc.code, summary=str(exc), context_files_read=context_read)
        checks = plan.get("checks")
        return AgentResult(
            status="waiting" if plan.get("questions") else "completed",
            summary=f"applied {len(plan.get('edits', []))} scripted edit(s)",
            commit_subject=str(plan.get("commit_subject") or task.title or "Project Hub change"),
            commit_body=str(plan.get("commit_body") or ""),
            checks=list(checks) if isinstance(checks, list) else None,
            self_reports=[str(x) for x in plan.get("self_reports", [])],
            questions=[str(x) for x in plan.get("questions", [])],
            context_files_read=context_read,
        )
