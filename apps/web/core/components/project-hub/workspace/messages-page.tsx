/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "next/navigation";
// plane imports
import { Button } from "@makeplane/propel/components/button";
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
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useMemberDisplayName } from "../common/member-name";
import { HubPage } from "../common/page";
import { HubSelect } from "../common/select";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";

const GROUPS: { kind: TConversationKind; i18n: string }[] = [
  { kind: "project", i18n: "project_hub.messages.project_channels" },
  { kind: "package", i18n: "project_hub.messages.package_threads" },
  { kind: "direct", i18n: "project_hub.messages.direct_messages" },
];

/** S09 Messages: project channels, package threads, DMs; the selected conversation opens beside the list. */
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
  const selectedId = searchParams.get("c");
  const conversations = useHubResource<TPHConversation[]>(PH_KEYS.conversations(workspaceSlug), () =>
    store.collaborationService.listConversations(workspaceSlug)
  );
  const notifications = useHubResource<TPHNotificationItem[]>(PH_KEYS.notifications(workspaceSlug), () =>
    store.collaborationService.listNotifications(workspaceSlug)
  );
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
    if (c.kind === "direct") return c.participant_ids.map(displayName).join(", ");
    return c.id;
  };

  return (
    <HubPage
      title={t("project_hub.messages.title")}
      className="max-w-none"
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("project_hub.common.create")}
          onClick={() => setIsCreateOpen(true)}
        />
      }
    >
      <HubResourceBoundary
        resource={conversations}
        loadingRows={5}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.messages.empty")} />}
      >
        {(data) => {
          const selected = data.find((c) => c.id === selectedId);
          return (
            <div className="flex flex-col gap-4 lg:flex-row">
              <nav
                aria-label={t("project_hub.messages.conversations")}
                className="flex w-full shrink-0 flex-col gap-4 lg:w-72"
              >
                {mentions.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <h2 className="text-caption-md-medium text-tertiary">{t("project_hub.messages.mentions")}</h2>
                    <ul className="flex flex-col gap-0.5">
                      {mentions.map((n) => (
                        <li key={n.id}>
                          <button
                            type="button"
                            disabled={!n.target.id}
                            onClick={() => n.target.id && select(n.target.id)}
                            className="focus-visible:outline-accent-primary flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-body-xs-regular text-secondary hover:bg-layer-transparent-hover focus-visible:outline-2"
                          >
                            <span aria-hidden="true">@</span>
                            <span className="truncate">{n.title}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {GROUPS.map((group) => {
                  const items = data.filter((c) => c.kind === group.kind);
                  if (items.length === 0) return null;
                  return (
                    <div key={group.kind} className="flex flex-col gap-1">
                      <h2 className="text-caption-md-medium text-tertiary">{t(group.i18n)}</h2>
                      <ul className="flex flex-col gap-0.5">
                        {items.map((c) => (
                          <li key={c.id}>
                            <button
                              type="button"
                              aria-current={c.id === selectedId ? "true" : undefined}
                              onClick={() => select(c.id)}
                              className={cn(
                                "focus-visible:outline-accent-primary flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-body-xs-regular focus-visible:outline-2",
                                c.id === selectedId
                                  ? "bg-layer-transparent-selected text-primary"
                                  : "text-secondary hover:bg-layer-transparent-hover"
                              )}
                            >
                              <span className="truncate">{labelOf(c)}</span>
                              {(c.unread_count ?? 0) > 0 && (
                                <span className="shrink-0 text-caption-sm-medium text-accent-primary">
                                  {t("project_hub.messages.unread", { count: c.unread_count })}
                                </span>
                              )}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </nav>
              <section
                aria-label={selected ? labelOf(selected) : t("project_hub.messages.title")}
                className="min-w-0 flex-1"
              >
                {selected ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-0.5 border-b border-subtle pb-2">
                      <h2 className="text-body-sm-semibold text-primary">{labelOf(selected)}</h2>
                      {selected.project_id && (
                        <p className="text-caption-sm-regular text-tertiary">
                          {t("project_hub.messages.context", {
                            name: getPartialProjectById(selected.project_id)?.name ?? selected.project_id,
                          })}
                        </p>
                      )}
                      <p className="text-caption-sm-regular text-tertiary">
                        {t("project_hub.messages.participants")}:{" "}
                        {selected.participant_ids.map(displayName).join(", ") || "—"}
                      </p>
                    </div>
                    <ConversationView key={selected.id} workspaceSlug={workspaceSlug} conversation={selected} />
                  </div>
                ) : (
                  <HubEmpty title={t("project_hub.messages.select_conversation")} />
                )}
              </section>
            </div>
          );
        }}
      </HubResourceBoundary>

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
