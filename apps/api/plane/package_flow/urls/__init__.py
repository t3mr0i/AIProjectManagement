# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Package-flow URL aggregator.

Project-scoped prefix (PRD §13.4):
``/api/workspaces/{workspace_slug}/projects/{project_id}/package-flow/``
Workspace-scoped prefix: ``/api/workspaces/{workspace_slug}/package-flow/``
Runner / webhook ingress: ``/api/package-flow/...``

Each domain module owns its own patterns so workstreams stay independent.
"""

from .collaboration import urlpatterns as collaboration_urls
from .execution import urlpatterns as execution_urls
from .integrations import urlpatterns as integration_urls
from .packages import urlpatterns as package_urls
from .planning import urlpatterns as planning_urls

urlpatterns = [
    *package_urls,
    *execution_urls,
    *integration_urls,
    *collaboration_urls,
    *planning_urls,
]
