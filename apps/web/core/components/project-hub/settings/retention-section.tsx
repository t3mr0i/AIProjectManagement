/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import type { TPHRetentionPolicy } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextField } from "../common/field";
import { HubSection } from "../common/section";
import { HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";

const CATEGORIES = ["messages", "audit", "run_logs", "raw_events", "ai_outputs", "exports"];

/** Separate retention per category (PRD §15.3). Empty = keep forever. */
export const RetentionSection = observer(function RetentionSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const retention = useHubResource<TPHRetentionPolicy[]>(PH_KEYS.retention(workspaceSlug), async () => {
    const payload = await store.knowledgeService.getRetention(workspaceSlug);
    return Array.isArray(payload) ? payload : (payload.policies ?? []);
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const data = retention.data;
  useEffect(() => {
    if (!data) return;
    setDraft(
      Object.fromEntries(CATEGORIES.map((c) => [c, String(data.find((p) => p.category === c)?.retain_days ?? "")]))
    );
  }, [data]);

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
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <HubSection title={t("project_hub.settings.retention")} as="h2">
      <HubResourceBoundary resource={retention} loadingRows={2}>
        {() => (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {CATEGORIES.map((category) => (
                <HubTextField
                  key={category}
                  type="number"
                  label={`${t(`project_hub.settings.retention_categories.${category}`)} (${t("project_hub.settings.retention_days")})`}
                  placeholder={t("project_hub.settings.retention_keep")}
                  hint={!draft[category] ? t("project_hub.settings.retention_keep") : undefined}
                  value={draft[category] ?? ""}
                  onChange={(v) => setDraft((d) => ({ ...d, [category]: v }))}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                variant="primary"
                size="sm"
                stretch="auto"
                loading={busy === "save"}
                label={t("project_hub.common.save")}
              />
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                loading={busy === "apply"}
                label={t("project_hub.settings.retention_apply")}
                onClick={() => void apply()}
              />
            </div>
          </form>
        )}
      </HubResourceBoundary>
    </HubSection>
  );
});
