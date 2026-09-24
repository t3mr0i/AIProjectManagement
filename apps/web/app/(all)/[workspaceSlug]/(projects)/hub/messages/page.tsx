/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { WorkspaceMessagesPage } from "@/components/project-hub/workspace";
import type { Route } from "./+types/page";

export default function ProjectHubMessagesRoute({ params }: Route.ComponentProps) {
  return <WorkspaceMessagesPage workspaceSlug={params.workspaceSlug} />;
}
