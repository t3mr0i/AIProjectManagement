# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider adapters (PRD §12). ``get_adapter(provider)`` is the only entry point."""

from .azure_devops import AzureDevOpsAdapter
from .base import CAPABILITIES, Adapter, CapabilityDeclaration, NormalizedEvent, override_transport  # noqa: F401
from .generic_git import GenericGitAdapter
from .github import GitHubAdapter
from .gitlab import GitLabAdapter
from .jira import JiraAdapter
from .linear import LinearAdapter

ADAPTERS = {
    cls.provider: cls
    for cls in (GitLabAdapter, JiraAdapter, LinearAdapter, AzureDevOpsAdapter, GenericGitAdapter, GitHubAdapter)
}


def get_adapter(provider, transport=None) -> Adapter:
    try:
        return ADAPTERS[provider](transport=transport)
    except KeyError:
        raise ValueError(f"Unknown provider {provider!r}") from None


def all_declarations():
    return [cls().declare().as_dict() for cls in ADAPTERS.values()]
