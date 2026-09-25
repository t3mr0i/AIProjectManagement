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
import { KeyOutline, ServerOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TRunnerKind, TRunnerProfile, TRunnerRegistration } from "@plane/types";
import { cn, getAgeSeconds } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubCodeBlock } from "../common/copy-button";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { HubListRow } from "../common/list";
import { HubMemberName } from "../common/member-name";
import { HubSelect } from "../common/select";
import { HubEmptyState, HubNotice, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { SettingsCard, SettingsConfirmDialog, SettingsSection } from "./settings-rows";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const ONLINE_WINDOW_SECONDS = 5 * 60;

type TRunnerStatus = "online" | "idle" | "inactive";

const runnerStatus = (runner: TRunnerProfile): TRunnerStatus => {
  if (!runner.is_active) return "inactive";
  const age = getAgeSeconds(runner.last_seen_at);
  return age !== null && age <= ONLINE_WINDOW_SECONDS ? "online" : "idle";
};

const STATUS_DOT: Record<TRunnerStatus, string> = {
  online: "text-success-primary",
  idle: "text-placeholder",
  inactive: "text-danger-primary",
};

/** 8px status dot with a screen-reader label (colour is backed by the text in the meta). */
function StatusDot({ status, label }: { status: TRunnerStatus; label: string }) {
  return (
    <span className="flex size-4 items-center justify-center" title={label}>
      <span className={cn("size-2 rounded-full bg-current", STATUS_DOT[status])} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/** Runner registration; the token is shown exactly once and never stored in the UI state afterwards. */
export const RunnersSection = observer(function RunnersSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatAge } = useHubFormatters();
  const runners = useHubResource<TRunnerProfile[]>(PH_KEYS.runners(workspaceSlug), () =>
    store.executionService.listRunners(workspaceSlug)
  );
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TRunnerKind>("local");
  const [registration, setRegistration] = useState<TRunnerRegistration | null>(null);
  const [deactivating, setDeactivating] = useState<TRunnerProfile | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const register = async () => {
    if (!name.trim()) return;
    setBusy("register");
    try {
      const result = await store.executionService.registerRunner(workspaceSlug, { name: name.trim(), kind });
      setRegistration(result);
      store.invalidate(PH_KEYS.runners(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const close = () => {
    // Drop the token from memory when the dialog closes.
    setRegistration(null);
    setName("");
    setKind("local");
    setIsOpen(false);
  };

  const deactivate = async () => {
    if (!deactivating) return;
    setBusy(deactivating.id);
    try {
      await store.executionService.deactivateRunner(workspaceSlug, deactivating.id);
      store.invalidate(PH_KEYS.runners(workspaceSlug));
      setDeactivating(null);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const registerAction = (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      label={t("project_hub.settings.runner_register")}
      onClick={() => setIsOpen(true)}
    />
  );

  return (
    <SettingsSection
      title={t("project_hub.settings.runners")}
      description={t("project_hub.settings.runners_description")}
      actions={registerAction}
    >
      <HubResourceBoundary
        resource={runners}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={
          <HubEmptyState
            size="sm"
            icon={ServerOutline as TGlyph}
            title={t("project_hub.settings.runners_empty")}
            description={t("project_hub.settings.runners_empty_description")}
            action={
              <Button
                variant="tertiary"
                size="sm"
                stretch="auto"
                label={t("project_hub.settings.runner_register")}
                onClick={() => setIsOpen(true)}
              />
            }
          />
        }
      >
        {(data) => (
          <SettingsCard aria-label={t("project_hub.settings.runners")}>
            {data.map((runner) => {
              const status = runnerStatus(runner);
              const statusLabel = t(`project_hub.settings.runner_status.${status}`);
              return (
                <HubListRow
                  key={runner.id}
                  leading={<StatusDot status={status} label={statusLabel} />}
                  title={runner.name}
                  disabled={!runner.is_active}
                  meta={
                    <>
                      <HubChip
                        variant="soft"
                        icon={ServerOutline as TGlyph}
                        label={t(`project_hub.settings.runner_kinds.${runner.kind}`)}
                      />
                      {runner.token_prefix && (
                        <code className="font-mono text-caption-md-regular text-tertiary">{runner.token_prefix}…</code>
                      )}
                      <span className="text-caption-md-regular text-tertiary">
                        <HubMemberName userId={runner.owner_id} />
                      </span>
                      <span className="text-caption-md-regular text-tertiary">
                        {runner.is_active
                          ? t("project_hub.settings.last_seen", { time: formatAge(runner.last_seen_at) })
                          : statusLabel}
                      </span>
                    </>
                  }
                  trailing={
                    runner.is_active ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        stretch="auto"
                        label={t("project_hub.settings.runner_deactivate")}
                        onClick={() => setDeactivating(runner)}
                      />
                    ) : undefined
                  }
                />
              );
            })}
          </SettingsCard>
        )}
      </HubResourceBoundary>

      <HubDialog
        isOpen={isOpen}
        onClose={close}
        isBusy={busy === "register"}
        title={registration ? t("project_hub.settings.runner_token_title") : t("project_hub.settings.runner_register")}
        onSubmit={() => void (registration ? close() : register())}
        actions={
          registration ? (
            <Button type="submit" variant="primary" size="md" stretch="auto" label={t("project_hub.common.close")} />
          ) : (
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
                variant="primary"
                size="md"
                stretch="auto"
                loading={busy === "register"}
                disabled={!name.trim()}
                label={t("project_hub.settings.runner_register")}
              />
            </>
          )
        }
      >
        {registration ? (
          <>
            <HubNotice
              role="alert"
              tone="warning"
              icon={WarningTriangleOutline as TGlyph}
              title={t("project_hub.settings.runner_token_once")}
              description={t("project_hub.settings.runner_token_description")}
            />
            <div className="flex flex-col gap-1">
              <span className="flex items-center gap-1.5 text-caption-md-medium text-tertiary">
                <KeyOutline className="size-3.5" aria-hidden="true" />
                {registration.name ?? name}
              </span>
              <HubCodeBlock value={registration.token} />
            </div>
          </>
        ) : (
          <>
            <HubTextField label={t("project_hub.settings.runner_name")} value={name} required onChange={setName} />
            <HubSelect
              label={t("project_hub.settings.runner_kind")}
              value={kind}
              onChange={(v) => setKind(v as TRunnerKind)}
              options={(["local", "customer", "managed"] as TRunnerKind[]).map((k) => ({
                value: k,
                label: t(`project_hub.settings.runner_kinds.${k}`),
              }))}
            />
            <p className="text-caption-sm-regular text-tertiary">{t("project_hub.settings.runner_register_hint")}</p>
          </>
        )}
      </HubDialog>

      <SettingsConfirmDialog
        isOpen={!!deactivating}
        busy={!!deactivating && busy === deactivating.id}
        title={t("project_hub.settings.runner_deactivate_confirm_title")}
        description={
          deactivating && t("project_hub.settings.runner_deactivate_confirm_description", { name: deactivating.name })
        }
        confirmLabel={t("project_hub.settings.runner_deactivate")}
        onConfirm={() => void deactivate()}
        onClose={() => setDeactivating(null)}
      />
    </SettingsSection>
  );
});
