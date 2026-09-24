/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo } from "react";
// plane imports
import { EUserPermissions } from "@plane/constants";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { PROJECT_HUB_PROJECT_PAGES } from "./items";

/** Same shape as the native project navigation item (tab + sidebar navigation). */
export type TProjectHubNavigationItem = {
  name: string;
  href: string;
  icon: React.ElementType;
  access: EUserPermissions[];
  shouldRender: boolean;
  sortOrder: number;
  i18n_key: string;
  key: string;
};

/**
 * Additional project navigation items (Aktivität, Arbeitspakete, Roadmap, Wissen). Returns an empty
 * list unless the extension is enabled for the project, so native navigation stays unchanged.
 * Must be called from an observer component.
 */
export const useProjectHubNavigationItems = (
  workspaceSlug: string | undefined,
  projectId: string | undefined
): TProjectHubNavigationItem[] => {
  const store = useProjectHub();
  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    if (store.getCapabilities(workspaceSlug, projectId) === undefined)
      void store.fetchCapabilities(workspaceSlug, projectId);
  }, [store, workspaceSlug, projectId]);

  const enabled = !!workspaceSlug && !!projectId && store.isEnabled(workspaceSlug, projectId);

  // Stable identity so native navigation memos/effects don't re-run on every render.
  return useMemo(() => {
    if (!enabled || !workspaceSlug || !projectId) return [];
    return PROJECT_HUB_PROJECT_PAGES.map((page, index) => ({
      name: page.key,
      key: page.key,
      i18n_key: page.i18nKey,
      href: `/${workspaceSlug}/projects/${projectId}/hub/${page.segment}`,
      icon: page.icon,
      access: [EUserPermissions.ADMIN, EUserPermissions.MEMBER, EUserPermissions.GUEST],
      shouldRender: true,
      sortOrder: 100 + index,
    }));
  }, [enabled, workspaceSlug, projectId]);
};
