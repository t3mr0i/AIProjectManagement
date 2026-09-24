/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useEffect } from "react";
import { observer } from "mobx-react";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";

/** Loads `GET W/capabilities/me/?project_id=` once per scope. */
export const useProjectHubCapabilities = (workspaceSlug: string | undefined, projectId?: string) => {
  const store = useProjectHub();
  useEffect(() => {
    if (!workspaceSlug) return;
    if (store.getCapabilities(workspaceSlug, projectId) === undefined)
      void store.fetchCapabilities(workspaceSlug, projectId);
  }, [store, workspaceSlug, projectId]);
  const caps = workspaceSlug ? store.getCapabilities(workspaceSlug, projectId) : undefined;
  return {
    capabilities: caps,
    isLoaded: caps !== undefined,
    isEnabled: !!caps?.extension_enabled,
    has: (capability: Parameters<typeof store.hasCapability>[2]) =>
      !!workspaceSlug && store.hasCapability(workspaceSlug, projectId, capability),
    isHuman: caps?.principal_kind !== "agent",
  };
};

type Props = {
  workspaceSlug: string | undefined;
  projectId?: string;
  children: ReactNode;
  /** Rendered while loading or when disabled. Defaults to nothing (native UI stays unchanged). */
  fallback?: ReactNode;
  loading?: ReactNode;
};

/**
 * Feature flag boundary. The flag is only UX: every write is still authorized by the backend policy.
 * With the extension disabled nothing extra is rendered, so native Plane stays unchanged.
 */
export const ProjectHubGate = observer(function ProjectHubGate({
  workspaceSlug,
  projectId,
  children,
  fallback = null,
  loading = null,
}: Props) {
  const { isLoaded, isEnabled } = useProjectHubCapabilities(workspaceSlug, projectId);
  if (!isLoaded) return <>{loading}</>;
  if (!isEnabled) return <>{fallback}</>;
  return <>{children}</>;
});
