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
import { Switch } from "@makeplane/propel/components/switch";
import { LayerStackOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TProjectHubActivation } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextAreaField } from "../common/field";
import { HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { SettingsCard, SettingsRow, SettingsSection } from "./settings-rows";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

type TPending = { scope: "workspace" } | { scope: "project"; projectId: string; name: string };

/** Audited activation per workspace / project (FR-B04). Every change requires a reason. */
export const ActivationSection = observer(function ActivationSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { getPartialProjectById, joinedProjectIds } = useProject();
  const activation = useHubResource<TProjectHubActivation>(PH_KEYS.activation(workspaceSlug), () =>
    store.packageService.getActivation(workspaceSlug)
  );
  const [pending, setPending] = useState<(TPending & { next: boolean }) | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!pending || !reason.trim()) return;
    setBusy(true);
    try {
      if (pending.scope === "workspace") {
        await store.packageService.setWorkspaceActivation(workspaceSlug, {
          is_enabled: pending.next,
          reason: reason.trim(),
        });
      } else {
        await store.packageService.setProjectActivation(workspaceSlug, pending.projectId, {
          is_enabled: pending.next,
          reason: reason.trim(),
        });
      }
      showHubSuccessToast(t("project_hub.settings.activation_saved"));
      setPending(null);
      setReason("");
      store.invalidate(PH_KEYS.activation(workspaceSlug));
      // capability/flag cache must be refreshed for navigation and gates
      store.invalidate(`ph:caps:${workspaceSlug}:`);
      await store.fetchCapabilities(workspaceSlug);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    if (busy) return;
    setPending(null);
    setReason("");
  };

  return (
    <SettingsSection
      title={t("project_hub.settings.activation")}
      description={t("project_hub.settings.activation_description")}
    >
      <HubResourceBoundary resource={activation} loadingRows={2}>
        {(data) => {
          const projectIds = [...new Set([...joinedProjectIds, ...data.projects.map((p) => p.project_id)])];
          const enabledCount = projectIds.filter(
            (id) => data.projects.find((p) => p.project_id === id)?.is_enabled ?? false
          ).length;
          return (
            <SettingsCard aria-label={t("project_hub.settings.activation")}>
              <SettingsRow
                title={t("project_hub.settings.workspace_enabled")}
                description={t("project_hub.settings.workspace_enabled_description")}
                control={
                  <Switch
                    size="sm"
                    aria-label={t("project_hub.settings.workspace_enabled")}
                    checked={data.workspace_enabled}
                    onCheckedChange={(checked) => setPending({ scope: "workspace", next: checked })}
                  />
                }
              />
              <SettingsCard
                title={t("project_hub.settings.project_activation")}
                icon={LayerStackOutline as TGlyph}
                count={projectIds.length}
                trailing={
                  <span className="text-caption-md-regular text-tertiary">
                    {t("project_hub.settings.projects_enabled_count", { count: enabledCount })}
                  </span>
                }
                className="rounded-none border-0 border-t border-subtle"
              >
                {projectIds.map((projectId) => {
                  const enabled = data.projects.find((p) => p.project_id === projectId)?.is_enabled ?? false;
                  const name = getPartialProjectById(projectId)?.name ?? projectId;
                  return (
                    <SettingsRow
                      key={projectId}
                      indent
                      title={name}
                      disabled={!data.workspace_enabled}
                      description={!data.workspace_enabled ? t("project_hub.settings.requires_workspace") : undefined}
                      control={
                        <Switch
                          size="sm"
                          aria-label={`${t("project_hub.settings.activation")}: ${name}`}
                          checked={enabled}
                          disabled={!data.workspace_enabled}
                          onCheckedChange={(checked) =>
                            setPending({ scope: "project", projectId, name, next: checked })
                          }
                        />
                      }
                    />
                  );
                })}
              </SettingsCard>
            </SettingsCard>
          );
        }}
      </HubResourceBoundary>
      <HubDialog
        isOpen={!!pending}
        onClose={close}
        isBusy={busy}
        title={
          pending?.scope === "project"
            ? `${t("project_hub.settings.activation")}: ${pending.name}`
            : t("project_hub.settings.workspace_enabled")
        }
        onSubmit={() => void submit()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={close}
            />
            <Button
              type="submit"
              variant={pending?.next ? "primary" : "danger"}
              size="md"
              stretch="auto"
              loading={busy}
              disabled={!reason.trim()}
              label={pending?.next ? t("project_hub.settings.enable") : t("project_hub.settings.disable")}
            />
          </>
        }
      >
        <p className="text-13 text-secondary">
          {pending?.next
            ? t("project_hub.settings.activation_enable_description")
            : t("project_hub.settings.activation_disable_description")}
        </p>
        <HubTextAreaField
          label={t("project_hub.settings.reason")}
          placeholder={t("project_hub.settings.reason_placeholder")}
          hint={t("project_hub.settings.reason_required")}
          value={reason}
          required
          onChange={setReason}
        />
      </HubDialog>
    </SettingsSection>
  );
});
