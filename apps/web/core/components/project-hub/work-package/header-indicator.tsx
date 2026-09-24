/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// local imports
import { ProjectHubGate } from "../common/gate";
import { PackagePhaseIndicator } from "../common/phase-indicator";
import { usePackageProfile, usePackageStatus } from "./use-work-package";

type Props = { workspaceSlug: string; projectId: string; issueId: string };

const HeaderIndicatorInner = observer(function HeaderIndicatorInner({ workspaceSlug, projectId, issueId }: Props) {
  const profile = usePackageProfile({ workspaceSlug, projectId, issueId });
  const status = usePackageStatus({ workspaceSlug, projectId, issueId }, !!profile.data);
  // No profile or not loaded → render nothing (native header unchanged).
  if (!profile.data || !status.data) return null;
  return <PackagePhaseIndicator status={status.data} variant="compact" />;
});

/** Compact phase/evidence indicator for the work item detail header. */
export const WorkPackageHeaderIndicator = observer(function WorkPackageHeaderIndicator(props: Props) {
  return (
    <ProjectHubGate workspaceSlug={props.workspaceSlug} projectId={props.projectId}>
      <HeaderIndicatorInner {...props} />
    </ProjectHubGate>
  );
});
