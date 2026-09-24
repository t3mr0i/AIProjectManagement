/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
// plane imports
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { Header } from "@plane/blocks/layout";
import { useTranslation } from "@plane/i18n";
// components
import { CommonProjectBreadcrumbs } from "@/components/breadcrumbs/common";
import { useProjectCrumbProps } from "@/components/breadcrumbs/use-project-crumb-props";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
// hooks
import { useProject } from "@/hooks/store/use-project";
// local imports
import { PROJECT_HUB_PROJECT_PAGES, PROJECT_HUB_WORKSPACE_PAGES } from "./items";

/** Header for project-level Project Hub pages (native breadcrumb pattern). */
export const ProjectHubProjectHeader = observer(function ProjectHubProjectHeader() {
  const { t } = useTranslation();
  const { workspaceSlug, projectId } = useParams();
  const pathname = usePathname();
  const { loader } = useProject();
  const projectCrumb = useProjectCrumbProps(workspaceSlug?.toString(), projectId?.toString());
  const page = PROJECT_HUB_PROJECT_PAGES.find((p) => pathname.includes(`/hub/${p.segment}`));
  const PageIcon = page?.icon;
  return (
    <Header>
      <Header.LeftItem>
        <Breadcrumbs isLoading={loader === "init-loader"}>
          <CommonProjectBreadcrumbs
            workspaceSlug={workspaceSlug?.toString()}
            projectId={projectId?.toString()}
            {...projectCrumb}
          />
          {page && (
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink
                  label={t(page.i18nKey)}
                  href={`/${workspaceSlug}/projects/${projectId}/hub/${page.segment}`}
                  icon={PageIcon ? <PageIcon className="h-4 w-4 text-tertiary" /> : undefined}
                  isLast
                />
              }
              isLast
            />
          )}
        </Breadcrumbs>
      </Header.LeftItem>
    </Header>
  );
});

/** Header for workspace-level Project Hub pages. */
export const ProjectHubWorkspaceHeader = observer(function ProjectHubWorkspaceHeader() {
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();
  const pathname = usePathname();
  const page =
    PROJECT_HUB_WORKSPACE_PAGES.filter((p) => p.segment).find((p) => pathname.includes(`/hub/${p.segment}`)) ??
    PROJECT_HUB_WORKSPACE_PAGES[0];
  const PageIcon = page?.icon;
  return (
    <Header>
      <Header.LeftItem>
        <Breadcrumbs>
          <Breadcrumbs.Item
            component={<BreadcrumbLink label={t("project_hub.nav.section")} href={`/${workspaceSlug}/hub`} />}
          />
          {page && (
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink
                  label={t(page.i18nKey)}
                  icon={PageIcon ? <PageIcon className="h-4 w-4 text-tertiary" /> : undefined}
                  isLast
                />
              }
              isLast
            />
          )}
        </Breadcrumbs>
      </Header.LeftItem>
    </Header>
  );
});
