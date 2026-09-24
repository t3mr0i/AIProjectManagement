# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Manifest validation (INV-01/INV-03) and local policy mirror (AC27)."""

from __future__ import annotations

import copy
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from project_hub_runner.errors import ManifestInvalid
from project_hub_runner.manifest import canonical_hash, parse_manifest
from project_hub_runner.policy import Rules, glob_to_regex, normalize_repo_path

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
BASE = "b" * 40


def good(**over):
    m = {
        "runId": "run-1",
        "workspaceId": "ws-1",
        "projectId": "p-1",
        "workItemId": "i-1",
        "revisionId": "rev-1",
        "revisionHash": "c" * 64,
        "policyVersion": "v1",
        "approval": {
            "id": "ap-1",
            "approvedBy": {"principalId": "u-1", "kind": "human"},
            "expiresAt": (NOW + timedelta(hours=1)).isoformat(),
            "revokedAt": None,
        },
        "repositoryScope": [
            {"bindingId": "b-1", "baseCommit": BASE, "targetBranch": "main", "allowedPaths": ["src/**", "docs/"]}
        ],
        "allowedActions": ["prepare_worktree", "edit_allowed_files", "create_commit"],
        "limits": {"maxSeconds": 60, "maxSpendMinor": 0, "currency": "EUR"},
    }
    m.update(over)
    return m


def test_valid_manifest_parses():
    m = parse_manifest(good(), expected_run_id="run-1", expected_work_item_id="i-1", now=NOW)
    assert m.scope_for(None).base_commit == BASE
    assert m.allowed_actions == frozenset({"prepare_worktree", "edit_allowed_files", "create_commit"})


def test_snake_case_manifest_is_accepted():
    snake = {
        "run_id": "run-1",
        "workspace_id": "ws-1",
        "project_id": "p-1",
        "work_item_id": "i-1",
        "revision_id": "rev-1",
        "revision_hash": "c" * 64,
        "policy_version": "v1",
        "approval": {"id": "a", "approved_by": {"kind": "human"}, "expires_at": (NOW + timedelta(1)).isoformat()},
        "repository_scope": [
            {"binding_id": "b", "base_commit": BASE, "target_branch": "main", "allowed_paths": ["src/**"]}
        ],
        "allowed_actions": ["edit_allowed_files"],
        "limits": {"max_seconds": 5, "max_spend_minor": 0, "currency": "EUR"},
    }
    assert parse_manifest(snake, now=NOW).limits.max_seconds == 5


@pytest.mark.parametrize(
    "field",
    [
        "workspaceId",
        "projectId",
        "workItemId",
        "revisionId",
        "revisionHash",
        "approval",
        "repositoryScope",
        "allowedActions",
        "limits",
        "policyVersion",
    ],
)
def test_missing_field_refused(field):
    m = good()
    del m[field]
    with pytest.raises(ManifestInvalid):
        parse_manifest(m, now=NOW)


@pytest.mark.parametrize(
    "mutate,msg",
    [
        (lambda m: m.update(revisionState="draft"), "not approved"),
        (lambda m: m.update(isDraft=True), "not approved"),
        (lambda m: m["approval"]["approvedBy"].update(kind="agent"), "human"),
        (lambda m: m["approval"].update(revokedAt=NOW.isoformat()), "revoked"),
        (lambda m: m["approval"].update(expiresAt=(NOW - timedelta(seconds=1)).isoformat()), "expired"),
        (lambda m: m["repositoryScope"][0].update(baseCommit="main"), "baseCommit"),
        (lambda m: m["repositoryScope"][0].update(allowedPaths=[]), "allowedPaths"),
        (lambda m: m.update(allowedActions=["merge"]), "unknown allowedActions"),
    ],
)
def test_invalid_manifests_refused(mutate, msg):
    m = copy.deepcopy(good())
    mutate(m)
    with pytest.raises(ManifestInvalid, match=msg):
        parse_manifest(m, now=NOW)


def test_manifest_for_other_work_item_refused():
    with pytest.raises(ManifestInvalid):
        parse_manifest(good(), expected_work_item_id="other", now=NOW)


def test_manifest_hash_verified():
    m = good()
    m["manifestHash"] = canonical_hash(m)
    parse_manifest(m, now=NOW)
    m["allowedActions"] = ["edit_allowed_files", "push_work_branch"]  # tampered after hashing
    with pytest.raises(ManifestInvalid, match="hash"):
        parse_manifest(m, now=NOW)


@pytest.mark.parametrize(
    "pattern,path,ok",
    [
        ("src/**", "src/a.py", True),
        ("src/**", "src/deep/b/c.py", True),
        ("src/**", "srcx/a.py", False),
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/sub/a.py", False),
        ("**/*.md", "README.md", True),
        ("**/*.md", "docs/x/y.md", True),
        ("docs/", "docs/notes.md", True),
        ("docs", "docs/notes.md", True),
        ("docs", "docsx", False),
        ("src/app.py", "src/app.py", True),
    ],
)
def test_glob(pattern, path, ok):
    assert bool(glob_to_regex(pattern).match(path)) is ok


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x", "src/../../x", ".git/config", "src/.git/hooks/pre-commit"])
def test_path_escape_refused(bad):
    m = good()
    m["repositoryScope"][0]["allowedPaths"] = ["**"]
    rules = Rules.from_manifest(parse_manifest(m, now=NOW))
    assert not rules.path_allowed(bad)
    with pytest.raises(Exception):
        normalize_repo_path(bad)


def test_rules_are_immutable_and_manifest_only():
    rules = Rules.from_manifest(parse_manifest(good(), now=NOW))
    with pytest.raises(dataclasses.FrozenInstanceError):
        rules.allowed_paths = ("**",)  # type: ignore[misc]
    assert not rules.path_allowed("README.md")
    assert not rules.action_allowed("push_work_branch")
