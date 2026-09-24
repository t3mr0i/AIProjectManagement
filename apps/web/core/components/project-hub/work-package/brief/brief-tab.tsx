/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import type { TExecutionApproval, TPackageProfile, TPackageReadiness, TPackageRevision } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useProjectHubCapabilities } from "../../common/gate";
import { useHubResource } from "../../common/use-hub-resource";
import type { TWorkPackageScope } from "../types";
import { ApprovalPanel } from "./approval";
import { BriefForm } from "./brief-form";
import { ClarifyPanel } from "./clarify";
import { ProposalsPanel } from "./proposals";
import { ReadinessPanel } from "./readiness";
import { RevisionsPanel } from "./revisions";

/** "Auftrag" tab (S04): editable brief, readiness, revisions, approval, AI clarification. */
export const BriefTab = observer(function BriefTab({
  scope,
  profile,
}: {
  scope: TWorkPackageScope;
  profile: TPackageProfile;
}) {
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const { workspaceSlug, projectId, issueId } = scope;
  const canEdit = has("package.edit") && !scope.readOnly;

  const readiness = useHubResource<TPackageReadiness>(PH_KEYS.readiness(issueId), () =>
    store.packageService.getReadiness(workspaceSlug, projectId, issueId)
  );
  const revisions = useHubResource<TPackageRevision[]>(PH_KEYS.revisions(issueId), () =>
    store.packageService.listRevisions(workspaceSlug, projectId, issueId)
  );
  const approvals = useHubResource<TExecutionApproval[]>(PH_KEYS.approvals(issueId), () =>
    store.packageService.listExecutionApprovals(workspaceSlug, projectId, issueId)
  );

  return (
    <div className="flex flex-col gap-6">
      <BriefForm {...scope} profile={profile} canEdit={canEdit} />
      <ReadinessPanel readiness={readiness} />
      <ClarifyPanel scope={scope} canEdit={canEdit} />
      <ProposalsPanel scope={scope} canEdit={canEdit} />
      <RevisionsPanel
        scope={scope}
        revisions={revisions}
        workingRevisionId={profile.working_revision_id}
        canEdit={canEdit}
      />
      <ApprovalPanel scope={scope} approvals={approvals} revisions={revisions.data} readiness={readiness.data} />
    </div>
  );
});
