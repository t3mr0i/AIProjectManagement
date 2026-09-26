/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, KeyboardEvent, SVGProps } from "react";
import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Avatar } from "@makeplane/propel/components/avatar";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { TextArea } from "@makeplane/propel/components/text-area";
import {
  AgentOutline,
  AiStarOneOutline,
  ChatOutline,
  CloseOutline,
  LockOutline,
  ReplyOutline,
  SendOutline,
  SettingsOutline,
  TickCircleOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHAiContext, TPHContextPreview, TPHConversation, TPHMessage, TPHSourceRef } from "@plane/types";
import { cn, getFileURL } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { useMemberDisplayName } from "../common/member-name";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { DecisionFlowDialog } from "./decision-flow";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const AI_MENTION = /@ai\b/i;

const refLabel = (ref: TPHSourceRef, title?: string | null) => title || `${ref.type}:${ref.id.slice(0, 8)}`;

/* -------------------------------------------------------------------------------------------------
 * Avatars
 * -----------------------------------------------------------------------------------------------*/

const initialsOf = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

/** 20px avatar for a native member, or a glyph for AI / system authors. */
export const AuthorAvatar = observer(function AuthorAvatar({
  kind,
  userId,
  className,
}: {
  kind: TPHMessage["author_kind"];
  userId: string | null;
  className?: string;
}) {
  const { t } = useTranslation();
  const { getUserDetails } = useMember();
  const displayName = useMemberDisplayName();
  if (kind === "ai" || kind === "system") {
    const Glyph = kind === "ai" ? (AgentOutline as TGlyph) : (SettingsOutline as TGlyph);
    return (
      <span
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-full bg-layer-2 text-tertiary",
          className
        )}
        aria-hidden="true"
      >
        <Glyph className="size-3" />
      </span>
    );
  }
  const user = userId ? getUserDetails(userId) : undefined;
  const name = userId ? displayName(userId) : t("project_hub.common.unknown");
  return (
    <span className={cn("flex shrink-0", className)} aria-hidden="true">
      <Avatar size="xs" src={getFileURL(user?.avatar_url ?? "")} alt={name} fallback={initialsOf(name)} />
    </span>
  );
});

/* -------------------------------------------------------------------------------------------------
 * @AI context (used and blocked sources as quiet chips — FR-C02)
 * -----------------------------------------------------------------------------------------------*/

function SourceChips({ context, className }: { context: TPHAiContext | TPHContextPreview; className?: string }) {
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
  const blockedReasons = [...new Set(blocked.map((b) => b.reason))].join(", ");
  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-1", className)}>
      <span className="text-caption-md-regular text-tertiary">{t("project_hub.discussion.used_sources")}:</span>
      {used.length === 0 && <span className="text-caption-md-regular text-placeholder">—</span>}
      {used.map((label) => (
        <HubChip key={label} variant="soft" icon={TickCircleOutline as TGlyph} label={label} />
      ))}
      {"model" in context && context.model && (
        <HubChip variant="outline" icon={AiStarOneOutline as TGlyph} label={context.model} />
      )}
      {blocked.length > 0 && (
        <HubChip
          variant="outline"
          icon={LockOutline as TGlyph}
          label={t("project_hub.discussion.blocked_count", { count: blocked.length })}
          title={`${t("project_hub.discussion.blocked_sources")}: ${blockedReasons}`}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------------------------------
 * Message
 * -----------------------------------------------------------------------------------------------*/

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
  const { formatDateTime, formatAge } = useHubFormatters();
  const [showThread, setShowThread] = useState(true);

  const renderOne = (m: TPHMessage, nested = false) => {
    const isSelected = selected.has(m.id);
    const author =
      m.author_kind === "ai"
        ? t("project_hub.discussion.ai_badge")
        : m.author_kind === "system"
          ? t("project_hub.discussion.system")
          : displayName(m.author_id);
    return (
      <div
        key={m.id}
        className={cn(
          "group/msg relative flex min-w-0 items-start gap-2 rounded-md py-1.5 pr-2 pl-2 transition-colors duration-100 hover:bg-layer-transparent-hover",
          isSelected && "bg-accent-primary/10 hover:bg-accent-primary/10",
          nested && "ml-7"
        )}
      >
        <span
          className={cn(
            "absolute top-2 -left-5 flex opacity-0 transition-opacity duration-100 group-hover/msg:opacity-100 focus-within:opacity-100",
            isSelected && "opacity-100"
          )}
        >
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => onToggle(m.id)}
            aria-label={`${t("project_hub.discussion.select_message")}: ${m.body.slice(0, 40)}`}
          />
        </span>
        <AuthorAvatar kind={m.author_kind} userId={m.author_id} className="mt-px" />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 items-center gap-1.5 text-13 leading-5">
            <span className="truncate font-medium text-primary">{author}</span>
            {m.author_kind === "ai" && (
              <HubChip variant="soft" tone="info" label={t("project_hub.discussion.ai_answer_hint")} />
            )}
            <span
              className="shrink-0 text-caption-md-regular text-tertiary tabular-nums"
              title={formatDateTime(m.created_at)}
            >
              {formatAge(m.created_at)}
            </span>
            {m.edited_at && (
              <span className="shrink-0 text-caption-md-regular text-placeholder">
                ({t("project_hub.discussion.edited")})
              </span>
            )}
            <span className="ml-auto flex shrink-0 items-center opacity-0 transition-opacity duration-100 group-hover/msg:opacity-100 focus-within:opacity-100">
              {!nested && (
                <IconButton
                  variant="ghost"
                  size="xs"
                  aria-label={t("project_hub.discussion.reply")}
                  icon={<Icon icon={ReplyOutline} />}
                  onClick={() => onReply(m.id)}
                />
              )}
            </span>
          </div>
          <p className="text-13 leading-5 break-words whitespace-pre-wrap text-primary">{m.body}</p>
          {m.author_kind === "ai" && m.ai_context && "visible" in m.ai_context && (
            <SourceChips context={m.ai_context as TPHAiContext} className="pt-0.5" />
          )}
        </div>
      </div>
    );
  };

  return (
    <li className="flex min-w-0 flex-col">
      {renderOne(message)}
      {replies.length > 0 && (
        <button
          type="button"
          aria-expanded={showThread}
          className="ml-9 flex h-6 w-fit items-center gap-1 rounded-sm px-1 text-caption-md-regular text-accent-primary transition-colors duration-100 hover:bg-layer-transparent-hover focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
          onClick={() => setShowThread((v) => !v)}
        >
          <ChatOutline className="size-3" aria-hidden="true" />
          {showThread
            ? t("project_hub.discussion.hide_replies")
            : t("project_hub.discussion.replies", { count: replies.length })}
        </button>
      )}
      {showThread && replies.map((r) => renderOne(r, true))}
    </li>
  );
});

/* -------------------------------------------------------------------------------------------------
 * Conversation
 * -----------------------------------------------------------------------------------------------*/

type Props = {
  workspaceSlug: string;
  conversation: TPHConversation;
  /** Target package for decisions (package thread / package context). */
  issueId?: string | null;
  className?: string;
};

/**
 * Conversation (S09 / package thread): compact message list (20px avatar, name, time, text), a
 * Linear-style comment box at the bottom, message selection with a stable selection marker,
 * @AI with visible context (used + blocked sources as chips) and the decision preview → confirm flow.
 */
export const ConversationView = observer(function ConversationView({
  workspaceSlug,
  conversation,
  issueId,
  className,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const displayName = useMemberDisplayName();
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

  const { topLevel, repliesByParent, byId } = useMemo(() => {
    const list = messages.data ?? [];
    const map = new Map<string, TPHMessage[]>();
    for (const m of list) {
      if (m.parent_id) map.set(m.parent_id, [...(map.get(m.parent_id) ?? []), m]);
    }
    return {
      topLevel: list.filter((m) => !m.parent_id),
      repliesByParent: map,
      byId: new Map(list.map((m) => [m.id, m])),
    };
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

  const onComposerKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void send();
    }
  };

  const decisionProjectId = conversation.project_id;
  const replyTarget = replyTo ? byId.get(replyTo) : undefined;
  const replyAuthor = replyTarget
    ? replyTarget.author_kind === "ai"
      ? t("project_hub.discussion.ai_badge")
      : replyTarget.author_kind === "system"
        ? t("project_hub.discussion.system")
        : displayName(replyTarget.author_id)
    : "";

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pt-3 pb-2 md:px-6">
        {conversation.kind === "direct" && (
          <p className="flex items-center gap-1.5 pb-2 text-caption-md-regular text-tertiary">
            <LockOutline className="size-3 shrink-0" aria-hidden="true" />
            {t("project_hub.messages.private_notice")}
          </p>
        )}
        <HubResourceBoundary
          resource={messages}
          loadingRows={3}
          size="sm"
          isEmpty={(d) => d.length === 0}
          empty={
            <HubEmptyState
              size="sm"
              icon={ChatOutline as TGlyph}
              title={t("project_hub.discussion.empty")}
              description={t("project_hub.discussion.empty_hint")}
            />
          }
        >
          {() => (
            <ul className="flex flex-col pl-5" aria-live="polite">
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
      </div>

      <div className="flex shrink-0 flex-col gap-2 border-t border-subtle px-4 py-3 md:px-6">
        {selected.size > 0 && (
          <div
            role="toolbar"
            aria-label={t("project_hub.discussion.selected", { count: selected.size })}
            className="flex h-8 items-center gap-2 rounded-md bg-layer-2 pr-1 pl-2.5 text-caption-md-regular"
          >
            <span className="font-medium text-primary">
              {t("project_hub.discussion.selected", { count: selected.size })}
            </span>
            <span className="flex-1" />
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
          className="flex flex-col overflow-hidden rounded-md border border-subtle bg-layer-1 transition-colors duration-100 focus-within:border-accent-strong"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          {replyTarget && (
            <div className="flex h-7 items-center gap-1.5 border-b border-subtle bg-layer-2 pr-1 pl-3 text-caption-md-regular text-tertiary">
              <ReplyOutline className="size-3 shrink-0" aria-hidden="true" />
              <span className="min-w-0 truncate">
                {t("project_hub.discussion.replying_to", { name: replyAuthor })}
                <span className="text-placeholder"> · {replyTarget.body}</span>
              </span>
              <span className="flex-1" />
              <IconButton
                variant="ghost"
                size="xs"
                aria-label={t("project_hub.common.cancel")}
                icon={<Icon icon={CloseOutline} />}
                onClick={() => setReplyTo(null)}
              />
            </div>
          )}
          <label htmlFor={`composer-${conversation.id}`} className="sr-only">
            {t("project_hub.discussion.title")}
          </label>
          <TextArea
            id={`composer-${conversation.id}`}
            size="md"
            surface="embedded"
            autoResize
            maxRows={10}
            placeholder={t("project_hub.discussion.placeholder")}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={onComposerKeyDown}
          />
          {mentionsAi && (
            <div className="px-3 pb-2" aria-live="polite">
              {contextPreview ? (
                <SourceChips context={contextPreview} />
              ) : (
                <span className="text-caption-md-regular text-tertiary">{t("project_hub.common.loading")}</span>
              )}
            </div>
          )}
          <div className="flex h-9 items-center gap-1 border-t border-subtle px-2">
            <span className="hidden text-caption-md-regular text-placeholder sm:inline">
              {t("project_hub.discussion.composer_hint")}
            </span>
            <span className="flex-1" />
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              label={t("project_hub.discussion.mark_read")}
              onClick={() => void markRead()}
            />
            <Button
              type="submit"
              variant="primary"
              size="sm"
              stretch="auto"
              loading={isSending}
              disabled={!body.trim()}
              icon={<Icon icon={SendOutline} />}
              label={isSending ? t("project_hub.discussion.sending") : t("project_hub.discussion.send")}
            />
          </div>
        </form>
      </div>

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
