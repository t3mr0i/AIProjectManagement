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
import type { TProjectHubCapability, TProjectHubCapabilityGrant } from "@plane/types";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useMemberDisplayName } from "../common/member-name";
import { HubSection } from "../common/section";
import { HubSelect } from "../common/select";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";

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

const WORKSPACE_WIDE = "__workspace__";

/** Explicit capability grants — native roles do not imply run/review/merge rights (PRD §5.2). */
export const GrantsSection = observer(function GrantsSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const displayName = useMemberDisplayName();
  const { joinedProjectIds, getPartialProjectById } = useProject();
  const {
    workspace: { workspaceMemberIds },
  } = useMember();
  const grants = useHubResource<TProjectHubCapabilityGrant[]>(PH_KEYS.grants(workspaceSlug), () =>
    store.packageService.listCapabilityGrants(workspaceSlug)
  );
  const [member, setMember] = useState<string | null>(null);
  const [capability, setCapability] = useState<string | null>(null);
  const [project, setProject] = useState<string>(WORKSPACE_WIDE);
  const [busy, setBusy] = useState<string | null>(null);

  const add = async () => {
    if (!member || !capability) return;
    setBusy("add");
    try {
      await store.packageService.createCapabilityGrant(workspaceSlug, {
        member_id: member,
        capability: capability as TProjectHubCapability,
        ...(project !== WORKSPACE_WIDE ? { project_id: project } : {}),
      });
      showHubSuccessToast(t("project_hub.settings.grant_saved"));
      store.invalidate(PH_KEYS.grants(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const revoke = async (grant: TProjectHubCapabilityGrant) => {
    setBusy(grant.id);
    try {
      await store.packageService.revokeCapabilityGrant(workspaceSlug, grant.id);
      showHubSuccessToast(t("project_hub.settings.grant_revoked"));
      store.invalidate(PH_KEYS.grants(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <HubSection title={t("project_hub.settings.grants")} as="h2">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <HubSelect
          label={t("project_hub.settings.grant_member")}
          value={member}
          onChange={setMember}
          options={(workspaceMemberIds ?? []).map((id) => ({ value: id, label: displayName(id) }))}
        />
        <HubSelect
          label={t("project_hub.settings.grant_capability")}
          value={capability}
          onChange={setCapability}
          options={PROJECT_HUB_CAPABILITIES.map((c) => ({ value: c, label: t(capabilityLabelKey(c)) }))}
        />
        <HubSelect
          label={t("project_hub.settings.grant_project")}
          value={project}
          onChange={setProject}
          options={[
            { value: WORKSPACE_WIDE, label: t("project_hub.common.workspace") },
            ...joinedProjectIds.map((id) => ({ value: id, label: getPartialProjectById(id)?.name ?? id })),
          ]}
        />
        <Button
          type="submit"
          variant="primary"
          size="sm"
          stretch="auto"
          loading={busy === "add"}
          disabled={!member || !capability}
          label={t("project_hub.settings.grant_add")}
        />
      </form>
      <HubResourceBoundary
        resource={grants}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.settings.grants_empty")} />}
      >
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-body-xs-regular">
              <caption className="sr-only">{t("project_hub.settings.grants")}</caption>
              <thead>
                <tr className="border-b border-subtle text-tertiary">
                  <th scope="col" className="py-1.5 pr-3 font-medium">
                    {t("project_hub.settings.grant_member")}
                  </th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">
                    {t("project_hub.settings.grant_capability")}
                  </th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">
                    {t("project_hub.common.project")}
                  </th>
                  <th scope="col" className="py-1.5 font-medium">
                    <span className="sr-only">{t("project_hub.settings.grant_revoke")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((grant) => (
                  <tr key={grant.id} className="border-b border-subtle">
                    <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                      {displayName(grant.member_id)}
                    </th>
                    <td className="py-1.5 pr-3 text-secondary">{t(capabilityLabelKey(grant.capability))}</td>
                    <td className="py-1.5 pr-3 text-secondary">
                      {grant.project_id
                        ? (getPartialProjectById(grant.project_id)?.name ?? grant.project_id)
                        : t("project_hub.common.workspace")}
                    </td>
                    <td className="py-1.5 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        stretch="auto"
                        loading={busy === grant.id}
                        label={t("project_hub.settings.grant_revoke")}
                        onClick={() => void revoke(grant)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </HubResourceBoundary>
    </HubSection>
  );
});
