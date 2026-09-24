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
import type { TRunnerKind, TRunnerProfile, TRunnerRegistration } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubCodeBlock } from "../common/copy-button";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { HubSection } from "../common/section";
import { HubSelect } from "../common/select";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

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
    setIsOpen(false);
  };

  const deactivate = async (runner: TRunnerProfile) => {
    setBusy(runner.id);
    try {
      await store.executionService.deactivateRunner(workspaceSlug, runner.id);
      store.invalidate(PH_KEYS.runners(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <HubSection
      title={t("project_hub.settings.runners")}
      as="h2"
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("project_hub.settings.runner_register")}
          onClick={() => setIsOpen(true)}
        />
      }
    >
      <HubResourceBoundary
        resource={runners}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.settings.runners_empty")} />}
      >
        {(data) => (
          <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
            {data.map((runner) => (
              <li key={runner.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-body-xs-medium text-primary">{runner.name}</span>
                  <ToneBadge tone="neutral" size="xs" label={t(`project_hub.settings.runner_kinds.${runner.kind}`)} />
                  {!runner.is_active && (
                    <ToneBadge tone="danger" size="xs" label={t("project_hub.settings.runner_inactive")} />
                  )}
                  {runner.token_prefix && (
                    <code className="font-mono text-caption-sm-regular text-tertiary">{runner.token_prefix}…</code>
                  )}
                  <span className="text-caption-sm-regular text-tertiary">
                    {t("project_hub.settings.last_seen", { time: formatAge(runner.last_seen_at) })}
                  </span>
                </div>
                {runner.is_active && (
                  <Button
                    variant="danger-outline"
                    size="sm"
                    stretch="auto"
                    loading={busy === runner.id}
                    label={t("project_hub.settings.runner_deactivate")}
                    onClick={() => void deactivate(runner)}
                  />
                )}
              </li>
            ))}
          </ul>
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
            <p role="alert" className="text-body-xs-medium text-primary">
              {t("project_hub.settings.runner_token_description")}
            </p>
            <HubCodeBlock value={registration.token} />
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
          </>
        )}
      </HubDialog>
    </HubSection>
  );
});
