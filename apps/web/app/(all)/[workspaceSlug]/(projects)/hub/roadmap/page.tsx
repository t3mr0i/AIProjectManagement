/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { WorkspaceRoadmapPage } from "@/components/project-hub/workspace";
import type { Route } from "./+types/page";

export default function ProjectHubRoadmapRoute({ params }: Route.ComponentProps) {
  return <WorkspaceRoadmapPage workspaceSlug={params.workspaceSlug} />;
}
