/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { usePathname } from "next/navigation";
import { Outlet } from "react-router";
// components
import { getWorkspaceActivePath } from "@/components/settings/helper";
import { SettingsMobileNav } from "@/components/settings/mobile/nav";
import { WorkspaceSettingsSidebarRoot } from "@/components/settings/workspace/sidebar";

/**
 * Project Hub workspace settings (S12). Uses the native workspace settings chrome; authorization of
 * each section is enforced by the backend (capability `workspace.admin` / `integration.manage`).
 */
function ProjectHubSettingsLayout() {
  const pathname = usePathname();
  return (
    <>
      <SettingsMobileNav
        hamburgerContent={WorkspaceSettingsSidebarRoot}
        activePath={getWorkspaceActivePath(pathname) || ""}
      />
      <div className="inset-y-0 flex h-full w-full flex-row">
        <div className="relative flex size-full">
          <div className="hidden h-full md:block">
            <WorkspaceSettingsSidebarRoot />
          </div>
          <Outlet />
        </div>
      </div>
    </>
  );
}

export default observer(ProjectHubSettingsLayout);
