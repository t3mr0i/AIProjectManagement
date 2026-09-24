/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ProjectKnowledgePage } from "@/components/project-hub/project";
import type { Route } from "./+types/page";

export default function ProjectHubKnowledgeRoute({ params }: Route.ComponentProps) {
  return <ProjectKnowledgePage workspaceSlug={params.workspaceSlug} projectId={params.projectId} />;
}
