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
import { ProjectHubProjectHeader } from "@/components/project-hub/navigation/headers";
import type { Route } from "./+types/layout";

/** Project-level Project Hub pages (Activity, Work packages, Roadmap, Knowledge). Feature-flagged per project. */
export default function ProjectHubProjectLayout({ params }: Route.ComponentProps) {
  return (
    <>
      <AppHeader header={<ProjectHubProjectHeader />} />
      <ContentWrapper>
        <HubPageGate workspaceSlug={params.workspaceSlug} projectId={params.projectId}>
          <Outlet />
        </HubPageGate>
      </ContentWrapper>
    </>
  );
}
