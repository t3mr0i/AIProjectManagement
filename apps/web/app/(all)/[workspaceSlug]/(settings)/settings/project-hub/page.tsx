/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { HubPageGate } from "@/components/project-hub/common/page";
import { ProjectHubSettingsPage } from "@/components/project-hub/settings";
import type { Route } from "./+types/page";

export default function ProjectHubSettingsRoute({ params }: Route.ComponentProps) {
  return (
    <SettingsContentWrapper>
      <HubPageGate workspaceSlug={params.workspaceSlug}>
        <ProjectHubSettingsPage workspaceSlug={params.workspaceSlug} />
      </HubPageGate>
    </SettingsContentWrapper>
  );
}
