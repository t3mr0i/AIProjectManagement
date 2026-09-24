/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type { TPackageProfile, TPackageStatus } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useHubResource } from "../common/use-hub-resource";
import type { TWorkPackageScope } from "./types";

/** Profile (or `null` for a normal work item) of the native issue. */
export const usePackageProfile = ({ workspaceSlug, projectId, issueId }: Omit<TWorkPackageScope, "readOnly">) => {
  const store = useProjectHub();
  return useHubResource<TPackageProfile | null>(PH_KEYS.profile(issueId), () =>
    store.fetchProfile(workspaceSlug, projectId, issueId)
  );
};

/** Status projection (phase, delivery, flags) of the package. */
export const usePackageStatus = (
  { workspaceSlug, projectId, issueId }: Omit<TWorkPackageScope, "readOnly">,
  enabled = true
) => {
  const store = useProjectHub();
  return useHubResource<TPackageStatus | null>(enabled ? PH_KEYS.status(issueId) : null, () =>
    store.fetchStatus(workspaceSlug, projectId, issueId)
  );
};
