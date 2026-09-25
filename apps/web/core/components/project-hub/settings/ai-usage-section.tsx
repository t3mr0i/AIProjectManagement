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
import type { TPHAIUsage, TPHAIUsageRow } from "@plane/types";
import { getProjectHubErrorKind } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubAIStatusBadge, useHubAIStatus } from "../ai/status-badge";
import { useProjectHubCapabilities } from "../common/gate";
import { HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { SettingsCard, SettingsRow, SettingsSection } from "./settings-rows";

const USAGE_DAYS = 30;

function UsageRows({ title, rows, format }: { title: string; rows: TPHAIUsageRow[]; format: (n: number) => string }) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  return (
    <SettingsCard title={title} count={rows.length} aria-label={title}>
      {rows.map((row) => (
        <SettingsRow
          key={row.key || "—"}
          title={row.key || t("project_hub.common.unknown")}
          control={
            <span className="text-caption-md-regular text-tertiary tabular-nums">
              {t("project_hub.ai.usage.row", {
                calls: format(row.calls),
                input: format(row.input_tokens),
                output: format(row.output_tokens),
              })}
            </span>
          }
        />
      ))}
    </SettingsCard>
  );
}

/**
 * Workspace AI usage for admins: calls, tokens and errors of the last 30 days, broken down by
 * feature and model, plus a "rebuild semantic index" action. Hidden for non-admins (403).
 */
export const AIUsageSection = observer(function AIUsageSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t, currentLocale } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug);
  const aiStatus = useHubAIStatus(workspaceSlug);
  // Usage works even while the extension is disabled, so the endpoint (403 for non-admins) is the guard.
  const usage = useHubResource<TPHAIUsage>(PH_KEYS.aiUsage(workspaceSlug, USAGE_DAYS), () =>
    store.aiService.getUsage(workspaceSlug, USAGE_DAYS)
  );
  const [isReindexing, setIsReindexing] = useState(false);

  if (!usage.data) {
    if (usage.error && getProjectHubErrorKind(usage.error) === "permission") return null;
    // Avoid flashing a loading section for members who will get a 403.
    if (!usage.error && !has("workspace.admin")) return null;
  }

  const numberFormat = new Intl.NumberFormat(currentLocale);
  const format = (n: number) => numberFormat.format(n ?? 0);
  const canReindex = !!aiStatus.data?.embeddings;

  const reindex = async () => {
    setIsReindexing(true);
    try {
      await store.aiService.reindex(workspaceSlug);
      showHubSuccessToast(t("project_hub.ai.usage.reindex_queued"));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsReindexing(false);
    }
  };

  return (
    <SettingsSection
      title={t("project_hub.ai.usage.title")}
      description={t("project_hub.ai.usage.description", { days: USAGE_DAYS })}
      actions={<HubAIStatusBadge workspaceSlug={workspaceSlug} />}
    >
      <HubResourceBoundary resource={usage} loadingRows={2}>
        {(data) => (
          <div className="flex min-w-0 flex-col gap-3">
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(
                [
                  ["calls", data.calls],
                  ["input_tokens", data.input_tokens],
                  ["output_tokens", data.output_tokens],
                  ["errors", data.errors],
                ] as const
              ).map(([key, value]) => (
                <div
                  key={key}
                  className="flex min-w-0 flex-col gap-0.5 rounded-md border border-subtle bg-layer-1 px-3 py-2"
                >
                  <dt className="truncate text-caption-md-regular text-tertiary">{t(`project_hub.ai.usage.${key}`)}</dt>
                  <dd
                    className={
                      key === "errors" && value > 0
                        ? "text-body-sm-medium text-warning-primary tabular-nums"
                        : "text-body-sm-medium text-primary tabular-nums"
                    }
                  >
                    {format(value)}
                  </dd>
                </div>
              ))}
            </dl>
            {data.calls === 0 ? (
              <p className="text-caption-md-regular text-tertiary">{t("project_hub.ai.usage.empty")}</p>
            ) : (
              <>
                <UsageRows title={t("project_hub.ai.usage.by_feature")} rows={data.by_feature} format={format} />
                <UsageRows title={t("project_hub.ai.usage.by_model")} rows={data.by_model} format={format} />
              </>
            )}
          </div>
        )}
      </HubResourceBoundary>
      <SettingsCard aria-label={t("project_hub.ai.usage.reindex")}>
        <SettingsRow
          title={t("project_hub.ai.usage.reindex")}
          description={
            canReindex
              ? t("project_hub.ai.usage.reindex_description", { model: aiStatus.data?.embedding_model ?? "" })
              : t("project_hub.ai.usage.reindex_unavailable")
          }
          control={
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              loading={isReindexing}
              disabled={!canReindex}
              label={t("project_hub.ai.usage.reindex_action")}
              onClick={() => void reindex()}
            />
          }
        />
      </SettingsCard>
    </SettingsSection>
  );
});
