/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ProjectRoadmapPage } from "@/components/project-hub/project";
import type { Route } from "./+types/page";

export default function ProjectHubProjectRoadmapRoute({ params }: Route.ComponentProps) {
  return <ProjectRoadmapPage workspaceSlug={params.workspaceSlug} projectId={params.projectId} />;
}
