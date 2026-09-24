/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { WorkspaceOverviewPage } from "@/components/project-hub/workspace";
import type { Route } from "./+types/page";

export default function ProjectHubOverviewRoute({ params }: Route.ComponentProps) {
  return <WorkspaceOverviewPage workspaceSlug={params.workspaceSlug} />;
}
