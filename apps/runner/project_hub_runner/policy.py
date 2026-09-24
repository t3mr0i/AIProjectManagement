# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local enforcement mirror of the server policy (FR-G06, AC27, PRD §14.4).

The **server is the authority**: every controlled action is first sent to
``POST R/runs/{id}/actions`` with the current fencing token. Only if the
server accepts it AND the local mirror agrees is the action executed. Local
checks are defense in depth (e.g. against a server bug or a stale cache).

:class:`Rules` is built *exclusively* from the server-issued manifest and is
immutable. Repository content (README, AGENTS.md, skill files, prompts) is
data: nothing in this module ever reads the repository, so it cannot add
actions, paths, checks or budget (AC27).
"""

from __future__ import annotations

import posixpath
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .claim import ClaimHandle, StopSignal
from .errors import (
    ActionRejected,
    ActionsStopped,
    FencingLost,
    Forbidden,
    PolicyViolation,
    RunCancelled,
    RunRefused,
    stop_reason,
)
from .manifest import CheckSpec, Manifest


def normalize_repo_path(path: str) -> str:
    """Normalize a repo-relative path; raise PolicyViolation for anything escaping the repo."""
    if not isinstance(path, str) or not path:
        raise PolicyViolation("empty path", [str(path)])
    p = path.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise PolicyViolation(f"absolute path not allowed: {path}", [path])
    norm = posixpath.normpath(p)
    if norm == ".." or norm.startswith("../"):
        raise PolicyViolation(f"path escapes the repository: {path}", [path])
    if ".git" in norm.split("/"):
        raise PolicyViolation(f"git metadata is never editable: {path}", [path])
    return norm


@lru_cache(maxsize=256)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """``**`` spans directories, ``*``/``?`` stay within one segment.

    A pattern without wildcards matches that file or everything below that
    directory; a trailing ``/`` means "everything below".
    """
    pat = pattern.replace("\\", "/")
    while pat.startswith("./"):
        pat = pat[2:]
    if not any(ch in pat for ch in "*?["):
        base = pat.rstrip("/")
        return re.compile("^" + re.escape(base) + "(?:/.*)?$")
    if pat.endswith("/"):
        pat += "**"
    out, i, n = [], 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if pat.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if pat.startswith("**", i):
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


@dataclass(frozen=True)
class Rules:
    """Immutable, manifest-derived policy for one run and one repository."""

    run_id: str
    work_item_id: str
    revision_id: str
    policy_version: str
    binding_id: str
    base_commit: str
    target_branch: str
    allowed_actions: frozenset[str]
    allowed_paths: tuple[str, ...]
    max_seconds: int
    max_spend_minor: int
    currency: str
    checks: tuple[CheckSpec, ...]
    on_base_moved: str = "wait"

    @classmethod
    def from_manifest(
        cls, manifest: Manifest, binding_id: str | None = None, extra_checks: tuple[CheckSpec, ...] = ()
    ) -> Rules:
        """``extra_checks`` = operator-configured checks (local runner config, never repo content).

        Human-approved manifest checks always win; operator checks are only a fallback when the
        manifest carries none (older servers). Either way each check still needs the server gate
        to accept ``run_allowed_checks`` — current servers reject names not in the manifest.
        """
        scope = manifest.scope_for(binding_id)
        checks = manifest.checks if manifest.checks else tuple(extra_checks)
        return cls(
            run_id=manifest.run_id,
            work_item_id=manifest.work_item_id,
            revision_id=manifest.revision_id,
            policy_version=manifest.policy_version,
            binding_id=scope.binding_id,
            base_commit=scope.base_commit,
            target_branch=scope.target_branch,
            allowed_actions=manifest.allowed_actions,
            allowed_paths=scope.allowed_paths,
            max_seconds=manifest.limits.max_seconds,
            max_spend_minor=manifest.limits.max_spend_minor,
            currency=manifest.limits.currency,
            checks=checks,
            on_base_moved=manifest.on_base_moved,
        )

    def action_allowed(self, action: str) -> bool:
        return action in self.allowed_actions

    def path_allowed(self, path: str) -> bool:
        try:
            norm = normalize_repo_path(path)
        except PolicyViolation:
            return False
        return path_matches(norm, self.allowed_paths)

    def disallowed_paths(self, paths: Iterable[str]) -> list[str]:
        return sorted({p for p in paths if not self.path_allowed(p)})

    def check(self, name: str) -> CheckSpec | None:
        for c in self.checks:
            if c.name == name:
                return c
        return None


class PolicyGate:
    """Server-first action gate + local mirror + stop flag + time/spend budget.

    This is the ``policy`` object handed to agent adapters. Adapters can read
    ``gate.rules`` but cannot change it (frozen dataclass), and every
    side-effecting step must go through :meth:`authorize`.
    """

    def __init__(
        self,
        rules: Rules,
        client,
        run_token: str,
        claim: ClaimHandle,
        stop: StopSignal,
        clock=time.monotonic,
    ):
        self._rules = rules
        self._client = client
        self._run_token = run_token
        self._claim = claim
        self.stop = stop
        self._clock = clock
        self.started_at = clock()
        self.spent_minor = 0
        self.log: list[dict[str, Any]] = []

    @property
    def rules(self) -> Rules:
        return self._rules

    @property
    def run_id(self) -> str:
        return self._rules.run_id

    @property
    def fencing_token(self) -> int:
        return self._claim.fencing_token

    @property
    def stopped(self) -> bool:
        return self.stop.is_set()

    def remaining_seconds(self) -> float:
        return self._rules.max_seconds - (self._clock() - self.started_at)

    def ensure_active(self) -> None:
        if self.stop.is_set():
            raise ActionsStopped(self.stop.reason or "stopped")
        if self.remaining_seconds() <= 0:
            self.stop.trigger("time_limit")
            raise ActionsStopped("time_limit")

    def authorize(
        self,
        action: str,
        paths: Iterable[str] | None = None,
        spend_minor: int = 0,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ask the server first, then check locally. Raises on any refusal."""
        self.ensure_active()
        path_list = sorted(set(paths or []))
        body = dict(detail or {})
        if path_list:
            body["paths"] = path_list
        if spend_minor:
            body["spend_minor"] = int(spend_minor)
        body.setdefault("binding_id", self._rules.binding_id)
        try:
            resp = self._client.request_action(self.run_id, self._run_token, action, self.fencing_token, body)
        except FencingLost as exc:
            self.stop.trigger(exc.code)
            raise
        except RunCancelled as exc:
            self.stop.trigger(stop_reason(exc))
            raise
        except (RunRefused, Forbidden) as exc:
            # Approval revoked/expired, native source changed, project archived, capability lost:
            # the basis of the run is gone — stop everything (FR-B06, FR-B07, FR-I07).
            self.stop.trigger(exc.code)
            self.log.append({"action": action, "accepted": False, "by": "server", "reason": exc.code})
            raise ActionsStopped(exc.code) from exc
        except ActionRejected as exc:
            self.log.append({"action": action, "accepted": False, "by": "server", "reason": exc.code})
            raise PolicyViolation(f"server rejected {action}: {exc.code} {exc.message}", path_list, action) from exc
        if not resp.get("accepted", False):
            self.log.append({"action": action, "accepted": False, "by": "server", "reason": resp.get("reason")})
            raise PolicyViolation(f"server did not accept {action}: {resp.get('reason')}", path_list, action)
        # Defense in depth — the local mirror must agree too.
        self._local_check(action, path_list, spend_minor)
        self.spent_minor += int(spend_minor or 0)
        self.log.append({"action": action, "accepted": True, "paths": path_list})
        return resp

    def _local_check(self, action: str, paths: list[str], spend_minor: int) -> None:
        if not self._rules.action_allowed(action):
            self.log.append({"action": action, "accepted": False, "by": "local", "reason": "action_not_allowed"})
            raise PolicyViolation(f"action {action!r} is not in the approved allowedActions", paths, action)
        bad = self._rules.disallowed_paths(paths)
        if bad:
            self.log.append({"action": action, "accepted": False, "by": "local", "reason": "paths", "paths": bad})
            raise PolicyViolation(f"paths outside allowedPaths: {', '.join(bad)}", bad, action)
        if self.spent_minor + int(spend_minor or 0) > self._rules.max_spend_minor:
            self.stop.trigger("spend_limit")
            raise PolicyViolation("spend limit exceeded", paths, action)
        self.ensure_active()

    def record_spend(self, spend_minor: int, source: str = "agent") -> None:
        """Account spend reported by an adapter. Exceeding the limit stops the run."""
        if spend_minor <= 0:
            return
        self.spent_minor += int(spend_minor)
        if self.spent_minor > self._rules.max_spend_minor:
            self.stop.trigger("spend_limit")
