/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import type { TPHProposal } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubCard, HubSection } from "../../common/section";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import type { TWorkPackageScope } from "../types";

const str = (v: unknown) =>
  v === undefined || v === null || v === "" ? "—" : typeof v === "string" ? v : JSON.stringify(v);

/** AI proposals: nothing is applied without an explicit human accept. */
export const ProposalsPanel = observer(function ProposalsPanel({
  scope,
  canEdit,
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [busyId, setBusyId] = useState<string | null>(null);
  const proposals = useHubResource<TPHProposal[]>(
    PH_KEYS.proposals(scope.workspaceSlug, scope.projectId, scope.issueId),
    () => store.collaborationService.listProposals(scope.workspaceSlug, scope.projectId, scope.issueId)
  );

  const act = async (proposal: TPHProposal, action: "accept" | "reject") => {
    setBusyId(proposal.id);
    try {
      if (action === "accept") {
        await store.collaborationService.acceptProposal(scope.workspaceSlug, scope.projectId, proposal.id);
        showHubSuccessToast(t("project_hub.proposals.accepted"));
      } else {
        await store.collaborationService.rejectProposal(scope.workspaceSlug, scope.projectId, proposal.id);
        showHubSuccessToast(t("project_hub.proposals.rejected"));
      }
      store.invalidate(PH_KEYS.proposals(scope.workspaceSlug, scope.projectId, scope.issueId));
      store.invalidateIssue(scope.issueId);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <HubSection title={t("project_hub.proposals.title")} description={t("project_hub.proposals.hint")}>
      <HubResourceBoundary
        resource={proposals}
        loadingRows={1}
        isEmpty={(d) => d.filter((p) => p.status === "pending").length === 0}
        empty={<HubEmpty title={t("project_hub.proposals.empty")} />}
      >
        {(data) => (
          <ul className="flex flex-col gap-2">
            {data
              .filter((p) => p.status === "pending")
              .map((proposal) => (
                <li key={proposal.id}>
                  <HubCard className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge tone="info" size="xs" label={t(`project_hub.proposals.status.${proposal.status}`)} />
                      <span className="text-caption-sm-regular text-tertiary">{proposal.kind}</span>
                    </div>
                    {proposal.content.summary && (
                      <p className="text-body-xs-regular text-primary">{proposal.content.summary}</p>
                    )}
                    {proposal.content.changes && proposal.content.changes.length > 0 && (
                      <ul className="flex flex-col gap-1 text-body-xs-regular text-secondary">
                        {proposal.content.changes.map((change) => (
                          <li key={change.field}>
                            {t("project_hub.proposals.change", {
                              field: change.field,
                              from: str(change.from),
                              to: str(change.to),
                            })}
                          </li>
                        ))}
                      </ul>
                    )}
                    {proposal.content.statements && proposal.content.statements.length > 0 && (
                      <ul className="flex flex-col gap-1">
                        {proposal.content.statements.map((statement, i) => (
                          // oxlint-disable-next-line react/no-array-index-key
                          <li key={i} className="flex items-start gap-2 text-body-xs-regular text-secondary">
                            {statement.kind && (
                              <ToneBadge
                                tone={
                                  statement.kind === "confirmed" || statement.kind === "observed"
                                    ? "neutral"
                                    : "warning"
                                }
                                size="xs"
                                label={t(`project_hub.proposals.statement.${statement.kind}`)}
                              />
                            )}
                            <span>{statement.text}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {proposal.sources && proposal.sources.length > 0 && (
                      <p className="text-caption-sm-regular text-tertiary">
                        {t("project_hub.common.sources")}: {proposal.sources.map((s) => s.title ?? s.id).join(", ")}
                      </p>
                    )}
                    {canEdit && (
                      <div className="flex gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          stretch="auto"
                          loading={busyId === proposal.id}
                          label={t("project_hub.common.accept")}
                          onClick={() => void act(proposal, "accept")}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          stretch="auto"
                          disabled={busyId === proposal.id}
                          label={t("project_hub.common.reject")}
                          onClick={() => void act(proposal, "reject")}
                        />
                      </div>
                    )}
                  </HubCard>
                </li>
              ))}
          </ul>
        )}
      </HubResourceBoundary>
    </HubSection>
  );
});
