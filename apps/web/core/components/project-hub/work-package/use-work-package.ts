/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type {
  TExecutionApproval,
  TPackageProfile,
  TPackageReadiness,
  TPackageRevision,
  TPackageStatus,
} from "@plane/types";
import { getApprovalValidity } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import type { TWorkPackageScope } from "./types";

type TScopeIds = Omit<TWorkPackageScope, "readOnly">;

/** Profile (or `null` for a normal work item) of the native issue. */
export const usePackageProfile = ({ workspaceSlug, projectId, issueId }: TScopeIds) => {
  const store = useProjectHub();
  return useHubResource<TPackageProfile | null>(PH_KEYS.profile(issueId), () =>
    store.fetchProfile(workspaceSlug, projectId, issueId)
  );
};

/** Status projection (phase, delivery, flags) of the package. */
export const usePackageStatus = ({ workspaceSlug, projectId, issueId }: TScopeIds, enabled = true) => {
  const store = useProjectHub();
  return useHubResource<TPackageStatus | null>(enabled ? PH_KEYS.status(issueId) : null, () =>
    store.fetchStatus(workspaceSlug, projectId, issueId)
  );
};

/** Readiness checks of the working draft (server is the source of truth). */
export const usePackageReadiness = ({ workspaceSlug, projectId, issueId }: TScopeIds, enabled = true) => {
  const store = useProjectHub();
  return useHubResource<TPackageReadiness>(enabled ? PH_KEYS.readiness(issueId) : null, () =>
    store.packageService.getReadiness(workspaceSlug, projectId, issueId)
  );
};

/** All revisions of the package (unsorted, as served). */
export const usePackageRevisions = ({ workspaceSlug, projectId, issueId }: TScopeIds, enabled = true) => {
  const store = useProjectHub();
  return useHubResource<TPackageRevision[]>(enabled ? PH_KEYS.revisions(issueId) : null, () =>
    store.packageService.listRevisions(workspaceSlug, projectId, issueId)
  );
};

/** Execution approvals of the package. */
export const usePackageApprovals = ({ workspaceSlug, projectId, issueId }: TScopeIds, enabled = true) => {
  const store = useProjectHub();
  return useHubResource<TExecutionApproval[]>(enabled ? PH_KEYS.approvals(issueId) : null, () =>
    store.packageService.listExecutionApprovals(workspaceSlug, projectId, issueId)
  );
};

/** Revisions sorted newest first (a copy; never mutates the store value). */
export const sortRevisions = (revisions: TPackageRevision[] | undefined): TPackageRevision[] =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted typing)
  [...(revisions ?? [])].sort((a, b) => b.number - a.number);

/** Latest revision, if any. */
export const useLatestRevision = (revisions: TPackageRevision[] | undefined) =>
  useMemo(() => sortRevisions(revisions)[0], [revisions]);

/** The currently valid (server-confirmed, not revoked/expired) execution approval, if any. */
export const findValidApproval = (approvals: TExecutionApproval[] | undefined) =>
  approvals?.find((a) => getApprovalValidity(a).kind === "valid");

/** "Create revision" action shared by the brief tab and the sidebar card (same toasts, same invalidation). */
export const useCreateRevision = (scope: TScopeIds) => {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [isCreating, setIsCreating] = useState(false);
  const create = async () => {
    setIsCreating(true);
    try {
      const revision = await store.packageService.createRevision(scope.workspaceSlug, scope.projectId, scope.issueId);
      store.invalidateIssue(scope.issueId);
      showHubSuccessToast(t("project_hub.revisions.created", { number: revision.number }));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsCreating(false);
    }
  };
  return { create, isCreating };
};

/** "Activate as work package" action (never forced; normal issues stay normal, FR-B02). */
export const useActivatePackage = (scope: TScopeIds) => {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [isActivating, setIsActivating] = useState(false);
  const activate = async () => {
    setIsActivating(true);
    try {
      await store.activateProfile(scope.workspaceSlug, scope.projectId, scope.issueId);
      showHubSuccessToast(t("project_hub.work_package.activated"));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsActivating(false);
    }
  };
  return { activate, isActivating };
};
