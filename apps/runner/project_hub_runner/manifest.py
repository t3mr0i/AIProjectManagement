# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Immutable run manifest: fetch, normalize, validate (INV-01, INV-03, INV-04).

The manifest is issued by the server for exactly one run and is the *only*
source of the runner's policy. The runner refuses to act if:

* required fields are missing or malformed;
* the revision is a draft / not approved, or no approval is attached (INV-01, AC01);
* the approval was not given by a human principal (INV-03), is revoked or expired;
* the manifest does not belong to the run / work item we claimed;
* a ``manifestHash`` is present and does not match the content.

Accepted spelling: camelCase (JSON-schema transport contract) or snake_case
(REST); keys are normalized to camelCase.

Manifest hash canonicalization (if the server sends ``manifestHash`` /
``manifest_hash``): SHA-256 hex over ``json.dumps(payload_without_hash,
sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")``
computed on the payload exactly as received (before key normalization).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import ManifestInvalid

ALLOWED_ACTIONS = frozenset(
    {
        "prepare_worktree",
        "edit_allowed_files",
        "run_allowed_checks",
        "create_commit",
        "push_work_branch",
        "open_merge_request",
    }
)
APPROVED_REVISION_STATES = frozenset({"approved"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_CHECK_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _camel(key: str) -> str:
    if "_" not in key:
        return key
    head, *rest = key.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def normalize_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {_camel(str(k)): normalize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_keys(v) for v in value]
    return value


def canonical_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k not in ("manifestHash", "manifest_hash")}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_dt(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ManifestInvalid(f"{name} missing")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManifestInvalid(f"{name} is not an ISO timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class RepoScope:
    binding_id: str
    base_commit: str
    target_branch: str
    allowed_paths: tuple[str, ...]


@dataclass(frozen=True)
class CheckSpec:
    """An approved check: fixed argv from the manifest, never from the repository."""

    name: str
    command: tuple[str, ...]
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class Limits:
    max_seconds: int
    max_spend_minor: int
    currency: str


@dataclass(frozen=True)
class Approval:
    id: str
    approved_by_kind: str
    approved_by: str
    approved_at: str
    expires_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class TaskText:
    """Human-approved task text. It is DATA for the agent, never a source of permissions."""

    title: str = ""
    intent: str = ""
    outcome: str = ""
    criteria: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    run_id: str
    workspace_id: str
    project_id: str
    work_item_id: str
    revision_id: str
    revision_hash: str
    policy_version: str
    approval: Approval
    repository_scope: tuple[RepoScope, ...]
    allowed_actions: frozenset[str]
    limits: Limits
    checks: tuple[CheckSpec, ...] = ()
    task: TaskText = field(default_factory=TaskText)
    on_base_moved: str = "wait"  # wait (INV-04: human decides) | continue
    manifest_hash: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def scope_for(self, binding_id: str | None) -> RepoScope:
        if binding_id is None:
            if len(self.repository_scope) != 1:
                raise ManifestInvalid("manifest has several repositories; pass --repo BINDING")
            return self.repository_scope[0]
        for scope in self.repository_scope:
            if scope.binding_id == binding_id:
                return scope
        raise ManifestInvalid(f"repository binding {binding_id} is not in the approved repositoryScope")


def _req(data: dict[str, Any], key: str) -> Any:
    value = data.get(key)
    if value is None or value == "" or value == [] or value == {}:
        raise ManifestInvalid(f"manifest field {key!r} missing")
    return value


def parse_manifest(
    payload: Any,
    *,
    expected_run_id: str | None = None,
    expected_work_item_id: str | None = None,
    expected_project_id: str | None = None,
    now: datetime | None = None,
) -> Manifest:
    """Validate a manifest payload. Raises :class:`ManifestInvalid` on any doubt."""
    if isinstance(payload, dict) and isinstance(payload.get("manifest"), dict):
        payload = payload["manifest"]
    if not isinstance(payload, dict):
        raise ManifestInvalid("manifest is not a JSON object")

    declared_hash = payload.get("manifestHash") or payload.get("manifest_hash")
    if declared_hash is not None:
        actual = canonical_hash(payload)
        if str(declared_hash).lower() != actual:
            raise ManifestInvalid(
                f"manifest hash mismatch (declared {str(declared_hash)[:12]}…, actual {actual[:12]}…)"
            )

    data = normalize_keys(payload)
    now = now or datetime.now(timezone.utc)

    for key in ("workspaceId", "projectId", "workItemId", "revisionId", "revisionHash", "policyVersion"):
        _req(data, key)

    # INV-01 / AC01: drafts are never executable.
    state = data.get("revisionState") or (data.get("revision") or {}).get("state")
    if data.get("isDraft") is True or (state is not None and str(state).lower() not in APPROVED_REVISION_STATES):
        raise ManifestInvalid(f"revision is not approved (state={state!r}); refusing to act (INV-01)")

    if not _HEX64.match(str(data["revisionHash"])):
        raise ManifestInvalid("revisionHash must be 64 lowercase hex chars")

    approval_raw = data.get("approval")
    if not isinstance(approval_raw, dict) or not approval_raw.get("id"):
        raise ManifestInvalid("manifest has no server-side approval; refusing to act (INV-01)")
    approved_by = approval_raw.get("approvedBy") or {}
    kind = str(approved_by.get("kind") or approval_raw.get("approvedByKind") or "")
    if kind != "human":
        raise ManifestInvalid("approval was not granted by a human principal (INV-03)")
    if approval_raw.get("revisionId") and approval_raw["revisionId"] != data["revisionId"]:
        raise ManifestInvalid("approval belongs to a different revision")
    if approval_raw.get("revisionHash") and approval_raw["revisionHash"] != data["revisionHash"]:
        raise ManifestInvalid("approval revisionHash differs from manifest revisionHash (stale approval)")
    if approval_raw.get("revokedAt"):
        raise ManifestInvalid("approval is revoked")
    expires = _parse_dt(approval_raw.get("expiresAt"), "approval.expiresAt")
    if expires <= now:
        raise ManifestInvalid("approval is expired")
    approval = Approval(
        id=str(approval_raw["id"]),
        approved_by_kind=kind,
        approved_by=str(approved_by.get("principalId") or ""),
        approved_at=str(approval_raw.get("approvedAt") or ""),
        expires_at=str(approval_raw.get("expiresAt")),
        revoked_at=None,
    )

    scopes_raw = _req(data, "repositoryScope")
    if not isinstance(scopes_raw, list):
        raise ManifestInvalid("repositoryScope must be a list")
    scopes: list[RepoScope] = []
    for i, s in enumerate(scopes_raw):
        if not isinstance(s, dict):
            raise ManifestInvalid(f"repositoryScope[{i}] is not an object")
        for key in ("bindingId", "baseCommit", "targetBranch", "allowedPaths"):
            _req(s, key)
        if not _COMMIT.match(str(s["baseCommit"])):
            raise ManifestInvalid(f"repositoryScope[{i}].baseCommit is not a full commit sha")
        paths = s["allowedPaths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            raise ManifestInvalid(f"repositoryScope[{i}].allowedPaths must be a non-empty list of strings")
        scopes.append(RepoScope(str(s["bindingId"]), str(s["baseCommit"]), str(s["targetBranch"]), tuple(paths)))

    actions = _req(data, "allowedActions")
    if not isinstance(actions, list):
        raise ManifestInvalid("allowedActions must be a list")
    unknown = set(actions) - ALLOWED_ACTIONS
    if unknown:
        raise ManifestInvalid(f"unknown allowedActions: {sorted(unknown)}")

    limits_raw = _req(data, "limits")
    try:
        limits = Limits(int(limits_raw["maxSeconds"]), int(limits_raw["maxSpendMinor"]), str(limits_raw["currency"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestInvalid(f"limits invalid: {exc}") from exc
    if limits.max_seconds < 1 or limits.max_spend_minor < 0 or not _CURRENCY.match(limits.currency):
        raise ManifestInvalid("limits out of range")

    checks: list[CheckSpec] = []
    for i, c in enumerate(data.get("checks") or []):
        if not isinstance(c, dict):
            raise ManifestInvalid(f"checks[{i}] is not an object")
        name, cmd = c.get("name"), c.get("command")
        if not isinstance(name, str) or not _CHECK_NAME.match(name):
            raise ManifestInvalid(f"checks[{i}].name invalid")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
            raise ManifestInvalid(f"checks[{i}].command must be a non-empty argv list")
        timeout = c.get("timeoutSeconds")
        checks.append(CheckSpec(name, tuple(cmd), int(timeout) if timeout else None))

    task_raw = data.get("task") or data.get("revision") or {}
    task = TaskText(
        title=str(task_raw.get("title") or ""),
        intent=str(task_raw.get("intent") or task_raw.get("description") or ""),
        outcome=str(task_raw.get("outcome") or ""),
        criteria=tuple(_as_text(x) for x in task_raw.get("criteria") or task_raw.get("acceptanceCriteria") or []),
        non_goals=tuple(_as_text(x) for x in task_raw.get("nonGoals") or []),
    )

    run_id = str(data.get("runId") or data.get("id") or expected_run_id or "")
    if expected_run_id and run_id != expected_run_id:
        raise ManifestInvalid(f"manifest is for run {run_id}, not {expected_run_id}")
    if expected_work_item_id and data["workItemId"] != expected_work_item_id:
        raise ManifestInvalid("manifest workItemId differs from the claimed work item")
    if expected_project_id and data["projectId"] != expected_project_id:
        raise ManifestInvalid("manifest projectId differs from the claimed project")

    on_base_moved = str((data.get("policy") or {}).get("onBaseMoved") or data.get("onBaseMoved") or "wait")
    if on_base_moved not in ("wait", "continue"):
        on_base_moved = "wait"

    return Manifest(
        run_id=run_id,
        workspace_id=str(data["workspaceId"]),
        project_id=str(data["projectId"]),
        work_item_id=str(data["workItemId"]),
        revision_id=str(data["revisionId"]),
        revision_hash=str(data["revisionHash"]),
        policy_version=str(data["policyVersion"]),
        approval=approval,
        repository_scope=tuple(scopes),
        allowed_actions=frozenset(actions),
        limits=limits,
        checks=tuple(checks),
        task=task,
        on_base_moved=on_base_moved,
        manifest_hash=str(declared_hash) if declared_hash else None,
        raw=payload,
    )


def _as_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("title") or value.get("description") or json.dumps(value))
    return str(value)


def fetch_manifest(client, run_id: str, run_token: str, **expected) -> Manifest:
    return parse_manifest(client.get_manifest(run_id, run_token), expected_run_id=run_id, **expected)
