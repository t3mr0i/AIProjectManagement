/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// local imports
import { RoadmapView } from "../planning/roadmap-view";

/** S10 Multi-project roadmap (the view owns the page header: view tabs, range, actions). */
export const WorkspaceRoadmapPage = observer(function WorkspaceRoadmapPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  return <RoadmapView workspaceSlug={workspaceSlug} title={t("project_hub.roadmap.title")} />;
});
