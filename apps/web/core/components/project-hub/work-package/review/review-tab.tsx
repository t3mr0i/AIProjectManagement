/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AlertCircleOutline, NewTabOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type {
  TMergeRequestLink,
  TPackageEvidence,
  TPackageReviewView,
  TProjectHubApiError,
  TReviewApproval,
  TReviewOpenPoint,
  TReviewDecision,
  TReviewKind,
} from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import {
  canEvidenceProve,
  getProjectHubErrorMessageKey,
  getTrustLabelKey,
  safeCriterionState,
  shortHash,
  toProjectHubApiError,
} from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField } from "../../common/field";
import { useProjectHubCapabilities } from "../../common/gate";
import { useMemberDisplayName } from "../../common/member-name";
import { HubCard, HubSection } from "../../common/section";
import { HubSelect } from "../../common/select";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

const CRITERION_TONE: Record<string, TProjectHubTone> = { proven: "success", failed: "danger", not_proven: "neutral" };
const RESULT_TONE: Record<string, TProjectHubTone> = {
  passed: "success",
  failed: "danger",
  not_run: "neutral",
  unknown: "neutral",
};

const EvidenceItem = observer(function EvidenceItem({ evidence }: { evidence: TPackageEvidence }) {
  const { t } = useTranslation();
  const { formatDateTime } = useHubFormatters();
  const proves = canEvidenceProve(evidence);
  return (
    <li className="flex flex-col gap-0.5 border-l-2 border-subtle pl-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-caption-md-medium text-primary">{evidence.name}</span>
        <ToneBadge tone={RESULT_TONE[evidence.result] ?? "neutral"} size="xs" label={evidence.result} />
        <ToneBadge tone={proves ? "info" : "neutral"} size="xs" label={t(getTrustLabelKey(evidence.trust))} />
        {!proves && evidence.result === "passed" && (
          <span className="text-caption-sm-regular text-tertiary">{t("project_hub.review.never_proof")}</span>
        )}
        {evidence.url && (
          <a
            href={evidence.url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-visible:outline-accent-primary inline-flex items-center gap-1 text-caption-sm-regular text-accent-primary underline focus-visible:outline-2"
          >
            {evidence.source}
            <Icon icon={NewTabOutline} />
          </a>
        )}
      </div>
      <p className="text-caption-sm-regular text-tertiary">
        {!evidence.url && `${evidence.source} · `}
        {evidence.commit_sha && <code className="font-mono">{shortHash(evidence.commit_sha)}</code>} ·{" "}
        {formatDateTime(evidence.occurred_at)}
      </p>
    </li>
  );
});

/** Code review decision of an MR is only valid for the reviewed head (INV-05). */
const getMrReviewState = (mr: TMergeRequestLink, approvals: TReviewApproval[]) => {
  const forMr = approvals.filter((a) => a.kind === "code" && a.merge_request_id === mr.id);
  const valid = forMr.find((a) => a.valid);
  const invalidated = forMr.find((a) => a.validity === "invalidated" || a.validity === "stale_head");
  return { valid, needsNewReview: !valid && !!invalidated };
};

const useOpenPointLabel = () => {
  const { t } = useTranslation();
  return (point: TReviewOpenPoint, criteria: TPackageReviewView["criteria"]): string => {
    switch (point.kind) {
      case "criterion_not_proven": {
        const c = criteria.find((x) => x.id === point.criterion_id);
        return t("project_hub.review.open_point.criterion_not_proven", {
          criterion: c?.statement ?? point.criterion_id,
          reason: point.reason,
        });
      }
      case "code_review_required":
        return point.invalidated
          ? t("project_hub.review.open_point.code_review_invalidated", { sha: shortHash(point.head_sha) })
          : t("project_hub.review.open_point.code_review_required", { sha: shortHash(point.head_sha) });
      case "open_question":
        return t("project_hub.review.open_point.open_question", { title: point.title });
      default:
        return t(`project_hub.review.open_point.${point.kind}`);
    }
  };
};

/** "Review" tab (S06): intent vs change, criteria ↔ evidence, separate technical and business reviews. */
export const ReviewTab = observer(function ReviewTab({ scope }: { scope: TWorkPackageScope }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const displayName = useMemberDisplayName();
  const { formatDateTime } = useHubFormatters();
  const { has, isHuman } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const openPointLabel = useOpenPointLabel();
  const { workspaceSlug, projectId, issueId } = scope;

  const review = useHubResource<TPackageReviewView>(PH_KEYS.review(issueId), () =>
    store.integrationService.getReview(workspaceSlug, projectId, issueId)
  );
  const mrs = useHubResource<TMergeRequestLink[]>(PH_KEYS.mergeRequests(issueId), () =>
    store.integrationService.listMergeRequests(workspaceSlug, projectId, issueId)
  );

  const [selectedMrId, setSelectedMrId] = useState<string | null>(null);
  const [codeComment, setCodeComment] = useState("");
  const [outcomeComment, setOutcomeComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [mergeTarget, setMergeTarget] = useState<TMergeRequestLink | null>(null);
  const [mergeError, setMergeError] = useState<TProjectHubApiError | null>(null);

  const mergeRequests = mrs.data ?? review.data?.merge_requests ?? [];
  const openMrs = mergeRequests.filter((m) => m.state === "open");
  const selectedMr = openMrs.find((m) => m.id === selectedMrId) ?? openMrs[0];

  const refreshAll = () => {
    store.invalidate(PH_KEYS.review(issueId));
    store.invalidate(PH_KEYS.mergeRequests(issueId));
    store.invalidate(PH_KEYS.status(issueId));
    store.invalidate(PH_KEYS.rows(workspaceSlug, projectId));
  };

  const submitReview = async (kind: TReviewKind, decision: TReviewDecision) => {
    setBusy(`${kind}:${decision}`);
    try {
      await store.integrationService.createReviewApproval(workspaceSlug, projectId, issueId, {
        kind,
        decision,
        comment: kind === "code" ? codeComment : outcomeComment,
        ...(kind === "code" && selectedMr ? { merge_request_id: selectedMr.id, head_sha: selectedMr.head_sha } : {}),
      });
      showHubSuccessToast(t("project_hub.review.recorded"));
      if (kind === "code") setCodeComment("");
      else setOutcomeComment("");
      refreshAll();
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const handleMerge = async () => {
    if (!mergeTarget) return;
    setBusy("merge");
    setMergeError(null);
    try {
      await store.integrationService.merge(workspaceSlug, projectId, mergeTarget.id, mergeTarget.head_sha);
      showHubSuccessToast(t("project_hub.review.merge_accepted"));
      setMergeTarget(null);
      refreshAll();
    } catch (error) {
      // HEAD_MISMATCH / REVIEW_REQUIRED / CAPABILITY_MISSING are shown inside the dialog.
      setMergeError(toProjectHubApiError(error));
      refreshAll();
    } finally {
      setBusy(null);
    }
  };

  const canReviewCode = has("review.approve_code") && isHuman && !scope.readOnly;
  const canAcceptOutcome = has("review.accept_outcome") && isHuman && !scope.readOnly;
  const canMerge = has("merge.request") && isHuman && !scope.readOnly;

  return (
    <HubResourceBoundary resource={review} loadingRows={4}>
      {(data) => (
        <div className="flex flex-col gap-6">
          <div className="grid gap-4 @3xl:grid-cols-2">
            <HubSection title={t("project_hub.review.intent")}>
              {data.revision ? (
                <HubCard className="flex flex-col gap-2 text-body-xs-regular">
                  <p className="text-caption-sm-regular text-tertiary">
                    {t("project_hub.revisions.number", { number: data.revision.number })} ·{" "}
                    <code className="font-mono">{shortHash(data.revision.content_hash)}</code>
                  </p>
                  <p className="font-medium text-primary">{data.revision.title}</p>
                  <p className="whitespace-pre-wrap text-primary">{data.revision.intent || "—"}</p>
                  {data.revision.outcome && (
                    <p className="whitespace-pre-wrap text-secondary">{data.revision.outcome}</p>
                  )}
                </HubCard>
              ) : (
                <HubEmpty title={t("project_hub.review.no_intent")} />
              )}
            </HubSection>
            <HubSection title={t("project_hub.review.current_change")}>
              {data.change_summary.merge_requests > 0 || data.claims.length > 0 ? (
                <HubCard className="flex flex-col gap-2 text-body-xs-regular">
                  <p className="text-secondary">
                    {t("project_hub.review.change_counts", {
                      mrs: data.change_summary.merge_requests,
                      commits: data.change_summary.commits,
                    })}
                  </p>
                  {data.claims.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <p className="text-caption-md-medium text-tertiary">
                        {t("project_hub.review.commit_claims")} — {t("project_hub.review.never_proof")}
                      </p>
                      <ul className="flex flex-col gap-0.5 text-caption-sm-regular text-secondary">
                        {data.claims.map((c) => (
                          <li key={`${c.merge_request_id}-${c.sha}`}>
                            <code className="font-mono">{shortHash(c.sha)}</code> {c.message}{" "}
                            <ToneBadge tone="neutral" size="xs" label={t("project_hub.trust.commit_message")} />
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-caption-sm-regular text-tertiary">{data.change_summary.note}</p>
                </HubCard>
              ) : (
                <HubEmpty title={t("project_hub.review.no_change")} />
              )}
            </HubSection>
          </div>

          <HubSection title={t("project_hub.review.criteria")}>
            {data.criteria.length === 0 ? (
              <HubEmpty title={t("project_hub.review.criteria_empty")} />
            ) : (
              <ol className="flex flex-col gap-2">
                {data.criteria.map((criterion) => {
                  const state = safeCriterionState(criterion.state, criterion.evidence ?? []);
                  return (
                    <li key={criterion.id}>
                      <HubCard className="flex flex-col gap-2">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="text-body-xs-medium text-primary">
                            {criterion.id}: {criterion.statement}
                          </p>
                          <ToneBadge
                            tone={CRITERION_TONE[state]}
                            size="xs"
                            label={t(`project_hub.review.state.${state}`)}
                          />
                        </div>
                        <p className="text-caption-sm-regular text-tertiary">
                          {t("project_hub.review.required_trust", {
                            trust: t(`project_hub.review.trust_level.${criterion.required_trust}`),
                          })}
                          {criterion.reason && ` · ${criterion.reason}`}
                        </p>
                        {(criterion.evidence ?? []).length === 0 ? (
                          <p className="text-caption-sm-regular text-tertiary">
                            {t("project_hub.review.evidence_none")}
                          </p>
                        ) : (
                          <ul className="flex flex-col gap-1.5">
                            {criterion.evidence.map((e) => (
                              <EvidenceItem key={e.id} evidence={e} />
                            ))}
                          </ul>
                        )}
                      </HubCard>
                    </li>
                  );
                })}
              </ol>
            )}
          </HubSection>

          {data.open_points.length > 0 && (
            <HubSection title={t("project_hub.review.open_points")}>
              <ul className="list-inside list-disc text-body-xs-regular text-secondary">
                {data.open_points.map((p, i) => (
                  // oxlint-disable-next-line react/no-array-index-key -- open points have no id
                  <li key={`${p.kind}-${i}`}>{openPointLabel(p, data.criteria)}</li>
                ))}
              </ul>
            </HubSection>
          )}

          <HubSection title={t("project_hub.review.mrs")}>
            {mergeRequests.length === 0 ? (
              <HubEmpty title={t("project_hub.review.mrs_empty")} />
            ) : (
              <ul className="flex flex-col gap-2">
                {mergeRequests.map((mr) => {
                  const reviewState = getMrReviewState(mr, data.approvals);
                  return (
                    <li key={mr.id}>
                      <HubCard className="flex flex-col gap-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <a
                            href={mr.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="focus-visible:outline-accent-primary text-body-xs-medium text-primary underline focus-visible:outline-2"
                          >
                            {mr.title || mr.external_id}
                          </a>
                          <ToneBadge tone={mr.state === "merged" ? "success" : "neutral"} size="xs" label={mr.state} />
                          {reviewState.valid && (
                            <ToneBadge
                              tone="success"
                              size="xs"
                              label={t("project_hub.review.valid_for_head", { sha: shortHash(mr.head_sha) })}
                            />
                          )}
                          {reviewState.needsNewReview && (
                            <ToneBadge tone="warning" size="xs" label={t("project_hub.review.new_review_required")} />
                          )}
                        </div>
                        <p className="text-caption-sm-regular text-tertiary">
                          {mr.repository ? `${mr.repository} · ` : ""}
                          {t("project_hub.review.branches", {
                            source: mr.source_branch,
                            target: mr.target_branch,
                          })}{" "}
                          · {t("project_hub.review.head", { sha: shortHash(mr.head_sha) })}
                        </p>
                        {mr.state === "open" && canMerge && (
                          <div>
                            <Button
                              variant="secondary"
                              size="sm"
                              stretch="auto"
                              label={t("project_hub.review.merge")}
                              onClick={() => {
                                setMergeError(null);
                                setMergeTarget(mr);
                              }}
                            />
                          </div>
                        )}
                      </HubCard>
                    </li>
                  );
                })}
              </ul>
            )}
            {!canMerge && mergeRequests.some((m) => m.state === "open") && (
              <p className="text-caption-sm-regular text-tertiary">{t("project_hub.review.no_capability_merge")}</p>
            )}
          </HubSection>

          <div className="grid gap-4 @3xl:grid-cols-2">
            <HubSection title={t("project_hub.review.code_review")}>
              {canReviewCode ? (
                <div className="flex flex-col gap-2">
                  {openMrs.length > 1 && (
                    <HubSelect
                      label={t("project_hub.review.select_mr")}
                      value={selectedMr?.id ?? null}
                      onChange={setSelectedMrId}
                      options={openMrs.map((m) => ({ value: m.id, label: `${m.title} (${shortHash(m.head_sha)})` }))}
                    />
                  )}
                  {selectedMr && (
                    <p className="text-caption-sm-regular text-tertiary">
                      {t("project_hub.review.head", { sha: shortHash(selectedMr.head_sha) })}
                    </p>
                  )}
                  <HubTextAreaField
                    label={t("project_hub.review.comment")}
                    placeholder={t("project_hub.review.comment_placeholder")}
                    value={codeComment}
                    onChange={setCodeComment}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      stretch="auto"
                      disabled={!selectedMr || !!busy}
                      loading={busy === "code:approved"}
                      label={t("project_hub.review.approve_code")}
                      onClick={() => void submitReview("code", "approved")}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      disabled={!selectedMr || !!busy}
                      loading={busy === "code:changes_requested"}
                      label={t("project_hub.review.request_changes")}
                      onClick={() => void submitReview("code", "changes_requested")}
                    />
                  </div>
                </div>
              ) : (
                <p className="text-caption-sm-regular text-tertiary">{t("project_hub.review.no_capability_review")}</p>
              )}
            </HubSection>
            <HubSection title={t("project_hub.review.outcome_acceptance")}>
              {canAcceptOutcome ? (
                <div className="flex flex-col gap-2">
                  <HubTextAreaField
                    label={t("project_hub.review.comment")}
                    placeholder={t("project_hub.review.comment_placeholder")}
                    value={outcomeComment}
                    onChange={setOutcomeComment}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      stretch="auto"
                      disabled={!!busy}
                      loading={busy === "outcome:approved"}
                      label={t("project_hub.review.accept_outcome")}
                      onClick={() => void submitReview("outcome", "approved")}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      disabled={!!busy}
                      loading={busy === "outcome:changes_requested"}
                      label={t("project_hub.review.return_for_rework")}
                      onClick={() => void submitReview("outcome", "changes_requested")}
                    />
                  </div>
                </div>
              ) : (
                <p className="text-caption-sm-regular text-tertiary">{t("project_hub.review.no_capability_review")}</p>
              )}
            </HubSection>
          </div>

          <HubSection title={t("project_hub.review.approvals")}>
            {data.approvals.length === 0 ? (
              <HubEmpty title={t("project_hub.review.approvals_empty")} />
            ) : (
              <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
                {data.approvals.map((approval) => (
                  <li key={approval.id} className="flex flex-col gap-0.5 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body-xs-medium text-primary">
                        {approval.kind === "code"
                          ? t("project_hub.review.code_review")
                          : t("project_hub.review.outcome_acceptance")}
                      </span>
                      <ToneBadge
                        tone={
                          approval.valid ? "success" : approval.validity === "changes_requested" ? "danger" : "warning"
                        }
                        size="xs"
                        label={
                          approval.validity === "invalidated"
                            ? t("project_hub.review.invalidated", { reason: approval.invalidated_reason })
                            : t(`project_hub.review.validity.${approval.validity}`)
                        }
                      />
                      {approval.head_sha && (
                        <code className="font-mono text-caption-sm-regular text-tertiary">
                          {t("project_hub.review.head", { sha: shortHash(approval.head_sha) })}
                        </code>
                      )}
                    </div>
                    <p className="text-caption-sm-regular text-tertiary">
                      {displayName(approval.approved_by)} · {formatDateTime(approval.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </HubSection>

          <HubDialog
            isOpen={!!mergeTarget}
            onClose={() => setMergeTarget(null)}
            isBusy={busy === "merge"}
            title={t("project_hub.review.merge_title", { title: mergeTarget?.title ?? "" })}
            onSubmit={() => void handleMerge()}
            actions={
              <>
                <Button
                  variant="secondary"
                  size="md"
                  stretch="auto"
                  label={t("project_hub.common.cancel")}
                  onClick={() => setMergeTarget(null)}
                />
                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  stretch="auto"
                  loading={busy === "merge"}
                  label={busy === "merge" ? t("project_hub.review.merging") : t("project_hub.review.merge")}
                />
              </>
            }
          >
            <p className="text-body-xs-regular text-secondary">
              {t("project_hub.review.merge_description", { sha: mergeTarget?.head_sha ?? "" })}
            </p>
            {mergeError && (
              <Banner
                placement="inline"
                variant="danger"
                role="alert"
                icon={<Icon icon={AlertCircleOutline} />}
                title={mergeError.code}
                description={t(getProjectHubErrorMessageKey(mergeError))}
              />
            )}
          </HubDialog>
        </div>
      )}
    </HubResourceBoundary>
  );
});
