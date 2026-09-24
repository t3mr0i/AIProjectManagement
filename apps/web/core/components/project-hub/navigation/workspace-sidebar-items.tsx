/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
// local imports
import { ProjectHubGate } from "../common/gate";
import { PROJECT_HUB_WORKSPACE_PAGES } from "./items";

const Items = observer(function Items({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const { toggleSidebar, isExtendedSidebarOpened, toggleExtendedSidebar } = useAppTheme();
  const handleClick = () => {
    if (window.innerWidth < 768) toggleSidebar();
    if (isExtendedSidebarOpened) toggleExtendedSidebar(false);
  };
  return (
    <nav aria-label={t("project_hub.nav.section")} className="flex flex-col gap-0.5">
      <span className="px-2 pt-2 text-13 font-semibold whitespace-nowrap text-placeholder">
        {t("project_hub.nav.section")}
      </span>
      {PROJECT_HUB_WORKSPACE_PAGES.map((page) => {
        const href = `/${workspaceSlug}/hub${page.segment ? `/${page.segment}` : ""}`;
        const isActive = page.segment ? pathname.startsWith(href) : pathname === href || pathname === `${href}/`;
        return (
          <Link key={page.key} href={href} onClick={handleClick} aria-current={isActive ? "page" : undefined}>
            <SidebarNavItem isActive={isActive}>
              <div className="flex items-center gap-1.5 py-[1px]">
                <page.icon className="size-4 flex-shrink-0" />
                <p className="text-13 leading-5 font-medium">{t(page.i18nKey)}</p>
              </div>
            </SidebarNavItem>
          </Link>
        );
      })}
    </nav>
  );
});

/** Workspace sidebar entries; rendered only when the extension is enabled for the workspace. */
export const ProjectHubWorkspaceSidebarItems = observer(function ProjectHubWorkspaceSidebarItems() {
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString();
  if (!slug) return null;
  return (
    <ProjectHubGate workspaceSlug={slug}>
      <Items workspaceSlug={slug} />
    </ProjectHubGate>
  );
});
