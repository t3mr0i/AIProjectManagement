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
import type { TPHDecisionPreview } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
import { createIdempotencyKey } from "@/services/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextAreaField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubMeta } from "../common/section";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";

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
 * never a decision; confirming reuses one idempotency key so retries cannot duplicate it (INV-07).
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
        issue_id: issueId ?? undefined,
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
    if (!preview) return;
    setBusy("confirm");
    try {
      await store.collaborationService.confirmDecision(workspaceSlug, projectId, {
        preview_id: preview.preview_id,
        title: preview.title,
        text: preview.text,
        rationale: preview.rationale,
        issue_id: preview.issue_id ?? issueId ?? undefined,
        source_message_ids: messageIds,
        idempotency_key: idempotencyKey,
      });
      showHubSuccessToast(t("project_hub.discussion.decision_confirmed"));
      store.invalidate(PH_KEYS.decisions(workspaceSlug, projectId, issueId ?? undefined));
      store.invalidate(PH_KEYS.decisions(workspaceSlug, projectId));
      onConfirmed();
      close();
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const canConfirm = !!preview && !preview.clarification && has("decision.publish");

  return (
    <HubDialog
      isOpen={isOpen}
      onClose={close}
      isBusy={!!busy}
      title={preview ? t("project_hub.discussion.preview_title") : t("project_hub.discussion.take_as_decision")}
      onSubmit={() => void (preview && !preview.clarification ? handleConfirm() : handlePreview())}
      actions={
        <>
          <Button variant="secondary" size="md" stretch="auto" label={t("project_hub.common.cancel")} onClick={close} />
          {!preview || preview.clarification ? (
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "preview"}
              disabled={!instruction.trim()}
              label={busy === "preview" ? t("project_hub.discussion.previewing") : t("project_hub.discussion.preview")}
            />
          ) : (
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "confirm"}
              disabled={!canConfirm}
              label={t("project_hub.discussion.confirm_decision")}
            />
          )}
        </>
      }
    >
      <p className="text-caption-sm-regular text-tertiary">
        {t("project_hub.discussion.selected", { count: messageIds.length })}
      </p>
      {(!preview || preview.clarification) && (
        <HubTextAreaField
          label={t("project_hub.discussion.instruction")}
          value={instruction}
          onChange={setInstruction}
        />
      )}
      {preview?.clarification && (
        <p
          role="alert"
          className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular text-primary"
        >
          {t("project_hub.discussion.clarification", { question: preview.clarification })}
        </p>
      )}
      {preview && !preview.clarification && (
        <div className="flex flex-col gap-2">
          <ToneBadge tone="warning" size="xs" label={t("project_hub.discussion.ai_answer_hint")} />
          <HubMeta
            items={[
              { label: t("project_hub.discussion.decision_title"), value: preview.title ?? "—" },
              {
                label: t("project_hub.discussion.decision_text"),
                value: <span className="whitespace-pre-wrap">{preview.text ?? "—"}</span>,
              },
              { label: t("project_hub.discussion.rationale"), value: preview.rationale ?? "—" },
              { label: t("project_hub.discussion.target"), value: preview.issue_id ?? issueId ?? "—" },
              {
                label: t("project_hub.common.sources"),
                value: (preview.sources ?? []).map((s) => s.title ?? s.id).join(", ") || "—",
              },
            ]}
          />
          {preview.audience_change?.description && (
            <p role="alert" className="text-body-xs-medium text-primary">
              {t("project_hub.discussion.audience_change", { description: preview.audience_change.description })}
            </p>
          )}
          {!has("decision.publish") && (
            <p className="text-caption-sm-regular text-tertiary">{t("project_hub.errors.kind.permission")}</p>
          )}
        </div>
      )}
    </HubDialog>
  );
});
