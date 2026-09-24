# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Git operations on the runner-owned worktree (FR-G06, FR-G08, K09).

Hard rules implemented here:

* commits carry ``Work-Item:``, ``Revision:`` and ``Run:`` trailers (FR-G08);
* the work branch is pushed only after the server action gate accepted
  ``push_work_branch`` for the current fencing token;
* never force-push (no ``--force``, no ``+`` refspec), never push to the
  target branch, only branches under ``ph/``;
* there is intentionally **no** merge function (K09: merge stays a human gate);
* git hooks are disabled for runner-initiated commits/pushes, so repository
  code only runs through explicitly approved checks.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .errors import GitError, PolicyViolation

WORK_BRANCH_PREFIX = "ph/"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_NO_HOOKS = ["-c", "core.hooksPath=/dev/null"]
RUNNER_IDENTITY = ("Project Hub Runner", "runner@project-hub.invalid")


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def git(cwd: str | Path, *args: str, check: bool = True, timeout: float = 120) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_git_env(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {' '.join(args)} failed: {exc}") from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def rev_parse(cwd: str | Path, rev: str) -> str | None:
    out = git(cwd, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False).strip()
    return out or None


def commit_exists(cwd: str | Path, sha: str) -> bool:
    return rev_parse(cwd, sha) is not None


def toplevel(cwd: str | Path) -> Path:
    return Path(git(cwd, "rev-parse", "--show-toplevel").strip()).resolve()


def work_branch_name(work_item_id: str, run_id: str) -> str:
    short_issue = _SAFE.sub("", work_item_id)[:8] or "item"
    short_run = _SAFE.sub("", run_id)[:8] or "run"
    return f"{WORK_BRANCH_PREFIX}{short_issue}/{short_run}"


def _split_z(out: str) -> list[str]:
    return [x for x in out.split("\0") if x]


def uncommitted_files(workdir: str | Path) -> set[str]:
    out = git(workdir, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
    files: set[str] = set()
    for entry in _split_z(out):
        files.add(entry[3:])
    return files


def committed_files(workdir: str | Path, base: str) -> set[str]:
    out = git(workdir, "diff", "--name-only", "-z", "--no-renames", f"{base}..HEAD")
    return set(_split_z(out))


def changed_files(workdir: str | Path, base: str) -> set[str]:
    """Everything that differs from the approved base: commits, index, worktree, untracked."""
    return committed_files(workdir, base) | uncommitted_files(workdir)


def build_commit_message(subject: str, body: str, work_item_id: str, revision_id: str, run_id: str) -> str:
    subject = (subject or "Project Hub change").strip().splitlines()[0][:72]
    parts = [subject]
    if body and body.strip():
        parts.append(body.strip())
    parts.append(f"Work-Item: {work_item_id}\nRevision: {revision_id}\nRun: {run_id}")
    return "\n\n".join(parts) + "\n"


def commit_all(gate, workdir: str | Path, subject: str, body: str = "") -> str | None:
    """Stage all changes and commit with correlation trailers. Returns the new sha, or None if clean."""
    paths = uncommitted_files(workdir)
    if not paths:
        return None
    rules = gate.rules
    gate.authorize("create_commit", paths=paths)
    message = build_commit_message(subject, body, rules.work_item_id, rules.revision_id, rules.run_id)
    git(workdir, "add", "-A")
    name, email = RUNNER_IDENTITY
    has_name = git(workdir, "config", "user.name", check=False).strip()
    has_email = git(workdir, "config", "user.email", check=False).strip()
    ident = []
    if not has_name:
        ident += ["-c", f"user.name={name}"]
    if not has_email:
        ident += ["-c", f"user.email={email}"]
    _commit_with_message(workdir, [*_NO_HOOKS, *ident], message)
    return rev_parse(workdir, "HEAD")


def _commit_with_message(workdir: str | Path, prefix: list[str], message: str) -> None:
    try:
        proc = subprocess.run(
            ["git", *prefix, "commit", "--no-verify", "-q", "-F", "-"],
            cwd=str(workdir),
            input=message,
            capture_output=True,
            text=True,
            timeout=120,
            env=_git_env(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git commit failed: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"git commit failed: {proc.stderr.strip()}")


def commit_trailers(workdir: str | Path, sha: str) -> dict[str, str]:
    out = git(workdir, "log", "-1", "--format=%(trailers:only,unfold)", sha)
    trailers: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            trailers[key.strip()] = value.strip()
    return trailers


def commits_since(workdir: str | Path, base: str) -> list[str]:
    out = git(workdir, "rev-list", f"{base}..HEAD")
    return [x for x in out.split() if x]


def current_branch(workdir: str | Path) -> str:
    return git(workdir, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip()


def push_work_branch(gate, workdir: str | Path, remote: str, branch: str) -> str:
    """Push the work branch via the server action gate. Returns the pushed head sha."""
    rules = gate.rules
    if not branch.startswith(WORK_BRANCH_PREFIX):
        raise PolicyViolation(f"only {WORK_BRANCH_PREFIX}* work branches may be pushed, not {branch!r}")
    if branch in (rules.target_branch, f"refs/heads/{rules.target_branch}"):
        raise PolicyViolation("pushing to the target branch is never allowed (K09)")
    if current_branch(workdir) != branch:
        raise PolicyViolation(f"worktree is not on the work branch {branch!r}")
    if uncommitted_files(workdir):
        raise PolicyViolation("worktree has uncommitted changes; commit (within allowedPaths) before pushing")
    head = rev_parse(workdir, "HEAD")
    if not head or head == rules.base_commit:
        raise PolicyViolation("nothing to push: no commits on top of the approved base")
    paths = committed_files(workdir, rules.base_commit)
    bad = rules.disallowed_paths(paths)
    if bad:
        # Checked before contacting the server so a violating diff is never announced as pushable.
        raise PolicyViolation(f"commits touch paths outside allowedPaths: {', '.join(bad)}", bad, "push_work_branch")
    gate.authorize(
        "push_work_branch",
        paths=paths,
        detail={"branch": branch, "head_sha": head, "base_commit": rules.base_commit, "remote": remote},
    )
    # No '+' in the refspec and no --force: a non-fast-forward is rejected by git itself.
    git(workdir, *_NO_HOOKS, "push", "--no-verify", "--porcelain", remote, f"refs/heads/{branch}:refs/heads/{branch}")
    return head
