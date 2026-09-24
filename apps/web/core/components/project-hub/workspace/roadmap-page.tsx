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

/** S10 Multi-project roadmap. */
export const WorkspaceRoadmapPage = observer(function WorkspaceRoadmapPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  return (
    <HubPage title={t("project_hub.roadmap.title")} description={t("project_hub.roadmap.scenario_hint")}>
      <RoadmapView workspaceSlug={workspaceSlug} />
    </HubPage>
  );
});
