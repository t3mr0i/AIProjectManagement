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
import { WpEntry, WpSection } from "../panel";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import type { TWorkPackageScope } from "../types";

const str = (v: unknown): string => {
  if (v === undefined || v === null || v === "") return "—";
  if (typeof v === "string") return v;
  if (Array.isArray(v))
    return v
      .map((item) =>
        item && typeof item === "object" && "text" in item ? String((item as { text: unknown }).text) : str(item)
      )
      .join("\n");
  return JSON.stringify(v);
};

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
    () =>
      store.collaborationService.listProposals(scope.workspaceSlug, scope.projectId, {
        issue_id: scope.issueId,
        status: "pending",
      })
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
    <WpSection title={t("project_hub.proposals.title")} description={t("project_hub.proposals.hint")}>
      <HubResourceBoundary
        resource={proposals}
        loadingRows={1}
        isEmpty={(d) => d.filter((p) => p.status === "pending").length === 0}
        empty={<HubEmpty size="sm" title={t("project_hub.proposals.empty")} />}
      >
        {(data) => (
          <ul className="flex flex-col divide-y divide-subtle">
            {data
              .filter((p) => p.status === "pending")
              .map((proposal) => (
                <li key={proposal.id}>
                  <WpEntry className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge tone="info" size="xs" label={t(`project_hub.proposals.status.${proposal.status}`)} />
                      <span className="text-caption-sm-regular text-tertiary">{proposal.kind}</span>
                    </div>
                    {(proposal.content.interpretation || proposal.content.result?.text) && (
                      <p className="text-body-xs-regular whitespace-pre-wrap text-primary">
                        {proposal.content.interpretation ?? proposal.content.result?.text}
                      </p>
                    )}
                    {proposal.content.patch && Object.keys(proposal.content.patch).length > 0 && (
                      <dl className="flex flex-col gap-1 text-body-xs-regular text-secondary">
                        {Object.entries(proposal.content.patch).map(([field, value]) => (
                          <div key={field} className="flex flex-col">
                            <dt className="text-caption-md-medium text-tertiary">
                              {t("project_hub.proposals.patch_field", { field })}
                            </dt>
                            <dd className="whitespace-pre-wrap">{str(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {(proposal.content.statements ?? []).length > 0 && (
                      <ul className="flex flex-col gap-1">
                        {(proposal.content.statements ?? []).map((statement, i) => {
                          const kind = statement.kind ?? statement.status;
                          return (
                            // oxlint-disable-next-line react/no-array-index-key -- statements have no id
                            <li key={i} className="flex items-start gap-2 text-body-xs-regular text-secondary">
                              {kind && (
                                <ToneBadge
                                  tone={kind === "confirmed" || kind === "observed" ? "neutral" : "warning"}
                                  size="xs"
                                  label={
                                    ["observed", "confirmed", "inferred", "proposed"].includes(kind)
                                      ? t(`project_hub.proposals.statement.${kind}`)
                                      : kind
                                  }
                                />
                              )}
                              <span>{statement.text}</span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    {proposal.content.note && (
                      <p className="text-caption-sm-regular text-tertiary">{proposal.content.note}</p>
                    )}
                    {proposal.sources && proposal.sources.length > 0 && (
                      <p className="text-caption-sm-regular text-tertiary">
                        {t("project_hub.common.sources")}:{" "}
                        {proposal.sources.map((src) => `${src.type}:${src.id.slice(0, 8)}`).join(", ")}
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
                  </WpEntry>
                </li>
              ))}
          </ul>
        )}
      </HubResourceBoundary>
    </WpSection>
  );
});
