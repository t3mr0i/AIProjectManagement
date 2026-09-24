/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// local imports
import { HubPage } from "../common/page";
import { RoadmapView } from "../planning/roadmap-view";

/** Project roadmap: project milestones and dependencies (same view as the workspace roadmap, scoped). */
export const ProjectRoadmapPage = observer(function ProjectRoadmapPage({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  return (
    <HubPage title={t("project_hub.roadmap.project_title")}>
      <RoadmapView workspaceSlug={workspaceSlug} fixedProjectId={projectId} />
    </HubPage>
  );
});
