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
import type { TPHAIPatchCriterion, TPHProposal } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubAIFindings, HubAIModelLine, HubAIResultNotice, HubAIStatements } from "../../ai/result";
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

const TEXT_FIELDS = ["outcome", "intent"] as const;
const KNOWN_TASKS = new Set<string>(["concretize", "interpret", "report", "answer"]);
const KNOWN_VERIFICATIONS = new Set<string>(["ci", "manual", "runner", "any"]);

const asCriteria = (value: unknown): TPHAIPatchCriterion[] =>
  Array.isArray(value)
    ? value
        .filter((c): c is Record<string, unknown> => !!c && typeof c === "object" && "text" in c)
        .map((c) => ({
          id: typeof c.id === "string" ? c.id : undefined,
          text: String(c.text),
          verification: typeof c.verification === "string" ? c.verification : undefined,
          required: c.required === undefined ? undefined : !!c.required,
        }))
    : [];

/**
 * Readable view of a draft patch: outcome/intent as text, non-goals as a list and the full new
 * criteria list with "new" markers for criteria that are not in the current brief yet.
 */
function PatchView({
  patch,
  existingCriterionIds,
}: {
  patch: Record<string, unknown>;
  existingCriterionIds: Set<string>;
}) {
  const { t } = useTranslation();
  const rest = Object.entries(patch).filter(
    ([field]) => !(TEXT_FIELDS as readonly string[]).includes(field) && field !== "non_goals" && field !== "criteria"
  );
  const nonGoals = Array.isArray(patch.non_goals) ? patch.non_goals.map((g) => str(g)) : [];
  const criteria = asCriteria(patch.criteria);
  return (
    <dl className="flex min-w-0 flex-col gap-2 text-body-xs-regular text-secondary">
      {TEXT_FIELDS.filter((field) => typeof patch[field] === "string" && patch[field]).map((field) => (
        <div key={field} className="flex min-w-0 flex-col">
          <dt className="text-caption-md-medium text-tertiary">{t(`project_hub.brief.${field}`)}</dt>
          <dd className="break-words whitespace-pre-wrap text-primary">{str(patch[field])}</dd>
        </div>
      ))}
      {nonGoals.length > 0 && (
        <div className="flex min-w-0 flex-col">
          <dt className="text-caption-md-medium text-tertiary">{t("project_hub.brief.non_goals")}</dt>
          <dd>
            <ul className="list-inside list-disc text-primary">
              {nonGoals.map((goal) => (
                <li key={goal} className="break-words">
                  {goal}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      )}
      {criteria.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1">
          <dt className="text-caption-md-medium text-tertiary">{t("project_hub.brief.criteria")}</dt>
          <dd>
            <ol className="flex min-w-0 flex-col gap-1">
              {criteria.map((criterion, i) => {
                const isNew = !criterion.id || !existingCriterionIds.has(criterion.id);
                return (
                  <li key={criterion.id ?? `new:${criterion.text}`} className="flex min-w-0 items-start gap-2">
                    <span className="w-4 shrink-0 text-right text-caption-md-regular text-tertiary tabular-nums">
                      {i + 1}.
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="break-words text-primary">{criterion.text}</span>
                      <span className="flex flex-wrap items-center gap-1.5 text-caption-sm-regular text-tertiary">
                        {isNew && <ToneBadge tone="brand" size="xs" label={t("project_hub.ai.patch.new")} />}
                        <span>
                          {criterion.required === false
                            ? t("project_hub.common.optional")
                            : t("project_hub.common.required")}
                        </span>
                        {criterion.verification && (
                          <span>
                            ·{" "}
                            {t("project_hub.ai.patch.verification", {
                              method: KNOWN_VERIFICATIONS.has(criterion.verification)
                                ? t(`project_hub.brief.verifications.${criterion.verification}`)
                                : criterion.verification,
                            })}
                          </span>
                        )}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </dd>
        </div>
      )}
      {rest.map(([field, value]) => (
        <div key={field} className="flex min-w-0 flex-col">
          <dt className="text-caption-md-medium text-tertiary">{t("project_hub.proposals.patch_field", { field })}</dt>
          <dd className="break-words whitespace-pre-wrap">{str(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** AI proposals: nothing is applied without an explicit human accept. */
export const ProposalsPanel = observer(function ProposalsPanel({
  scope,
  canEdit,
  existingCriterionIds = [],
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
  /** Criteria ids of the current brief, to mark criteria a proposal adds. */
  existingCriterionIds?: string[];
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [busyId, setBusyId] = useState<string | null>(null);
  const existingIds = new Set(existingCriterionIds);
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
              .map((proposal) => {
                const { content } = proposal;
                const result = content.result;
                const failed = !!result?.status && result.status !== "ok";
                const statements = content.statements ?? [];
                const hasPatch = !!content.patch && Object.keys(content.patch).length > 0;
                const task = typeof content.task === "string" ? content.task : undefined;
                return (
                  <li key={proposal.id}>
                    <WpEntry className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <ToneBadge
                          tone={failed ? "warning" : "info"}
                          size="xs"
                          label={t(`project_hub.proposals.status.${proposal.status}`)}
                        />
                        <span className="text-caption-md-medium text-secondary">
                          {task && KNOWN_TASKS.has(task) ? t(`project_hub.ai.task.${task}`) : proposal.kind}
                        </span>
                        {content.instruction && task !== "report" && (
                          <span
                            className="min-w-0 truncate text-caption-sm-regular text-tertiary"
                            title={content.instruction}
                          >
                            “{content.instruction}”
                          </span>
                        )}
                      </div>
                      <HubAIResultNotice result={result} />
                      {content.interpretation && (
                        <p className="text-body-xs-regular whitespace-pre-wrap text-primary">
                          {content.interpretation}
                        </p>
                      )}
                      {!content.interpretation && statements.length === 0 && !failed && result?.text && (
                        <p className="text-body-xs-regular whitespace-pre-wrap text-primary">{result.text}</p>
                      )}
                      {hasPatch && content.patch && (
                        <PatchView patch={content.patch} existingCriterionIds={existingIds} />
                      )}
                      <HubAIStatements statements={statements} />
                      <HubAIFindings flags={result?.flags} notes={result?.notes} />
                      {content.note && <p className="text-caption-sm-regular text-tertiary">{content.note}</p>}
                      {proposal.sources && proposal.sources.length > 0 && (
                        <p className="text-caption-sm-regular text-tertiary">
                          {t("project_hub.common.sources")}:{" "}
                          {proposal.sources.map((src) => `${src.type}:${src.id.slice(0, 8)}`).join(", ")}
                        </p>
                      )}
                      {result && <HubAIModelLine provider={result.provider} model={result.model} />}
                      {canEdit && (
                        <div className="flex gap-2">
                          {!failed && (
                            <Button
                              variant="secondary"
                              size="sm"
                              stretch="auto"
                              loading={busyId === proposal.id}
                              label={t("project_hub.common.accept")}
                              onClick={() => void act(proposal, "accept")}
                            />
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            stretch="auto"
                            disabled={busyId === proposal.id}
                            label={failed ? t("project_hub.ai.dismiss") : t("project_hub.common.reject")}
                            onClick={() => void act(proposal, "reject")}
                          />
                        </div>
                      )}
                    </WpEntry>
                  </li>
                );
              })}
          </ul>
        )}
      </HubResourceBoundary>
    </WpSection>
  );
});
