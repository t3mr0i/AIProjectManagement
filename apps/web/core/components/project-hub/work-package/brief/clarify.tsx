/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AiStarOneOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHClarifyRequest, TPHClarifyStep } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextAreaField } from "../../common/field";
import { HubCard, HubSection } from "../../common/section";
import { showHubErrorToast } from "../../common/toast";
import type { TWorkPackageScope } from "../types";

/**
 * "Clarify with AI" (PRD §14.3): one question per round with a labelled recommendation, a
 * checkpoint after three questions, stoppable at any time. Answers only produce a pending draft
 * proposal — nothing is applied without an explicit accept (see "AI proposals").
 */
export const ClarifyPanel = observer(function ClarifyPanel({
  scope,
  canEdit,
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [step, setStep] = useState<TPHClarifyStep | null>(null);
  const [answer, setAnswer] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const call = async (body: TPHClarifyRequest = {}) => {
    setIsBusy(true);
    try {
      const next = await store.collaborationService.clarify(scope.workspaceSlug, scope.projectId, scope.issueId, body);
      setStep(body.stop ? null : next);
      setAnswer("");
      store.invalidate(PH_KEYS.proposals(scope.workspaceSlug, scope.projectId, scope.issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsBusy(false);
    }
  };

  if (!canEdit) return null;

  const stopButton = (
    <Button
      variant="ghost"
      size="sm"
      stretch="auto"
      disabled={isBusy}
      label={t("project_hub.clarify.stop")}
      onClick={() => void call({ stop: true })}
    />
  );

  return (
    <HubSection title={t("project_hub.clarify.title")} description={t("project_hub.clarify.description")}>
      {!step ? (
        <div>
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            icon={<Icon icon={AiStarOneOutline} />}
            loading={isBusy}
            label={t("project_hub.clarify.start")}
            onClick={() => void call()}
          />
        </div>
      ) : (
        <HubCard className="flex flex-col gap-3">
          {step.type === "question" ? (
            <>
              <div aria-live="polite" className="flex flex-col gap-2">
                <p className="text-caption-md-medium text-tertiary">
                  {t("project_hub.clarify.question", { index: step.questions_asked })} · {step.topic}
                </p>
                <p className="text-body-sm-medium text-primary">{step.question}</p>
                {step.why && <p className="text-caption-sm-regular text-secondary">{step.why}</p>}
                {step.recommendation && (
                  <div className="rounded-md border border-dashed border-subtle px-3 py-2">
                    <p className="text-caption-md-medium text-tertiary">{t("project_hub.clarify.recommendation")}</p>
                    <p className="text-body-xs-regular text-secondary">{step.recommendation}</p>
                  </div>
                )}
              </div>
              <form
                className="flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (answer.trim()) void call({ answer: answer.trim() });
                }}
              >
                <HubTextAreaField label={t("project_hub.clarify.your_answer")} value={answer} onChange={setAnswer} />
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    stretch="auto"
                    loading={isBusy}
                    disabled={!answer.trim()}
                    label={t("project_hub.clarify.answer")}
                  />
                  {step.recommendation && (
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("project_hub.clarify.use_recommendation")}
                      onClick={() => setAnswer(step.recommendation ?? "")}
                    />
                  )}
                  {stopButton}
                </div>
              </form>
            </>
          ) : (
            <>
              <div aria-live="polite" className="flex flex-col gap-2">
                <p className="text-body-sm-medium text-primary">
                  {step.type === "complete"
                    ? t("project_hub.clarify.closed")
                    : t("project_hub.clarify.checkpoint_title")}
                </p>
                <p className="text-body-xs-regular text-secondary">{t("project_hub.clarify.checkpoint_description")}</p>
                {step.draft_proposal_id && (
                  <p className="text-caption-sm-regular text-secondary">{t("project_hub.clarify.draft_ready")}</p>
                )}
                {step.open_topics.length > 0 && (
                  <div>
                    <p className="text-caption-md-medium text-tertiary">{t("project_hub.clarify.open_blockers")}</p>
                    <ul className="list-inside list-disc text-body-xs-regular text-secondary">
                      {step.open_topics.map((topic) => (
                        <li key={topic}>{topic}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {step.can_continue && (
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    loading={isBusy}
                    label={t("project_hub.clarify.continue")}
                    onClick={() => void call({ continue: true })}
                  />
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  label={t("project_hub.common.close")}
                  onClick={() => setStep(null)}
                />
              </div>
            </>
          )}
        </HubCard>
      )}
    </HubSection>
  );
});
