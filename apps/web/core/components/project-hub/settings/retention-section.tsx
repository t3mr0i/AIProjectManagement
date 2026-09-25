/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import type { TPHRetentionPolicy } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { SettingsCard, SettingsConfirmDialog, SettingsRow, SettingsSection } from "./settings-rows";

const CATEGORIES = ["messages", "audit", "run_logs", "raw_events", "ai_outputs", "exports"];

const toDraft = (data: TPHRetentionPolicy[]) =>
  Object.fromEntries(CATEGORIES.map((c) => [c, String(data.find((p) => p.category === c)?.retain_days ?? "")]));

/** Number input + unit; empty means "keep forever" (shown as the placeholder). */
function RetentionInput({
  category,
  value,
  onChange,
}: {
  category: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="flex items-center gap-1.5">
      <label htmlFor={id} className="sr-only">
        {t(`project_hub.settings.retention_categories.${category}`)}
      </label>
      <div className="w-24">
        <InputGroup size="md">
          <Input
            id={id}
            size="md"
            type="number"
            min={1}
            inputMode="numeric"
            placeholder="∞"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        </InputGroup>
      </div>
      <span className="w-9 text-caption-md-regular text-tertiary">{t("project_hub.settings.retention_days")}</span>
    </div>
  );
}

/** Separate retention per category (PRD §15.3). Empty = keep forever. */
export const RetentionSection = observer(function RetentionSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const retention = useHubResource<TPHRetentionPolicy[]>(PH_KEYS.retention(workspaceSlug), () =>
    store.knowledgeService.getRetention(workspaceSlug)
  );
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);

  const data = retention.data;
  useEffect(() => {
    if (!data) return;
    setDraft(toDraft(data));
  }, [data]);

  const dirty = data ? CATEGORIES.some((c) => (draft[c] ?? "") !== toDraft(data)[c]) : false;

  const save = async () => {
    setBusy("save");
    try {
      await store.knowledgeService.updateRetention(
        workspaceSlug,
        CATEGORIES.map((category) => ({
          category,
          retain_days: draft[category] && Number(draft[category]) > 0 ? Number(draft[category]) : null,
        }))
      );
      showHubSuccessToast(t("project_hub.settings.retention_saved"));
      store.invalidate(PH_KEYS.retention(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    setBusy("apply");
    try {
      await store.knowledgeService.applyRetention(workspaceSlug);
      showHubSuccessToast(t("project_hub.settings.retention_applied"));
      setConfirmApply(false);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <SettingsSection
      title={t("project_hub.settings.retention")}
      description={t("project_hub.settings.retention_description")}
    >
      <HubResourceBoundary resource={retention} loadingRows={2}>
        {() => (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <SettingsCard aria-label={t("project_hub.settings.retention")}>
              {CATEGORIES.map((category) => {
                const value = draft[category] ?? "";
                return (
                  <SettingsRow
                    key={category}
                    title={t(`project_hub.settings.retention_categories.${category}`)}
                    description={
                      value && Number(value) > 0
                        ? t("project_hub.settings.retention_after_days", { count: Number(value) })
                        : t("project_hub.settings.retention_keep")
                    }
                    control={
                      <RetentionInput
                        category={category}
                        value={value}
                        onChange={(v) => setDraft((d) => ({ ...d, [category]: v }))}
                      />
                    }
                  />
                );
              })}
              <div className="flex h-10 items-center justify-between gap-2 border-t border-subtle bg-layer-2 pr-1.5 pl-3">
                <span className="truncate text-caption-md-regular text-tertiary">
                  {dirty ? t("project_hub.settings.unsaved_changes") : t("project_hub.settings.retention_apply_hint")}
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    stretch="auto"
                    disabled={busy === "save"}
                    label={t("project_hub.settings.retention_apply")}
                    onClick={() => setConfirmApply(true)}
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    stretch="auto"
                    loading={busy === "save"}
                    disabled={!dirty}
                    label={t("project_hub.common.save")}
                  />
                </div>
              </div>
            </SettingsCard>
          </form>
        )}
      </HubResourceBoundary>

      <SettingsConfirmDialog
        isOpen={confirmApply}
        busy={busy === "apply"}
        title={t("project_hub.settings.retention_apply_confirm_title")}
        description={t("project_hub.settings.retention_apply_confirm_description")}
        confirmLabel={t("project_hub.settings.retention_apply")}
        onConfirm={() => void apply()}
        onClose={() => setConfirmApply(false)}
      />
    </SettingsSection>
  );
});
