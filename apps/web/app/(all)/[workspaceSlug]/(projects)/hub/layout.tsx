/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
// components
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { HubPageGate } from "@/components/project-hub/common/page";
import { ProjectHubWorkspaceHeader } from "@/components/project-hub/navigation/headers";
import type { Route } from "./+types/layout";

/** Workspace-level Project Hub pages (Overview, Messages, Roadmap, Search). Feature-flagged. */
export default function ProjectHubWorkspaceLayout({ params }: Route.ComponentProps) {
  return (
    <>
      <AppHeader header={<ProjectHubWorkspaceHeader />} />
      <ContentWrapper>
        <HubPageGate workspaceSlug={params.workspaceSlug}>
          <Outlet />
        </HubPageGate>
      </ContentWrapper>
    </>
  );
}
