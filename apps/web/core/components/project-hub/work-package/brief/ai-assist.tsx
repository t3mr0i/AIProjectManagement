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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TPHAIProposalTask } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubAIStatusBadge } from "../../ai/status-badge";
import { HubTextAreaField } from "../../common/field";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { WpSection } from "../panel";
import type { TWorkPackageScope } from "../types";

const TASKS: TPHAIProposalTask[] = ["concretize", "interpret", "report"];
const KNOWN_RESULT_STATUSES = new Set<string>(["timeout", "budget_exceeded", "cancelled", "error", "unavailable"]);

/**
 * AI assistant for the brief: concretize (outcome, intent, non-goals, acceptance criteria),
 * interpret, or report. Every result is a pending proposal in "AI proposals" — nothing is applied
 * without an explicit accept.
 */
export const AIAssistPanel = observer(function AIAssistPanel({
  scope,
  canEdit,
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [instruction, setInstruction] = useState("");
  const [busyTask, setBusyTask] = useState<TPHAIProposalTask | null>(null);

  const run = async (task: TPHAIProposalTask) => {
    setBusyTask(task);
    try {
      const proposal = await store.aiService.requestProposal(scope.workspaceSlug, scope.projectId, {
        task,
        issue_id: scope.issueId,
        instruction: instruction.trim() || undefined,
      });
      const status = proposal.content.result?.status;
      // A failed AI call is still stored as a proposal (status + error) and shown below.
      if (status && status !== "ok")
        setToast({
          type: "warning",
          title: t("project_hub.ai.result_failed", {
            status: KNOWN_RESULT_STATUSES.has(status) ? t(`project_hub.ai.result_status.${status}`) : status,
          }),
          message: proposal.content.result?.error || undefined,
        });
      else showHubSuccessToast(t("project_hub.ai.assist.requested"));
      setInstruction("");
      store.invalidate(PH_KEYS.proposals(scope.workspaceSlug, scope.projectId, scope.issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusyTask(null);
    }
  };

  if (!canEdit) return null;

  return (
    <WpSection
      title={
        <span className="flex items-center gap-1.5">
          <AiStarOneOutline className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
          {t("project_hub.ai.assist.title")}
        </span>
      }
      description={t("project_hub.ai.assist.description")}
      actions={<HubAIStatusBadge workspaceSlug={scope.workspaceSlug} />}
      className="rounded-md border border-subtle bg-layer-1 p-3"
    >
      <form
        className="flex min-w-0 flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run("concretize");
        }}
      >
        <HubTextAreaField
          label={`${t("project_hub.ai.assist.instruction")} (${t("project_hub.common.optional")})`}
          placeholder={t("project_hub.ai.assist.instruction_placeholder")}
          value={instruction}
          onChange={setInstruction}
          disabled={busyTask !== null}
        />
        <div className="flex flex-wrap items-center gap-2">
          {TASKS.map((task) => (
            <Button
              key={task}
              type={task === "concretize" ? "submit" : "button"}
              variant={task === "concretize" ? "primary" : "secondary"}
              size="sm"
              stretch="auto"
              icon={task === "concretize" ? <Icon icon={AiStarOneOutline} /> : undefined}
              loading={busyTask === task}
              disabled={busyTask !== null && busyTask !== task}
              label={t(`project_hub.ai.assist.${task}`)}
              title={t(`project_hub.ai.assist.${task}_hint`)}
              onClick={task === "concretize" ? undefined : () => void run(task)}
            />
          ))}
        </div>
      </form>
    </WpSection>
  );
});
