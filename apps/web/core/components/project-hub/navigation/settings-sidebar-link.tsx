/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
// plane imports
import { IntegrationsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import { SettingsSidebarItem } from "@/components/settings/sidebar/item";
// local imports
import { ProjectHubGate } from "../common/gate";

/** Workspace settings entry for the Project Hub page (S12), only when the extension is enabled. */
export const ProjectHubSettingsSidebarLink = observer(function ProjectHubSettingsSidebarLink() {
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();
  const pathname = usePathname();
  const slug = workspaceSlug?.toString();
  if (!slug) return null;
  const href = `/${slug}/settings/project-hub`;
  return (
    <ProjectHubGate workspaceSlug={slug}>
      <div className="flex shrink-0 flex-col py-3 last:pb-0">
        <SettingsSidebarItem
          as="link"
          href={href}
          isActive={pathname.startsWith(href)}
          icon={IntegrationsOutline}
          label={t("project_hub.nav.settings")}
        />
      </div>
    </ProjectHubGate>
  );
});
