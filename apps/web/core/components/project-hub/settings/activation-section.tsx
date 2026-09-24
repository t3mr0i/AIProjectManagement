/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import { useTranslation } from "@plane/i18n";
import type { TProjectHubActivation } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextAreaField } from "../common/field";
import { HubSection } from "../common/section";
import { HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";

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

  return (
    <HubSection title={t("project_hub.settings.activation")} as="h2">
      <HubResourceBoundary resource={activation} loadingRows={2}>
        {(data) => {
          const projectIds = [...new Set([...joinedProjectIds, ...data.projects.map((p) => p.project_id)])];
          return (
            <div className="flex flex-col gap-3">
              <label className="flex items-center justify-between gap-3 rounded-md border border-subtle px-3 py-2">
                <span className="text-body-xs-medium text-primary">{t("project_hub.settings.workspace_enabled")}</span>
                <Switch
                  size="sm"
                  checked={data.workspace_enabled}
                  onCheckedChange={(checked) => setPending({ scope: "workspace", next: checked })}
                />
              </label>
              <div className="flex flex-col gap-1">
                <p className="text-caption-md-medium text-tertiary">{t("project_hub.settings.project_activation")}</p>
                <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
                  {projectIds.map((projectId) => {
                    const enabled = data.projects.find((p) => p.project_id === projectId)?.is_enabled ?? false;
                    const name = getPartialProjectById(projectId)?.name ?? projectId;
                    return (
                      <li key={projectId}>
                        <label className="flex items-center justify-between gap-3 px-3 py-2">
                          <span className="text-body-xs-regular text-secondary">{name}</span>
                          <Switch
                            size="sm"
                            checked={enabled}
                            disabled={!data.workspace_enabled}
                            onCheckedChange={(checked) =>
                              setPending({ scope: "project", projectId, name, next: checked })
                            }
                          />
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          );
        }}
      </HubResourceBoundary>
      <HubDialog
        isOpen={!!pending}
        onClose={() => setPending(null)}
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
              onClick={() => setPending(null)}
            />
            <Button
              type="submit"
              variant={pending?.next ? "primary" : "danger"}
              size="md"
              stretch="auto"
              loading={busy}
              disabled={!reason.trim()}
              label={t("project_hub.common.confirm")}
            />
          </>
        }
      >
        <HubTextAreaField
          label={t("project_hub.settings.reason")}
          placeholder={t("project_hub.settings.reason_placeholder")}
          hint={t("project_hub.settings.reason_required")}
          value={reason}
          required
          onChange={setReason}
        />
      </HubDialog>
    </HubSection>
  );
});
