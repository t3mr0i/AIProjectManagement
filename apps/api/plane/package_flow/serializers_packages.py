# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""REST (snake_case) and transport-contract (camelCase, 1.1.0) shapes for packages and execution."""

import uuid

from .services.packages import (
    COMMIT_RE,
    CONTRACT_VERSION,
    approval_state,
    revision_is_stale,
)


def _iso(value):
    return value.isoformat() if value else None


def _id(value):
    return str(value) if value else None


def profile_data(profile, issue):
    state = getattr(issue, "state", None)
    return {
        "id": str(profile.id),
        "work_item_id": str(issue.id),
        "project_id": str(issue.project_id),
        "workspace_id": str(issue.workspace_id),
        "profile_kind": profile.profile_kind,
        "package_type": profile.package_type,
        "completion_criterion": profile.completion_criterion,
        "intent": profile.intent,
        "outcome": profile.outcome,
        "non_goals": profile.non_goals,
        "scope": profile.scope,
        "criteria": profile.criteria,
        "risk": profile.risk,
        "working_revision_id": _id(profile.working_revision_id),
        "approved_revision_id": _id(profile.approved_revision_id),
        "version": profile.version,
        "flags": profile.flags,
        "updated_at": _iso(profile.updated_at),
        "native": {
            "name": issue.name,
            "priority": issue.priority,
            "state_group": state.group if state is not None else None,
            "state_name": state.name if state is not None else None,
            "is_draft": issue.is_draft,
            "sequence_id": issue.sequence_id,
            "project_identifier": issue.project.identifier,
        },
    }


def revision_data(revision, profile=None, current_hash=None, with_contract=False):
    data = {
        "id": str(revision.id),
        "work_item_id": str(revision.issue_id),
        "number": revision.number,
        "title": revision.title,
        "intent": revision.intent,
        "outcome": revision.outcome,
        "non_goals": revision.non_goals,
        "scope": revision.scope,
        "criteria": revision.criteria,
        "decisions": revision.decisions,
        "artifacts": revision.artifacts,
        "profile_kind": revision.profile_kind,
        "package_type": revision.package_type,
        "source_versions": {k: v for k, v in (revision.source_versions or {}).items() if k != "risk"},
        "content_hash": revision.content_hash,
        "created_by": _id(revision.created_by_id),
        "created_at": _iso(revision.created_at),
        "is_approved": bool(profile and profile.approved_revision_id == revision.id),
        "is_stale": revision_is_stale(revision, current_hash),
    }
    if with_contract:
        data["contract"] = revision_contract(revision)
    return data


def _uuid_or_none(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def revision_contract(revision):
    """package-revision.schema.json v1.1.0."""
    repositories = []
    for repo in (revision.scope or {}).get("repositories", []) or []:
        if not isinstance(repo, dict):
            continue
        binding = _uuid_or_none(repo.get("binding_id"))
        commit = str(repo.get("base_commit") or "")
        paths = [p for p in repo.get("allowed_paths") or [] if isinstance(p, str) and p]
        if binding and COMMIT_RE.match(commit) and repo.get("target_branch") and paths:
            repositories.append(
                {
                    "bindingId": binding,
                    "baseCommit": commit,
                    "targetBranch": str(repo["target_branch"]),
                    "allowedPaths": paths,
                }
            )
    artifacts = []
    for art in revision.artifacts or []:
        if isinstance(art, dict) and _uuid_or_none(art.get("id")) and art.get("path") and art.get("content_hash"):
            artifacts.append(
                {
                    "id": _uuid_or_none(art["id"]),
                    "path": str(art["path"]),
                    "format": art.get("format") or "attachment-reference",
                    "contentHash": str(art["content_hash"]),
                }
            )
    return {
        "schemaVersion": CONTRACT_VERSION,
        "id": str(revision.id),
        "workItemId": str(revision.issue_id),
        "projectId": str(revision.project_id),
        "workspaceId": str(revision.workspace_id),
        "number": revision.number,
        "title": revision.title,
        "intent": revision.intent or "",
        "outcome": revision.outcome or "",
        "nonGoals": [g for g in revision.non_goals or [] if isinstance(g, str) and g],
        "criteria": [
            {
                "id": str(c.get("id")),
                "statement": str(c.get("text") or c.get("statement")),
                "verification": str(c.get("verification") or "review"),
                "required": bool(c.get("required", True)),
            }
            for c in revision.criteria or []
            if isinstance(c, dict) and c.get("id") and (c.get("text") or c.get("statement"))
        ],
        "sources": [],
        "repositories": repositories,
        "artifacts": artifacts,
        "contentHash": revision.content_hash,
        "createdAt": _iso(revision.created_at),
        "createdBy": _id(revision.created_by_id),
    }


def approval_data(approval, with_contract=True):
    data = {
        "id": str(approval.id),
        "work_item_id": str(approval.issue_id),
        "revision_id": str(approval.revision_id),
        "revision_hash": approval.revision_hash,
        "approved_by": str(approval.approved_by_id),
        "approved_at": _iso(approval.approved_at),
        "expires_at": _iso(approval.expires_at),
        "policy_version": approval.policy_version,
        "repository_scope": approval.repository_scope,
        "allowed_actions": approval.allowed_actions,
        "runner_profile_id": _id(approval.runner_profile_id),
        "limits": approval.limits,
        "state": approval_state(approval),
        "revoked_at": _iso(approval.revoked_at),
        "revoke_reason": approval.revoke_reason,
    }
    if with_contract:
        data["contract"] = approval_contract(approval)
    return data


def approval_contract(approval):
    """execution-authorization.schema.json v1.1.0 (``runnerProfileId`` only when bound to a runner)."""
    body = {
        "schemaVersion": CONTRACT_VERSION,
        "id": str(approval.id),
        "workspaceId": str(approval.workspace_id),
        "workItemId": str(approval.issue_id),
        "revisionId": str(approval.revision_id),
        "revisionHash": approval.revision_hash,
        "action": "execute",
        "approvedBy": {"principalId": str(approval.approved_by_id), "kind": "human"},
        "approvedAt": _iso(approval.approved_at),
        "expiresAt": _iso(approval.expires_at),
        "policyVersion": approval.policy_version,
        "repositoryScope": [
            {
                "bindingId": s["binding_id"],
                "baseCommit": s["base_commit"],
                "targetBranch": s["target_branch"],
                "allowedPaths": list(s["allowed_paths"]),
            }
            for s in approval.repository_scope or []
        ],
        "allowedActions": list(approval.allowed_actions or []),
        "limits": {
            "maxSeconds": int(approval.limits.get("max_seconds")),
            "maxSpendMinor": int(approval.limits.get("max_spend_minor")),
            "currency": approval.limits.get("currency"),
        },
        "revokedAt": _iso(approval.revoked_at),
    }
    if approval.runner_profile_id:
        body["runnerProfileId"] = str(approval.runner_profile_id)
    return body


def change_record_data(record):
    return {
        "id": str(record.id),
        "work_item_id": str(record.issue_id),
        "kind": record.kind,
        "title": record.title,
        "description": record.description,
        "status": record.status,
        "revision_id": _id(record.revision_id),
        "links": record.links,
        "created_by": _id(record.created_by_id),
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }


def runner_data(runner, token=None):
    data = {
        "id": str(runner.id),
        "name": runner.name,
        "kind": runner.kind,
        "owner_id": str(runner.owner_id),
        "token_prefix": runner.token_prefix,
        "is_active": runner.is_active,
        "last_seen_at": _iso(runner.last_seen_at),
        "created_at": _iso(runner.created_at),
    }
    if token is not None:
        data["token"] = token
    return data


def claim_data(claim):
    return {
        "id": str(claim.id),
        "work_item_id": str(claim.issue_id),
        "repository_binding_id": _id(claim.repository_binding_id),
        "exclusive": claim.exclusive,
        "holder_id": str(claim.holder_id),
        "runner_id": _id(claim.runner_id),
        "approval_id": _id(claim.approval_id),
        "fencing_token": claim.fencing_token,
        "lease_expires_at": _iso(claim.lease_expires_at),
        "status": claim.status,
    }


def run_data(run):
    return {
        "id": str(run.id),
        "work_item_id": str(run.issue_id),
        "revision_id": str(run.revision_id),
        "approval_id": str(run.approval_id),
        "claim_id": str(run.claim_id),
        "runner_id": _id(run.runner_id),
        "responsible_id": str(run.responsible_id),
        "status": run.status,
        "mode": run.mode,
        "agent_adapter": run.agent_adapter,
        "base_commits": run.base_commits,
        "limits": run.limits,
        "spend_minor": run.spend_minor,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "last_heartbeat_at": _iso(run.last_heartbeat_at),
        "progress": run.progress,
        "result": run.result,
        "cancel_requested_at": _iso(run.cancel_requested_at),
        "pause_reason": run.pause_reason,
        "manifest_hash": run.manifest_hash,
    }
