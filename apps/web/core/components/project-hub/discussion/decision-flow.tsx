/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { AiStarOneOutline, ChatOutline, CubeOutline, LockOutline, ProjectsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHDecisionPreview } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { createIdempotencyKey } from "@/services/project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextAreaField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubSelect } from "../common/select";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onConfirmed: () => void;
  workspaceSlug: string;
  projectId: string;
  conversationId: string;
  messageIds: string[];
  issueId?: string | null;
};

/**
 * J06: selected messages → "@AI take as decision" preview → explicit human confirm. The preview is
 * never a decision; if the target or statement is unclear the server asks exactly one question.
 * Confirming reuses one idempotency key so retries cannot duplicate the decision (INV-07).
 */
export const DecisionFlowDialog = observer(function DecisionFlowDialog({
  isOpen,
  onClose,
  onConfirmed,
  workspaceSlug,
  projectId,
  conversationId,
  messageIds,
  issueId,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const [instruction, setInstruction] = useState(() => t("project_hub.discussion.instruction_default"));
  const [targetIssueId, setTargetIssueId] = useState<string | null>(issueId ?? null);
  const [preview, setPreview] = useState<TPHDecisionPreview | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(createIdempotencyKey);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);

  const close = () => {
    setPreview(null);
    setIdempotencyKey(createIdempotencyKey());
    onClose();
  };

  const handlePreview = async () => {
    setBusy("preview");
    try {
      const result = await store.collaborationService.previewDecision(workspaceSlug, projectId, {
        conversation_id: conversationId,
        message_ids: messageIds,
        issue_id: targetIssueId ?? undefined,
        instruction,
      });
      setPreview(result);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const handleConfirm = async () => {
    if (!preview || preview.type !== "preview") return;
    setBusy("confirm");
    try {
      await store.collaborationService.confirmDecision(workspaceSlug, projectId, {
        preview_id: preview.preview_id,
        source_message_ids: preview.source_message_ids,
        idempotency_key: idempotencyKey,
      });
      showHubSuccessToast(t("project_hub.discussion.decision_confirmed"));
      store.invalidate(`ph:decisions:${workspaceSlug}:${projectId}:`);
      if (preview.issue_id) store.invalidate(PH_KEYS.decisions(workspaceSlug, projectId, preview.issue_id));
      onConfirmed();
      close();
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const isPreview = preview?.type === "preview";
  const canConfirm = isPreview && has("decision.publish");

  return (
    <HubDialog
      isOpen={isOpen}
      onClose={close}
      isBusy={!!busy}
      title={isPreview ? t("project_hub.discussion.preview_title") : t("project_hub.discussion.take_as_decision")}
      onSubmit={() => void (isPreview ? handleConfirm() : handlePreview())}
      actions={
        <>
          <Button variant="secondary" size="md" stretch="auto" label={t("project_hub.common.cancel")} onClick={close} />
          {isPreview ? (
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "confirm"}
              disabled={!canConfirm}
              label={t("project_hub.discussion.confirm_decision")}
            />
          ) : (
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "preview"}
              disabled={!instruction.trim()}
              label={busy === "preview" ? t("project_hub.discussion.previewing") : t("project_hub.discussion.preview")}
            />
          )}
        </>
      }
    >
      <p className="text-caption-md-regular text-tertiary">
        {t("project_hub.discussion.selected", { count: messageIds.length })}
      </p>
      {!isPreview && (
        <HubTextAreaField
          label={t("project_hub.discussion.instruction")}
          value={instruction}
          onChange={setInstruction}
        />
      )}
      {preview?.type === "clarification" && (
        <div role="alert" className="flex flex-col gap-2 rounded-md border border-subtle bg-layer-2 px-3 py-2">
          <p className="text-13 text-primary">
            {t("project_hub.discussion.clarification", { question: preview.question })}
          </p>
          {preview.options && preview.options.length > 0 && (
            <HubSelect
              label={t("project_hub.discussion.target")}
              value={targetIssueId}
              onChange={setTargetIssueId}
              options={preview.options.map((o) => ({ value: o.issue_id, label: `${o.identifier} ${o.name}` }))}
            />
          )}
        </div>
      )}
      {preview?.type === "preview" && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col overflow-hidden rounded-md border border-subtle bg-layer-1">
            <div className="flex h-8 items-center gap-1.5 bg-layer-2 px-3">
              <AiStarOneOutline className="size-3.5 shrink-0 text-tertiary" aria-hidden="true" />
              <span className="truncate text-13 font-medium text-primary">{preview.title}</span>
              <span className="flex-1" />
              <HubChip variant="soft" tone="warning" label={t("project_hub.discussion.ai_answer_hint")} />
            </div>
            <div className="flex flex-col gap-2 px-3 py-2.5">
              <p className="text-13 leading-5 whitespace-pre-wrap text-primary">{preview.text}</p>
              {preview.rationale && (
                <p className="text-caption-md-regular leading-4 text-tertiary">
                  <span className="text-placeholder">{t("project_hub.discussion.rationale")}: </span>
                  {preview.rationale}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                <HubChip
                  icon={preview.issue_id ? (CubeOutline as TGlyph) : (ProjectsOutline as TGlyph)}
                  label={
                    preview.issue_id
                      ? `${t("project_hub.discussion.target")}: ${preview.issue_id.slice(0, 8)}`
                      : t("project_hub.common.project")
                  }
                />
                <HubChip
                  icon={ChatOutline as TGlyph}
                  label={t("project_hub.discussion.selected", { count: preview.source_message_ids.length })}
                />
                {preview.private_source && (
                  <HubChip
                    variant="soft"
                    tone="warning"
                    icon={LockOutline as TGlyph}
                    label={t("project_hub.discussion.private_source_short")}
                    title={t("project_hub.discussion.private_source")}
                  />
                )}
              </div>
            </div>
          </div>
          {preview.private_source && (
            <p role="alert" className="text-caption-md-regular text-secondary">
              {t("project_hub.discussion.private_source")}
            </p>
          )}
          {!has("decision.publish") && (
            <p className="text-caption-md-regular text-tertiary">{t("project_hub.errors.kind.permission")}</p>
          )}
        </div>
      )}
    </HubDialog>
  );
});
