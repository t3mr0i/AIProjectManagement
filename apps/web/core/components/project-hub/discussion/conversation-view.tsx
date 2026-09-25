/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { useTranslation } from "@plane/i18n";
import type { TPHAiContext, TPHContextPreview, TPHConversation, TPHMessage, TPHSourceRef } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextAreaField } from "../common/field";
import { useMemberDisplayName } from "../common/member-name";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { DecisionFlowDialog } from "./decision-flow";

const AI_MENTION = /@ai\b/i;

const refLabel = (ref: TPHSourceRef, title?: string | null) => title || `${ref.type}:${ref.id.slice(0, 8)}`;

/** Used and blocked sources for the audience (FR-C02). Blocked sources never show content. */
function SourcesList({ context }: { context: TPHAiContext | TPHContextPreview }) {
  const { t } = useTranslation();
  const visible = context.visible ?? [];
  const used =
    "allowed" in context
      ? context.allowed.map((a) => refLabel(a.ref, a.title))
      : (context.sources_used ?? []).map((ref) => {
          const v = visible.find((x) => x.ref.type === ref.type && x.ref.id === ref.id);
          return refLabel(ref, v?.title);
        });
  const blocked = context.blocked ?? [];
  return (
    <div className="flex flex-col gap-1 text-caption-sm-regular">
      <p className="text-tertiary">
        {t("project_hub.discussion.used_sources")}: {used.join(", ") || "—"}
      </p>
      {blocked.length > 0 && (
        <p className="text-tertiary">
          {t("project_hub.discussion.blocked_sources")}: {blocked.length} (
          {[...new Set(blocked.map((b) => b.reason))].join(", ")})
        </p>
      )}
    </div>
  );
}

type TMessageProps = {
  message: TPHMessage;
  replies: TPHMessage[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onReply: (id: string) => void;
};

const MessageItem = observer(function MessageItem({ message, replies, selected, onToggle, onReply }: TMessageProps) {
  const { t } = useTranslation();
  const displayName = useMemberDisplayName();
  const { formatDateTime } = useHubFormatters();
  const [showThread, setShowThread] = useState(false);
  const renderOne = (m: TPHMessage, nested = false) => (
    <div
      key={m.id}
      className={cn(
        "flex items-start gap-2 rounded-md px-2 py-1.5",
        selected.has(m.id) && "bg-accent-subtle",
        nested && "ml-6"
      )}
    >
      <Checkbox
        checked={selected.has(m.id)}
        onCheckedChange={() => onToggle(m.id)}
        aria-label={`${t("project_hub.discussion.select_message")}: ${m.body.slice(0, 40)}`}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex flex-wrap items-center gap-1.5 text-caption-sm-regular text-tertiary">
          <span className="text-caption-md-medium text-primary">
            {m.author_kind === "ai"
              ? t("project_hub.discussion.ai_badge")
              : m.author_kind === "system"
                ? t("project_hub.discussion.system")
                : displayName(m.author_id)}
          </span>
          {m.author_kind === "ai" && (
            <ToneBadge tone="info" size="xs" label={t("project_hub.discussion.ai_answer_hint")} />
          )}
          <span>{formatDateTime(m.created_at)}</span>
          {m.edited_at && <span>({t("project_hub.discussion.edited")})</span>}
        </div>
        <p className="text-body-xs-regular break-words whitespace-pre-wrap text-primary">{m.body}</p>
        {m.author_kind === "ai" && m.ai_context && "visible" in m.ai_context && (
          <SourcesList context={m.ai_context as TPHAiContext} />
        )}
      </div>
    </div>
  );

  return (
    <li className="flex flex-col gap-0.5">
      {renderOne(message)}
      <div className="ml-8 flex gap-3">
        <button
          type="button"
          className="focus-visible:outline-accent-primary rounded-sm text-caption-sm-regular text-accent-primary hover:underline focus-visible:outline-2"
          onClick={() => onReply(message.id)}
        >
          {t("project_hub.discussion.reply")}
        </button>
        {replies.length > 0 && (
          <button
            type="button"
            aria-expanded={showThread}
            className="focus-visible:outline-accent-primary rounded-sm text-caption-sm-regular text-accent-primary hover:underline focus-visible:outline-2"
            onClick={() => setShowThread((v) => !v)}
          >
            {t("project_hub.discussion.replies", { count: replies.length })}
          </button>
        )}
      </div>
      {showThread && replies.map((r) => renderOne(r, true))}
    </li>
  );
});

type Props = {
  workspaceSlug: string;
  conversation: TPHConversation;
  /** Target package for decisions (package thread / package context). */
  issueId?: string | null;
  className?: string;
};

/**
 * Conversation (S09 / package thread): threads, message selection with a stable selection marker,
 * @AI with visible context (used + blocked sources) and the decision preview → confirm flow.
 */
export const ConversationView = observer(function ConversationView({
  workspaceSlug,
  conversation,
  issueId,
  className,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const messages = useHubResource<TPHMessage[]>(PH_KEYS.messages(workspaceSlug, conversation.id), () =>
    store.collaborationService.listMessages(workspaceSlug, conversation.id)
  );
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isDecisionOpen, setIsDecisionOpen] = useState(false);
  const [contextPreview, setContextPreview] = useState<TPHContextPreview | null>(null);
  const mentionsAi = AI_MENTION.test(body);
  // oxlint-disable-next-line unicorn/no-array-sort -- web targets ES2022 (no toSorted typing)
  const selectionKey = [...selected].sort().join(",");

  // @AI shows which context would be used and which is blocked for this audience — before sending.
  useEffect(() => {
    if (!mentionsAi) {
      setContextPreview(null);
      return;
    }
    let cancelled = false;
    store.collaborationService
      .previewContext(workspaceSlug, {
        conversation_id: conversation.id,
        selection: selectionKey ? selectionKey.split(",").map((id) => ({ type: "message", id })) : [],
        project_ids: conversation.project_id ? [conversation.project_id] : [],
      })
      .then((preview) => {
        if (!cancelled) setContextPreview(preview);
        return preview;
      })
      .catch(() => {
        if (!cancelled) setContextPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [mentionsAi, selectionKey, workspaceSlug, conversation.id, conversation.project_id, store]);

  const { topLevel, repliesByParent } = useMemo(() => {
    const list = messages.data ?? [];
    const map = new Map<string, TPHMessage[]>();
    for (const m of list) {
      if (m.parent_id) map.set(m.parent_id, [...(map.get(m.parent_id) ?? []), m]);
    }
    return { topLevel: list.filter((m) => !m.parent_id), repliesByParent: map };
  }, [messages.data]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const send = async () => {
    if (!body.trim()) return;
    setIsSending(true);
    try {
      await store.collaborationService.postMessage(workspaceSlug, conversation.id, {
        body: body.trim(),
        ...(replyTo ? { parent_id: replyTo } : {}),
      });
      setBody("");
      setReplyTo(null);
      store.invalidate(PH_KEYS.messages(workspaceSlug, conversation.id));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsSending(false);
    }
  };

  const markRead = async () => {
    try {
      await store.collaborationService.markRead(workspaceSlug, conversation.id);
      store.invalidate(PH_KEYS.conversations(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    }
  };

  const decisionProjectId = conversation.project_id;

  return (
    <div className={cn("flex min-h-0 flex-col gap-3", className)}>
      {conversation.kind === "direct" && (
        <p className="text-caption-sm-regular text-tertiary">{t("project_hub.messages.private_notice")}</p>
      )}
      <HubResourceBoundary
        resource={messages}
        loadingRows={3}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.discussion.empty")} />}
      >
        {() => (
          <ul className="flex flex-col gap-1" aria-live="polite">
            {topLevel.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                replies={repliesByParent.get(m.id) ?? []}
                selected={selected}
                onToggle={toggle}
                onReply={setReplyTo}
              />
            ))}
          </ul>
        )}
      </HubResourceBoundary>

      {selected.size > 0 && (
        <div
          role="toolbar"
          aria-label={t("project_hub.discussion.selected", { count: selected.size })}
          className="flex flex-wrap items-center gap-2 rounded-md border border-accent-strong bg-accent-subtle px-3 py-2"
        >
          <span className="text-body-xs-medium text-primary">
            {t("project_hub.discussion.selected", { count: selected.size })}
          </span>
          {decisionProjectId && (
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label={t("project_hub.discussion.take_as_decision")}
              onClick={() => setIsDecisionOpen(true)}
            />
          )}
          <Button
            variant="ghost"
            size="sm"
            stretch="auto"
            label={t("project_hub.discussion.clear_selection")}
            onClick={() => setSelected(new Set())}
          />
        </div>
      )}

      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        {replyTo && (
          <div className="flex items-center gap-2 text-caption-sm-regular text-tertiary">
            <span>{t("project_hub.discussion.thread")}</span>
            <button
              type="button"
              className="focus-visible:outline-accent-primary rounded-sm text-accent-primary hover:underline focus-visible:outline-2"
              onClick={() => setReplyTo(null)}
            >
              {t("project_hub.common.cancel")}
            </button>
          </div>
        )}
        <HubTextAreaField
          label={t("project_hub.discussion.title")}
          hideLabel
          placeholder={t("project_hub.discussion.placeholder")}
          value={body}
          onChange={setBody}
        />
        {mentionsAi && (
          <div className="rounded-md border border-dashed border-subtle px-3 py-2" aria-live="polite">
            <p className="text-caption-md-medium text-tertiary">{t("project_hub.discussion.ai_context")}</p>
            {contextPreview ? (
              <SourcesList context={contextPreview} />
            ) : (
              <p className="text-caption-sm-regular text-tertiary">{t("project_hub.common.loading")}</p>
            )}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            stretch="auto"
            loading={isSending}
            disabled={!body.trim()}
            label={isSending ? t("project_hub.discussion.sending") : t("project_hub.discussion.send")}
          />
          <Button
            variant="ghost"
            size="sm"
            stretch="auto"
            label={t("project_hub.discussion.mark_read")}
            onClick={() => void markRead()}
          />
        </div>
      </form>

      {decisionProjectId && (
        <DecisionFlowDialog
          isOpen={isDecisionOpen}
          onClose={() => setIsDecisionOpen(false)}
          onConfirmed={() => setSelected(new Set())}
          workspaceSlug={workspaceSlug}
          projectId={decisionProjectId}
          conversationId={conversation.id}
          messageIds={[...selected]}
          issueId={issueId ?? conversation.issue_id}
        />
      )}
    </div>
  );
});
