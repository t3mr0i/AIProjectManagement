/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TExecutionApproval, TPackageStatus } from "@plane/types";
import { getApprovalValidity, getDeliveryLabelKey } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useProjectHubCapabilities } from "../../common/gate";
import { WpSection } from "../panel";
import { HubEmpty } from "../../common/states";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { DiagramsPanel } from "../../diagrams/diagrams-panel";
import type { TWorkPackageScope } from "../types";
import { ChangeRecordsPanel } from "./change-records";
import { OpenInIdePanel } from "./open-in-ide";
import { RunsPanel } from "./runs";
import { SpecSyncPanel } from "./spec-sync";

/** "Änderungen" tab (S05): change records, claims/runs, repositories, IDE hand-off, spec sync. */
export const ChangesTab = observer(function ChangesTab({
  scope,
  status,
}: {
  scope: TWorkPackageScope;
  status: TPackageStatus | null | undefined;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const canEdit = has("package.edit") && !scope.readOnly;
  const approvals = useHubResource<TExecutionApproval[]>(PH_KEYS.approvals(scope.issueId), () =>
    store.packageService.listExecutionApprovals(scope.workspaceSlug, scope.projectId, scope.issueId)
  );
  const validApproval = approvals.data?.find((a) => getApprovalValidity(a).kind === "valid");

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <RunsPanel scope={scope} />
      <OpenInIdePanel scope={scope} validApproval={validApproval} />
      <WpSection title={t("project_hub.changes.repositories")}>
        {status?.repositories && status.repositories.length > 0 ? (
          <ul className="flex flex-col divide-y divide-subtle">
            {status.repositories.map((repo) => (
              <li key={repo.binding_id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="text-body-xs-medium text-primary">{repo.name}</span>
                <ToneBadge
                  tone={repo.delivery === "unknown" ? "neutral" : repo.delivery === "rolled_back" ? "danger" : "info"}
                  size="xs"
                  label={t(getDeliveryLabelKey(repo.delivery))}
                />
                {repo.merge_request_state && (
                  <span className="text-caption-sm-regular text-tertiary">
                    {t("project_hub.changes.merge_request_state", { state: repo.merge_request_state })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <HubEmpty size="sm" title={t("project_hub.changes.repositories_empty")} />
        )}
      </WpSection>
      <ChangeRecordsPanel scope={scope} canEdit={canEdit} />
      <SpecSyncPanel scope={scope} canEdit={canEdit} />
      <DiagramsPanel
        workspaceSlug={scope.workspaceSlug}
        projectId={scope.projectId}
        issueId={scope.issueId}
        readOnly={scope.readOnly}
      />
    </div>
  );
});
