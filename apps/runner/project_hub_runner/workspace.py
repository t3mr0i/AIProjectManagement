# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runner-owned git worktree preparation (FR-G02, INV-01, INV-04).

A worktree is created **only** for a run that the server started and whose
manifest validated (the caller passes the :class:`PolicyGate` of that run,
and ``prepare_worktree`` is sent through the server action gate first). There
is no code path that prepares a worktree from a draft.

The worktree lives in a runner-owned directory
(``<runner_home>/worktrees/<binding>/<run>``), never in the developer's own
working directory. The developer's clone is only used as the object store.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import git_ops
from .errors import BaseMoved, GitError, WorkspaceError


@dataclass(frozen=True)
class PreparedWorkspace:
    path: Path
    branch: str
    base_commit: str
    target_branch: str
    target_head: str | None
    repo_path: Path
    remote: str


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def target_head(repo: Path, remote: str, target_branch: str, fetch: bool = True) -> str | None:
    """Current head of the target branch as far as we can observe it (remote-tracking first)."""
    if fetch and remote in git_ops.git(repo, "remote", check=False).split():
        # Best effort: a failed fetch must not be mistaken for "unchanged" — we fall back to what we have.
        git_ops.git(repo, "fetch", "--quiet", "--no-tags", remote, target_branch, check=False, timeout=300)
    for ref in (f"refs/remotes/{remote}/{target_branch}", f"refs/heads/{target_branch}"):
        sha = git_ops.rev_parse(repo, ref)
        if sha:
            return sha
    return None


def prepare_worktree(
    gate,
    repo_path: str | Path,
    runner_home: str | Path,
    remote: str = "origin",
    fetch: bool = True,
) -> PreparedWorkspace:
    rules = gate.rules
    repo = Path(repo_path).expanduser().resolve()
    home = Path(runner_home).expanduser().resolve()
    if not (repo / ".git").exists():
        raise WorkspaceError(f"{repo} is not a git clone")
    repo_top = git_ops.toplevel(repo)
    worktree = home / "worktrees" / _safe(rules.binding_id) / _safe(rules.run_id)
    if _is_within(worktree, repo_top):
        raise WorkspaceError("runner_home must not be inside the repository working tree (FR-G02)")
    if _is_within(Path.cwd(), worktree):
        raise WorkspaceError("refusing to create a worktree at the current working directory")
    if worktree.exists():
        raise WorkspaceError(f"worktree path already exists: {worktree}")

    base = rules.base_commit
    if not git_ops.commit_exists(repo, base):
        if remote in git_ops.git(repo, "remote", check=False).split():
            git_ops.git(repo, "fetch", "--quiet", "--no-tags", remote, base, check=False, timeout=300)
        if not git_ops.commit_exists(repo, base):
            raise WorkspaceError(f"approved baseCommit {base} does not exist in {repo}")

    head = target_head(repo, remote, rules.target_branch, fetch=fetch)
    if head is not None and head != base and rules.on_base_moved != "continue":
        # INV-04: the approved basis changed; a human must decide (rebase / re-approve).
        raise BaseMoved(base, head, rules.target_branch)

    branch = git_ops.work_branch_name(rules.work_item_id, rules.run_id)
    if git_ops.rev_parse(repo, f"refs/heads/{branch}"):
        raise WorkspaceError(f"work branch {branch} already exists")

    gate.authorize(
        "prepare_worktree",
        detail={"base_commit": base, "branch": branch, "target_branch": rules.target_branch, "target_head": head},
    )
    worktree.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(home, 0o700)
    except OSError:
        pass
    try:
        git_ops.git(repo, "worktree", "add", "--quiet", "-b", branch, str(worktree), base)
    except GitError as exc:
        raise WorkspaceError(str(exc)) from exc
    return PreparedWorkspace(worktree, branch, base, rules.target_branch, head, repo_top, remote)


def remove_worktree(ws: PreparedWorkspace, delete_branch: bool = False) -> None:
    git_ops.git(ws.repo_path, "worktree", "remove", "--force", str(ws.path), check=False)
    if delete_branch:
        git_ops.git(ws.repo_path, "branch", "-D", ws.branch, check=False)


def _safe(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_")[:64] or "x"
