/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Avatar } from "@makeplane/propel/components/avatar";
import { Button } from "@makeplane/propel/components/button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { Icon } from "@makeplane/propel/components/icon";
import { AddOutline, CloseOutline, ShieldOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TProjectHubCapability, TProjectHubCapabilityGrant } from "@plane/types";
import { getFileURL } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { useMemberDisplayName } from "../common/member-name";
import { HubSelect } from "../common/select";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { SettingsCard, SettingsConfirmDialog, SettingsSection } from "./settings-rows";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

export const PROJECT_HUB_CAPABILITIES: TProjectHubCapability[] = [
  "project.read",
  "package.edit",
  "package.approve_execution",
  "run.start",
  "run.cancel",
  "review.approve_code",
  "review.accept_outcome",
  "merge.request",
  "decision.publish",
  "project.plan",
  "integration.manage",
  "workspace.admin",
];

export const capabilityLabelKey = (capability: string) => `project_hub.capability.${capability.replace(".", "_")}`;
export const capabilityDescriptionKey = (capability: string) =>
  `project_hub.capability_description.${capability.replace(".", "_")}`;

const WORKSPACE_WIDE = "__workspace__";

type TAddDraft = { member: string | null; capability: string | null; project: string };

/** One capability chip with a description tooltip and a quiet remove control. */
function GrantChip({
  grant,
  projectName,
  onRemove,
}: {
  grant: TProjectHubCapabilityGrant;
  projectName?: string;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const label = t(capabilityLabelKey(grant.capability));
  const description = t(capabilityDescriptionKey(grant.capability));
  return (
    <Tooltip label={projectName ? `${description} · ${projectName}` : description} layout="stacked">
      <span className="inline-flex max-w-full">
        <HubChip
          label={projectName ? `${label} · ${projectName}` : label}
          tone={projectName ? "info" : "neutral"}
          trailing={
            <button
              type="button"
              aria-label={t("project_hub.settings.revoke_grant_label", { capability: label })}
              onClick={onRemove}
              className="-mr-0.5 flex size-3.5 items-center justify-center rounded-full text-tertiary transition-colors duration-100 hover:bg-layer-transparent-hover hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
            >
              <CloseOutline className="size-2.5" aria-hidden="true" />
            </button>
          }
        />
      </span>
    </Tooltip>
  );
}

/** Explicit capability grants — native roles do not imply run/review/merge rights (PRD §5.2). */
export const GrantsSection = observer(function GrantsSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const displayName = useMemberDisplayName();
  const { joinedProjectIds, getPartialProjectById } = useProject();
  const {
    workspace: { workspaceMemberIds },
    getUserDetails,
  } = useMember();
  const grants = useHubResource<TProjectHubCapabilityGrant[]>(PH_KEYS.grants(workspaceSlug), () =>
    store.packageService.listCapabilityGrants(workspaceSlug)
  );
  const [draft, setDraft] = useState<TAddDraft | null>(null);
  const [revoking, setRevoking] = useState<TProjectHubCapabilityGrant | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const openAdd = (memberId: string | null = null) =>
    setDraft({ member: memberId, capability: null, project: WORKSPACE_WIDE });

  const add = async () => {
    if (!draft?.member || !draft.capability) return;
    setBusy("add");
    try {
      await store.packageService.createCapabilityGrant(workspaceSlug, {
        member_id: draft.member,
        capability: draft.capability as TProjectHubCapability,
        ...(draft.project !== WORKSPACE_WIDE ? { project_id: draft.project } : {}),
      });
      showHubSuccessToast(t("project_hub.settings.grant_saved"));
      store.invalidate(PH_KEYS.grants(workspaceSlug));
      setDraft(null);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const revoke = async () => {
    if (!revoking) return;
    setBusy(revoking.id);
    try {
      await store.packageService.revokeCapabilityGrant(workspaceSlug, revoking.id);
      showHubSuccessToast(t("project_hub.settings.grant_revoked"));
      store.invalidate(PH_KEYS.grants(workspaceSlug));
      setRevoking(null);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const memberOptions = useMemo(
    () => (workspaceMemberIds ?? []).map((id) => ({ value: id, label: displayName(id) })),
    [workspaceMemberIds, displayName]
  );
  const projectName = (projectId: string | null | undefined) =>
    projectId ? (getPartialProjectById(projectId)?.name ?? projectId) : undefined;

  const grantAction = (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      label={t("project_hub.settings.grant_add")}
      onClick={() => openAdd()}
    />
  );

  return (
    <SettingsSection
      title={t("project_hub.settings.grants")}
      description={t("project_hub.settings.grants_description")}
      actions={grantAction}
    >
      <HubResourceBoundary
        resource={grants}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={
          <HubEmptyState
            size="sm"
            icon={ShieldOutline as TGlyph}
            title={t("project_hub.settings.grants_empty_title")}
            description={t("project_hub.settings.grants_empty")}
            action={
              <Button
                variant="tertiary"
                size="sm"
                stretch="auto"
                label={t("project_hub.settings.grant_add")}
                onClick={() => openAdd()}
              />
            }
          />
        }
      >
        {(data) => {
          // Group by member, keeping the capability order of the catalogue inside each group.
          const byMember = new Map<string, TProjectHubCapabilityGrant[]>();
          for (const grant of data) byMember.set(grant.member_id, [...(byMember.get(grant.member_id) ?? []), grant]);
          const order = (c: string) => {
            const index = PROJECT_HUB_CAPABILITIES.indexOf(c as TProjectHubCapability);
            return index === -1 ? PROJECT_HUB_CAPABILITIES.length : index;
          };
          const members = [...byMember.entries()]
            .map(([memberId, list]) => ({
              memberId,
              // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
              list: [...list].sort((a, b) => order(a.capability) - order(b.capability)),
            }))
            // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
            .sort((a, b) => displayName(a.memberId).localeCompare(displayName(b.memberId)));
          return (
            <SettingsCard aria-label={t("project_hub.settings.grants")}>
              {members.map(({ memberId, list }) => {
                const user = getUserDetails(memberId);
                const name = displayName(memberId);
                return (
                  <div key={memberId} className="flex min-w-0 flex-col border-b border-subtle last:border-b-0">
                    <div className="flex h-9 min-w-0 items-center gap-2 pr-1.5 pl-3">
                      <Avatar
                        size="xs"
                        alt={name}
                        fallback={name[0]?.toUpperCase()}
                        src={user?.avatar_url ? getFileURL(user.avatar_url) : undefined}
                      />
                      <span className="min-w-0 truncate text-13 font-medium text-primary">{name}</span>
                      <span className="shrink-0 text-caption-md-regular text-tertiary">
                        {t("project_hub.settings.grant_count", { count: list.length })}
                      </span>
                      <span className="flex-1" />
                      <Button
                        variant="ghost"
                        size="sm"
                        stretch="auto"
                        icon={<Icon icon={AddOutline} />}
                        label={t("project_hub.settings.grant_add")}
                        onClick={() => openAdd(memberId)}
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-1 pr-3 pb-2 pl-10">
                      {list.map((grant) => (
                        <GrantChip
                          key={grant.id}
                          grant={grant}
                          projectName={projectName(grant.project_id)}
                          onRemove={() => setRevoking(grant)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </SettingsCard>
          );
        }}
      </HubResourceBoundary>

      <HubDialog
        isOpen={!!draft}
        onClose={() => setDraft(null)}
        isBusy={busy === "add"}
        title={t("project_hub.settings.grant_dialog_title")}
        onSubmit={() => void add()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setDraft(null)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "add"}
              disabled={!draft?.member || !draft?.capability}
              label={t("project_hub.settings.grant_add")}
            />
          </>
        }
      >
        {draft && (
          <>
            <HubSelect
              label={t("project_hub.settings.grant_member")}
              value={draft.member}
              onChange={(v) => setDraft((d) => (d ? { ...d, member: v } : d))}
              options={memberOptions}
            />
            <div className="flex flex-col gap-1">
              <HubSelect
                label={t("project_hub.settings.grant_capability")}
                value={draft.capability}
                onChange={(v) => setDraft((d) => (d ? { ...d, capability: v } : d))}
                options={PROJECT_HUB_CAPABILITIES.map((c) => ({ value: c, label: t(capabilityLabelKey(c)) }))}
              />
              <p className="text-caption-sm-regular text-tertiary">
                {draft.capability
                  ? t(capabilityDescriptionKey(draft.capability))
                  : t("project_hub.settings.grant_capability_hint")}
              </p>
            </div>
            <HubSelect
              label={t("project_hub.settings.grant_project")}
              value={draft.project}
              onChange={(v) => setDraft((d) => (d ? { ...d, project: v } : d))}
              options={[
                { value: WORKSPACE_WIDE, label: t("project_hub.common.workspace") },
                ...joinedProjectIds.map((id) => ({ value: id, label: getPartialProjectById(id)?.name ?? id })),
              ]}
            />
          </>
        )}
      </HubDialog>

      <SettingsConfirmDialog
        isOpen={!!revoking}
        busy={!!revoking && busy === revoking.id}
        title={t("project_hub.settings.revoke_confirm_title")}
        description={
          revoking &&
          t("project_hub.settings.revoke_confirm_description", {
            capability: t(capabilityLabelKey(revoking.capability)),
            member: displayName(revoking.member_id),
            scope: projectName(revoking.project_id) ?? t("project_hub.common.workspace"),
          })
        }
        confirmLabel={t("project_hub.settings.grant_revoke")}
        onConfirm={() => void revoke()}
        onClose={() => setRevoking(null)}
      />
    </SettingsSection>
  );
});
