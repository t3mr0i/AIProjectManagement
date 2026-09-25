# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Edition / capability evidence register (FR-B13, PF13, PLANE_FOUNDATION §2, §5).

A capability counts as *available in this fork* only when its evidence points
at source files that actually exist in this checkout. Product marketing,
Plane Cloud or Commercial documentation is never accepted as evidence.
Everything else is needs_verification (open suitability check) or
extension (implemented by Project Hub, with evidence in this repo).
"""

import pathlib

API_ROOT = pathlib.Path(__file__).resolve().parents[2]  # apps/api
REPO_ROOT = API_ROOT.parents[1]

# status: native (Community source present) | extension (implemented here) | needs_verification
CAPABILITIES = [
    {
        "id": "users_memberships",
        "status": "native",
        "evidence": ["apps/api/plane/db/models/workspace.py", "apps/api/plane/db/models/project.py"],
    },
    {
        "id": "issues_drafts_states",
        "status": "native",
        "evidence": ["apps/api/plane/db/models/issue.py", "apps/api/plane/db/models/state.py"],
    },
    {
        "id": "cycles_modules_views",
        "status": "native",
        "evidence": [
            "apps/api/plane/db/models/cycle.py",
            "apps/api/plane/db/models/module.py",
            "apps/api/plane/db/models/view.py",
        ],
    },
    {
        "id": "pages_versions_assets",
        "status": "native",
        "evidence": ["apps/api/plane/db/models/page.py", "apps/api/plane/db/models/asset.py"],
    },
    {
        "id": "rich_text_collaboration",
        "status": "native",
        "evidence": ["packages/editor/package.json", "apps/live/package.json"],
    },
    {
        "id": "oauth_github_gitlab_google_gitea",
        "status": "native",
        "evidence": [
            "apps/api/plane/authentication/provider/oauth/github.py",
            "apps/api/plane/authentication/provider/oauth/gitlab.py",
        ],
    },
    {
        "id": "native_github_slack_integration_models",
        "status": "native",
        "evidence": ["apps/api/plane/db/models/integration/github.py", "apps/api/plane/db/models/integration/slack.py"],
    },
    {
        "id": "package_profiles_revisions_approvals",
        "status": "extension",
        "evidence": ["apps/api/plane/package_flow/models/core.py"],
    },
    {
        "id": "runner_claims_runs",
        "status": "extension",
        "evidence": ["apps/api/plane/package_flow/models/execution.py", "apps/runner"],
    },
    {
        "id": "chat_dm_ai_decisions",
        "status": "extension",
        "evidence": ["apps/api/plane/package_flow/models/collaboration.py"],
    },
    {
        "id": "portfolio_dependencies_milestones",
        "status": "extension",
        "evidence": ["apps/api/plane/package_flow/models/planning.py"],
    },
    {"id": "provider_adapters_contracts", "status": "extension", "evidence": ["apps/api/plane/package_flow/adapters"]},
    # Enterprise items are NOT in the Community source; they stay open checks (O03/O07).
    {"id": "saml_sso", "status": "needs_verification", "evidence": []},
    {"id": "oidc_enterprise_sso", "status": "needs_verification", "evidence": []},
    {"id": "scim_provisioning", "status": "needs_verification", "evidence": []},
    {"id": "commercial_portfolio_features", "status": "needs_verification", "evidence": []},
    {"id": "plane_cloud_ai_features", "status": "needs_verification", "evidence": []},
    {"id": "high_availability_operations", "status": "needs_verification", "evidence": []},
    {"id": "live_provider_contract_tests", "status": "needs_verification", "evidence": []},
]

ACCEPTED_EVIDENCE_KINDS = ("source_file",)
REJECTED_EVIDENCE_KINDS = ("marketing", "cloud_docs", "commercial_docs", "pricing_page")


def evaluate(capability):
    """Return the *effective* status: available only with existing source evidence."""
    if capability["status"] == "needs_verification":
        return "needs_verification"
    paths = capability.get("evidence") or []
    if not paths or not all((REPO_ROOT / p).exists() for p in paths):
        return "needs_verification"
    return capability["status"]


def accept_evidence(kind: str) -> bool:
    """Only source/runtime evidence counts; product docs never do (PF13)."""
    return kind in ACCEPTED_EVIDENCE_KINDS


def register():
    return [{**c, "effective_status": evaluate(c)} for c in CAPABILITIES]
