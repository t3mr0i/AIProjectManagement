/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

/**
 * Extension routes. `mergeRoutes` deep-merges layouts with the same file into the core tree, so the
 * parent chain below only re-declares existing core layouts to nest the new pages; no core route is
 * replaced.
 *
 * Project Hub (package-flow extension): every page is feature-flagged at runtime via
 * `GET W/capabilities/me/` (extension_enabled) — the backend policy remains the real guard.
 */
export const extendedRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(projects)/layout.tsx", [
        // Project Hub — workspace level: Overview (S01), Messages (S09), Roadmap (S10), Search (S11)
        layout("./(all)/[workspaceSlug]/(projects)/hub/layout.tsx", [
          route(":workspaceSlug/hub", "./(all)/[workspaceSlug]/(projects)/hub/page.tsx"),
          route(":workspaceSlug/hub/messages", "./(all)/[workspaceSlug]/(projects)/hub/messages/page.tsx"),
          route(":workspaceSlug/hub/roadmap", "./(all)/[workspaceSlug]/(projects)/hub/roadmap/page.tsx"),
          route(":workspaceSlug/hub/search", "./(all)/[workspaceSlug]/(projects)/hub/search/page.tsx"),
        ]),
        layout("./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/layout.tsx", [
          // Project Hub — project level: Activity (S02), Work packages (S03), Roadmap, Knowledge
          layout("./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/hub/layout.tsx", [
            route(
              ":workspaceSlug/projects/:projectId/hub/activity",
              "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/hub/activity/page.tsx"
            ),
            route(
              ":workspaceSlug/projects/:projectId/hub/packages",
              "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/hub/packages/page.tsx"
            ),
            route(
              ":workspaceSlug/projects/:projectId/hub/roadmap",
              "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/hub/roadmap/page.tsx"
            ),
            route(
              ":workspaceSlug/projects/:projectId/hub/knowledge",
              "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/hub/knowledge/page.tsx"
            ),
          ]),
        ]),
      ]),
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        // Project Hub — workspace settings (S12)
        layout("./(all)/[workspaceSlug]/(settings)/settings/project-hub/layout.tsx", [
          route(
            ":workspaceSlug/settings/project-hub",
            "./(all)/[workspaceSlug]/(settings)/settings/project-hub/page.tsx"
          ),
        ]),
      ]),
    ]),
  ]),
];
