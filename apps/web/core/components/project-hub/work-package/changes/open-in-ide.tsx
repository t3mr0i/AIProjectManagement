/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TExecutionApproval } from "@plane/types";
// local imports
import { HubCodeBlock } from "../../common/copy-button";
import { WpSection } from "../panel";
import type { TWorkPackageScope } from "../types";

/** Build the `ph-runner` command (apps/runner CLI). No IDE is embedded (DESIGN_BRIEF S05). */
export const buildRunnerCommand = (
  scope: Pick<TWorkPackageScope, "projectId" | "issueId">,
  approval: Pick<TExecutionApproval, "id" | "repository_scope"> | undefined
): string => {
  if (!approval) return `ph-runner claim --project ${scope.projectId} --work-item ${scope.issueId} --hold`;
  const repo = approval.repository_scope.length === 1 ? ` --repo ${approval.repository_scope[0]?.binding_id}` : "";
  return `ph-runner run --project ${scope.projectId} --work-item ${scope.issueId} --approval ${approval.id}${repo} --mode human`;
};

export const OpenInIdePanel = observer(function OpenInIdePanel({
  scope,
  validApproval,
}: {
  scope: TWorkPackageScope;
  validApproval: TExecutionApproval | undefined;
}) {
  const { t } = useTranslation();
  const command = buildRunnerCommand(scope, validApproval);
  return (
    <WpSection
      title={t("project_hub.changes.open_in_ide")}
      description={t("project_hub.changes.open_in_ide_description")}
    >
      <HubCodeBlock
        value={command}
        copyLabel={t("project_hub.changes.copy_command")}
        successMessage={t("project_hub.changes.command_copied")}
      />
    </WpSection>
  );
});
