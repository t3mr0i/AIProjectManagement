/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { observer } from "mobx-react";
// plane imports
import { LockOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
// local imports
import { useProjectHubCapabilities } from "../common/gate";
import { HubNotice } from "../common/states";
import { ActivationSection } from "./activation-section";
import { AIUsageSection } from "./ai-usage-section";
import { GrantsSection } from "./grants-section";
import { IntegrationsSection } from "./integrations-section";
import { RetentionSection } from "./retention-section";
import { RunnersSection } from "./runners-section";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/**
 * S12 Project Hub settings: a centered ~640px column of sections (title + one muted line) with
 * grouped rows inside rounded cards. Each section loads independently and renders its own
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
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-10">
      <PageHead title={t("project_hub.settings.title")} />
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-h5-medium text-primary">{t("project_hub.settings.title")}</h1>
          <p className="text-13 text-tertiary">{t("project_hub.settings.description")}</p>
        </div>
        {!isAdmin && (
          <HubNotice
            icon={LockOutline as TGlyph}
            title={t("project_hub.settings.admin_only")}
            description={t("project_hub.settings.admin_only_description")}
          />
        )}
      </div>
      <ActivationSection workspaceSlug={workspaceSlug} />
      <AIUsageSection workspaceSlug={workspaceSlug} />
      <GrantsSection workspaceSlug={workspaceSlug} />
      <RunnersSection workspaceSlug={workspaceSlug} />
      <IntegrationsSection workspaceSlug={workspaceSlug} />
      <RetentionSection workspaceSlug={workspaceSlug} />
    </div>
  );
});
