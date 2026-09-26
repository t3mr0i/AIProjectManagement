/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import type { TPackageProfile } from "@plane/types";
// local imports
import { useProjectHubCapabilities } from "../../common/gate";
import type { TWorkPackageScope } from "../types";
import { usePackageApprovals, usePackageReadiness, usePackageRevisions } from "../use-work-package";
import { AIAssistPanel } from "./ai-assist";
import { ApprovalPanel } from "./approval";
import { BriefForm } from "./brief-form";
import { ClarifyPanel } from "./clarify";
import { ProposalsPanel } from "./proposals";
import { ReadinessPanel } from "./readiness";
import { RevisionsPanel } from "./revisions";

/** "Auftrag" tab (S04): editable brief, AI assistant + proposals, clarification, readiness, revisions, approval. */
export const BriefTab = observer(function BriefTab({
  scope,
  profile,
}: {
  scope: TWorkPackageScope;
  profile: TPackageProfile;
}) {
  const { has } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const canEdit = has("package.edit") && !scope.readOnly;

  const readiness = usePackageReadiness(scope);
  const revisions = usePackageRevisions(scope);
  const approvals = usePackageApprovals(scope);

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <BriefForm {...scope} profile={profile} canEdit={canEdit} />
      <AIAssistPanel scope={scope} canEdit={canEdit} />
      <ProposalsPanel
        scope={scope}
        canEdit={canEdit}
        existingCriterionIds={(profile.criteria ?? []).map((c) => c.id)}
      />
      <ClarifyPanel scope={scope} canEdit={canEdit} />
      <ReadinessPanel readiness={readiness} />
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
