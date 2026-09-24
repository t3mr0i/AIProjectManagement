/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { SettingsHeading } from "@/components/settings/heading";
// local imports
import { useProjectHubCapabilities } from "../common/gate";
import { ActivationSection } from "./activation-section";
import { GrantsSection } from "./grants-section";
import { IntegrationsSection } from "./integrations-section";
import { RetentionSection } from "./retention-section";
import { RunnersSection } from "./runners-section";

/**
 * S12 Project Hub settings. Each section loads independently and renders its own
 * permission-denied / error state, so a missing admin capability degrades to a partial page.
 */
export const ProjectHubSettingsPage = observer(function ProjectHubSettingsPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  const { has } = useProjectHubCapabilities(workspaceSlug);
  const isAdmin = has("workspace.admin");
  return (
    <div className="flex w-full flex-col gap-8">
      <PageHead title={t("project_hub.settings.title")} />
      <SettingsHeading title={t("project_hub.settings.title")} description={t("project_hub.settings.description")} />
      {!isAdmin && <p className="text-body-xs-regular text-tertiary">{t("project_hub.settings.admin_only")}</p>}
      <ActivationSection workspaceSlug={workspaceSlug} />
      <GrantsSection workspaceSlug={workspaceSlug} />
      <RunnersSection workspaceSlug={workspaceSlug} />
      <IntegrationsSection workspaceSlug={workspaceSlug} />
      <RetentionSection workspaceSlug={workspaceSlug} />
    </div>
  );
});
