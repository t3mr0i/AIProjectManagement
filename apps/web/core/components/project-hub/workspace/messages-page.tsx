/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "next/navigation";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import {
  ArrowNarrowLeftOutline,
  ChatOutline,
  CubeOutline,
  HashOutline,
  NewChatOutline,
  ProjectsOutline,
  UserOutline,
} from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import type { TConversationKind, TPHConversation, TPHNotificationItem } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { useAppRouter } from "@/hooks/use-app-router";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { ConversationView } from "../discussion/conversation-view";
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { HubList, HubListGroup, useHubListNavigation } from "../common/list";
import { useMemberDisplayName } from "../common/member-name";
import { HubPage } from "../common/page";
import { HubSelect } from "../common/select";
import { HubEmptyState, HubErrorState, HubFreshnessBanner, HubLoading } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const GROUPS: { kind: TConversationKind; i18n: string; icon: TGlyph }[] = [
  { kind: "project", i18n: "project_hub.messages.project_channels", icon: HashOutline as TGlyph },
  { kind: "package", i18n: "project_hub.messages.package_threads", icon: CubeOutline as TGlyph },
  { kind: "direct", i18n: "project_hub.messages.direct_messages", icon: UserOutline as TGlyph },
];

const KIND_ICON: Record<TConversationKind, TGlyph> = {
  project: HashOutline as TGlyph,
  package: CubeOutline as TGlyph,
  direct: UserOutline as TGlyph,
};

/* -------------------------------------------------------------------------------------------------
 * Inbox rows (two lines: title + time, muted context — Linear inbox)
 * -----------------------------------------------------------------------------------------------*/

type TInboxRowProps = {
  icon: TGlyph;
  title: string;
  subtitle?: string;
  time?: string;
  timeTitle?: string;
  unread?: boolean;
  selected?: boolean;
  disabled?: boolean;
  onClick: () => void;
};

function InboxRow({
  icon: Glyph,
  title,
  subtitle,
  time,
  timeTitle,
  unread,
  selected,
  disabled,
  onClick,
}: TInboxRowProps) {
  return (
    <button
      type="button"
      data-hub-row=""
      aria-current={selected ? "true" : undefined}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "relative flex h-12 w-full min-w-0 items-center gap-2 border-b border-subtle pr-3 pl-2 text-left transition-colors duration-100 last:border-b-0 focus-visible:bg-accent-primary/10 focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none focus-visible:ring-inset",
        selected ? "bg-layer-transparent-selected" : "hover:bg-layer-transparent-hover",
        disabled && "cursor-default opacity-60"
      )}
    >
      <span className="flex w-2 shrink-0 items-center justify-center" aria-hidden="true">
        {unread && <span className="block size-1.5 rounded-full bg-accent-primary" />}
      </span>
      <Glyph className={cn("size-4 shrink-0", unread ? "text-primary" : "text-tertiary")} aria-hidden="true" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex min-w-0 items-center gap-2">
          <span className={cn("min-w-0 flex-1 truncate text-13 leading-5 text-primary", unread && "font-medium")}>
            {title}
          </span>
          {time && (
            <span className="shrink-0 text-caption-md-regular text-tertiary tabular-nums" title={timeTitle}>
              {time}
            </span>
          )}
        </span>
        {subtitle && <span className="truncate text-caption-md-regular leading-4 text-tertiary">{subtitle}</span>}
      </span>
    </button>
  );
}

/* -------------------------------------------------------------------------------------------------
 * Page
 * -----------------------------------------------------------------------------------------------*/

/** S09 Messages, two-pane: inbox-style list (channels, package threads, DMs) on the left, conversation on the right. */
export const WorkspaceMessagesPage = observer(function WorkspaceMessagesPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const router = useAppRouter();
  const searchParams = useSearchParams();
  const { getPartialProjectById, joinedProjectIds } = useProject();
  const {
    workspace: { workspaceMemberIds },
  } = useMember();
  const displayName = useMemberDisplayName();
  const { formatAge, formatDateTime } = useHubFormatters();
  const listRef = useRef<HTMLElement>(null);
  const onListKeyDown = useHubListNavigation(listRef);
  const selectedId = searchParams.get("c");
  const conversations = useHubResource<TPHConversation[]>(PH_KEYS.conversations(workspaceSlug), () =>
    store.collaborationService.listConversations(workspaceSlug)
  );
  const notifications = useHubResource<TPHNotificationItem[]>(PH_KEYS.notifications(workspaceSlug), async () => {
    const n = await store.collaborationService.listNotifications(workspaceSlug);
    return [...n.targeted, ...n.bundled];
  });
  const mentions = (notifications.data ?? []).filter((n) => n.category === "mention" && !n.read_at);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKind, setNewKind] = useState<"project" | "direct">("project");
  const [newProject, setNewProject] = useState<string | null>(null);
  const [newMember, setNewMember] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const select = (id: string) => router.push(`/${workspaceSlug}/hub/messages?c=${id}`);

  const create = async () => {
    setBusy(true);
    try {
      const created = await store.collaborationService.createConversation(workspaceSlug, {
        kind: newKind,
        ...(newKind === "project" && newProject ? { project_id: newProject } : {}),
        ...(newKind === "direct" && newMember ? { participant_ids: [newMember] } : {}),
        ...(newTitle ? { title: newTitle } : {}),
      });
      setIsCreateOpen(false);
      store.invalidate(PH_KEYS.conversations(workspaceSlug));
      select(created.id);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  const labelOf = (c: TPHConversation) => {
    if (c.title) return c.title;
    if (c.kind === "project" && c.project_id) return getPartialProjectById(c.project_id)?.name ?? c.project_id;
    if (c.kind === "direct") return (c.participant_ids ?? []).map(displayName).join(", ");
    return c.id;
  };

  /** Muted second line: project context, participants or the unread count. */
  const subtitleOf = (c: TPHConversation) => {
    const parts: string[] = [];
    if (c.project_id) parts.push(getPartialProjectById(c.project_id)?.name ?? c.project_id);
    if (c.kind === "direct" && c.participant_ids?.length) parts.push(c.participant_ids.map(displayName).join(", "));
    if ((c.unread_count ?? 0) > 0) parts.push(t("project_hub.messages.unread", { count: c.unread_count }));
    return parts.join(" · ");
  };

  const data = conversations.data;
  const selected = data?.find((c) => c.id === selectedId);
  const selectedProject = selected?.project_id ? getPartialProjectById(selected.project_id) : undefined;
  const SelectedGlyph = selected ? KIND_ICON[selected.kind] : (ChatOutline as TGlyph);

  const newButton = (
    <IconButton
      variant="ghost"
      size="sm"
      aria-label={t("project_hub.messages.new_conversation")}
      icon={<Icon icon={NewChatOutline} />}
      onClick={() => setIsCreateOpen(true)}
    />
  );

  return (
    <HubPage title={t("project_hub.messages.title")} width="full" flush className="min-h-0 flex-1 overflow-hidden">
      {data === undefined ? (
        <div className="p-4 md:p-6">
          {conversations.error ? (
            <HubErrorState error={conversations.error} onRetry={() => void conversations.refresh()} />
          ) : (
            <HubLoading rows={5} />
          )}
        </div>
      ) : data.length === 0 ? (
        <HubEmptyState
          icon={ChatOutline as TGlyph}
          title={t("project_hub.messages.empty")}
          description={t("project_hub.messages.empty_hint")}
          className="my-auto"
          action={
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label={t("project_hub.messages.new_conversation")}
              onClick={() => setIsCreateOpen(true)}
            />
          }
        />
      ) : (
        <div className="flex h-full min-h-0 flex-1">
          <nav
            ref={listRef}
            onKeyDown={onListKeyDown}
            aria-label={t("project_hub.messages.conversations")}
            className={cn(
              "flex w-full shrink-0 flex-col border-subtle lg:w-80 lg:border-r",
              selected && "hidden lg:flex"
            )}
          >
            <div className="flex h-11 shrink-0 items-center gap-2 border-b border-subtle pr-2 pl-4">
              <span className="text-13 font-medium text-primary">{t("project_hub.messages.conversations")}</span>
              <span className="text-13 text-tertiary">{data.length}</span>
              <span className="flex-1" />
              {newButton}
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
              <div className="px-3 pt-2 empty:hidden">
                <HubFreshnessBanner resource={conversations} />
              </div>
              <HubListGroup
                icon={ChatOutline as TGlyph}
                title={t("project_hub.messages.mentions")}
                count={mentions.length}
              >
                <HubList>
                  {mentions.map((n) => (
                    <InboxRow
                      key={n.id}
                      icon={ChatOutline as TGlyph}
                      title={n.title}
                      subtitle={n.project_id ? (getPartialProjectById(n.project_id)?.name ?? n.project_id) : undefined}
                      time={formatAge(n.updated_at)}
                      timeTitle={formatDateTime(n.updated_at)}
                      unread
                      disabled={!n.target.id}
                      onClick={() => n.target.id && select(n.target.id)}
                    />
                  ))}
                </HubList>
              </HubListGroup>
              {GROUPS.map((group) => {
                const items = data.filter((c) => c.kind === group.kind);
                return (
                  <HubListGroup key={group.kind} icon={group.icon} title={t(group.i18n)} count={items.length}>
                    <HubList>
                      {items.map((c) => (
                        <InboxRow
                          key={c.id}
                          icon={KIND_ICON[c.kind]}
                          title={labelOf(c)}
                          subtitle={subtitleOf(c)}
                          time={formatAge(c.updated_at)}
                          timeTitle={formatDateTime(c.updated_at)}
                          unread={(c.unread_count ?? 0) > 0}
                          selected={c.id === selectedId}
                          onClick={() => select(c.id)}
                        />
                      ))}
                    </HubList>
                  </HubListGroup>
                );
              })}
            </div>
          </nav>

          <section
            aria-label={selected ? labelOf(selected) : t("project_hub.messages.title")}
            className={cn("flex min-w-0 flex-1 flex-col", !selected && "hidden lg:flex")}
          >
            {selected ? (
              <>
                <div className="flex h-11 shrink-0 items-center gap-2 border-b border-subtle px-3 md:px-4">
                  <span className="lg:hidden">
                    <IconButton
                      variant="ghost"
                      size="sm"
                      aria-label={t("project_hub.messages.conversations")}
                      icon={<Icon icon={ArrowNarrowLeftOutline} />}
                      onClick={() => router.push(`/${workspaceSlug}/hub/messages`)}
                    />
                  </span>
                  <SelectedGlyph className="size-4 shrink-0 text-tertiary" aria-hidden="true" />
                  <h2 className="min-w-0 truncate text-13 font-medium text-primary">{labelOf(selected)}</h2>
                  {selectedProject && (
                    <HubChip
                      label={selectedProject.name}
                      icon={
                        selectedProject.logo_props?.in_use ? (
                          <Logo logo={selectedProject.logo_props} size={12} />
                        ) : (
                          (ProjectsOutline as TGlyph)
                        )
                      }
                      href={`/${workspaceSlug}/projects/${selectedProject.id}/hub/activity`}
                      className="hidden sm:inline-flex"
                    />
                  )}
                  <span className="flex-1" />
                  {selected.kind === "direct" && (
                    <span
                      className="hidden max-w-64 truncate text-caption-md-regular text-tertiary md:inline"
                      title={(selected.participant_ids ?? []).map(displayName).join(", ")}
                    >
                      {(selected.participant_ids ?? []).map(displayName).join(", ") || "—"}
                    </span>
                  )}
                  {(selected.unread_count ?? 0) > 0 && (
                    <HubChip
                      variant="soft"
                      tone="info"
                      label={t("project_hub.messages.unread", { count: selected.unread_count })}
                    />
                  )}
                </div>
                <ConversationView key={selected.id} workspaceSlug={workspaceSlug} conversation={selected} />
              </>
            ) : (
              <HubEmptyState
                icon={ChatOutline as TGlyph}
                title={t("project_hub.messages.select_conversation")}
                className="my-auto"
              />
            )}
          </section>
        </div>
      )}

      <HubDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        isBusy={busy}
        title={t("project_hub.messages.new_conversation")}
        onSubmit={() => void create()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setIsCreateOpen(false)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy}
              disabled={newKind === "project" ? !newProject : !newMember}
              label={t("project_hub.common.create")}
            />
          </>
        }
      >
        <HubSelect
          label={t("project_hub.messages.kind")}
          value={newKind}
          onChange={(v) => setNewKind(v as "project" | "direct")}
          options={[
            { value: "project", label: t("project_hub.messages.project_channels") },
            { value: "direct", label: t("project_hub.messages.new_dm") },
          ]}
        />
        {newKind === "project" ? (
          <HubSelect
            label={t("project_hub.common.project")}
            value={newProject}
            onChange={setNewProject}
            options={joinedProjectIds.map((id) => ({ value: id, label: getPartialProjectById(id)?.name ?? id }))}
          />
        ) : (
          <HubSelect
            label={t("project_hub.common.member")}
            value={newMember}
            onChange={setNewMember}
            options={(workspaceMemberIds ?? []).map((id) => ({ value: id, label: displayName(id) }))}
          />
        )}
        <HubTextField label={t("project_hub.messages.conversation_title")} value={newTitle} onChange={setNewTitle} />
      </HubDialog>
    </HubPage>
  );
});
