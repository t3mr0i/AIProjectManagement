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
import type {
  TConnectionHealth,
  TConnectionStatus,
  TIntegrationConnection,
  TIntegrationProvider,
  TProviderDeclaration,
} from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { HubCard, HubSection } from "../common/section";
import { HubSelect } from "../common/select";
import { HubEmpty, HubErrorState, HubLoading, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

const PROVIDERS: TIntegrationProvider[] = ["gitlab", "github", "jira", "linear", "azure_devops", "generic_git"];

const STATUS_TONE: Record<TConnectionStatus, TProjectHubTone> = {
  active: "success",
  degraded: "warning",
  offline: "danger",
  disabled: "neutral",
};

const supportOf = (value: unknown): "supported" | "partial" | "unsupported" | "unknown" => {
  if (value === true || value === "supported") return "supported";
  if (value === "partial") return "partial";
  if (value === false || value === "unsupported") return "unsupported";
  return "unknown";
};

const SUPPORT_TONE: Record<string, TProjectHubTone> = {
  supported: "success",
  partial: "warning",
  unsupported: "neutral",
  unknown: "neutral",
};

const ConnectionCard = observer(function ConnectionCard({
  workspaceSlug,
  connection,
}: {
  workspaceSlug: string;
  connection: TIntegrationConnection;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatAge } = useHubFormatters();
  const health = useHubResource<TConnectionHealth>(PH_KEYS.health(workspaceSlug, connection.id), () =>
    store.integrationService.getConnectionHealth(workspaceSlug, connection.id)
  );
  const [busy, setBusy] = useState<string | null>(null);

  const reconcile = async () => {
    setBusy("reconcile");
    try {
      await store.integrationService.reconcile(workspaceSlug, connection.id);
      // 202: accepted, not finished
      showHubSuccessToast(t("project_hub.settings.reconcile_started"));
      store.invalidate(PH_KEYS.health(workspaceSlug, connection.id));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    try {
      await store.integrationService.disconnect(workspaceSlug, connection.id);
      store.invalidate(PH_KEYS.connections(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const ownership = Object.entries(connection.field_ownership ?? {});
  const status = health.data?.status ?? connection.status;

  return (
    <HubCard className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-body-xs-medium text-primary">{connection.display_name || connection.instance_url}</span>
          <ToneBadge tone="neutral" size="xs" label={connection.provider} />
          <ToneBadge
            tone={STATUS_TONE[status] ?? "neutral"}
            size="xs"
            label={t(`project_hub.settings.connection_status.${status}`)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            loading={busy === "reconcile"}
            label={t("project_hub.settings.reconcile")}
            onClick={() => void reconcile()}
          />
          <Button
            variant="danger-outline"
            size="sm"
            stretch="auto"
            loading={busy === "disconnect"}
            label={t("project_hub.settings.disconnect")}
            onClick={() => void disconnect()}
          />
        </div>
      </div>
      <p className="text-caption-sm-regular text-tertiary">
        {connection.instance_url} · {connection.instance_type} {connection.edition}
      </p>
      {health.isLoading ? (
        <HubLoading rows={1} />
      ) : health.error && !health.data ? (
        <HubErrorState error={health.error} onRetry={() => void health.refresh()} />
      ) : health.data ? (
        <ul
          className="flex flex-col gap-0.5 text-caption-sm-regular text-secondary"
          aria-label={t("project_hub.settings.health")}
        >
          <li>{t("project_hub.settings.last_sync", { time: formatAge(health.data.last_successful_sync_at) })}</li>
          <li>{t("project_hub.settings.backlog", { count: health.data.backlog_count })}</li>
          {health.data.affected_capabilities.length > 0 && (
            <li>
              {t("project_hub.settings.affected_capabilities", { list: health.data.affected_capabilities.join(", ") })}
            </li>
          )}
          {health.data.last_error && <li>{t("project_hub.settings.last_error", { error: health.data.last_error })}</li>}
        </ul>
      ) : null}
      {ownership.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-caption-md-medium text-tertiary">{t("project_hub.settings.field_ownership")}</p>
          <table className="w-full max-w-md text-left text-caption-sm-regular">
            <tbody>
              {ownership.map(([field, owner]) => (
                <tr key={field} className="border-b border-subtle">
                  <th scope="row" className="py-1 pr-3 font-medium text-primary">
                    {field}
                  </th>
                  <td className="py-1 text-secondary">
                    {owner === "external"
                      ? t("project_hub.settings.owner_external")
                      : owner === "platform"
                        ? t("project_hub.settings.owner_platform")
                        : owner}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </HubCard>
  );
});

/** Integrations (S12): provider capability matrix, connections with health and field ownership. */
export const IntegrationsSection = observer(function IntegrationsSection({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const providers = useHubResource<TProviderDeclaration[]>(PH_KEYS.providers(workspaceSlug), () =>
    store.integrationService.listProviders(workspaceSlug)
  );
  const connections = useHubResource<TIntegrationConnection[]>(PH_KEYS.connections(workspaceSlug), () =>
    store.integrationService.listConnections(workspaceSlug)
  );
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    provider: "gitlab" as TIntegrationProvider,
    instance_url: "",
    instance_type: "cloud",
    edition: "",
    display_name: "",
    webhook_secret: "",
  });

  const create = async () => {
    setBusy(true);
    try {
      await store.integrationService.createConnection(workspaceSlug, {
        ...form,
        ...(form.webhook_secret ? {} : { webhook_secret: undefined }),
      });
      setIsOpen(false);
      store.invalidate(PH_KEYS.connections(workspaceSlug));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <HubSection
      title={t("project_hub.settings.integrations")}
      as="h2"
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("project_hub.settings.connection_add")}
          onClick={() => setIsOpen(true)}
        />
      }
    >
      <HubSection title={t("project_hub.settings.providers")}>
        <HubResourceBoundary resource={providers} loadingRows={2} isEmpty={(d) => d.length === 0}>
          {(data) => {
            // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
            const capabilityKeys = [...new Set(data.flatMap((p) => Object.keys(p.capabilities ?? {})))].sort();
            return (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-caption-sm-regular">
                  <caption className="sr-only">{t("project_hub.settings.providers")}</caption>
                  <thead>
                    <tr className="border-b border-subtle text-tertiary">
                      <th scope="col" className="py-1.5 pr-3 font-medium">
                        {t("project_hub.settings.provider")}
                      </th>
                      {data.map((p) => (
                        <th key={p.provider} scope="col" className="py-1.5 pr-3 font-medium">
                          {p.display_name ?? p.provider}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {capabilityKeys.map((cap) => (
                      <tr key={cap} className="border-b border-subtle">
                        <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                          {cap}
                        </th>
                        {data.map((p) => {
                          const support = supportOf(p.capabilities?.[cap]);
                          return (
                            <td key={p.provider} className="py-1.5 pr-3">
                              <ToneBadge
                                tone={SUPPORT_TONE[support]}
                                size="xs"
                                label={t(`project_hub.settings.support.${support}`)}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }}
        </HubResourceBoundary>
      </HubSection>
      <HubSection title={t("project_hub.settings.connections")}>
        <HubResourceBoundary
          resource={connections}
          loadingRows={2}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.settings.connections_empty")} />}
        >
          {(data) => (
            <ul className="flex flex-col gap-2">
              {data.map((connection) => (
                <li key={connection.id}>
                  <ConnectionCard workspaceSlug={workspaceSlug} connection={connection} />
                </li>
              ))}
            </ul>
          )}
        </HubResourceBoundary>
        <p className="text-caption-sm-regular text-tertiary">{t("project_hub.settings.disconnect_description")}</p>
      </HubSection>
      <HubDialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        isBusy={busy}
        title={t("project_hub.settings.connection_add")}
        onSubmit={() => void create()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setIsOpen(false)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy}
              disabled={!form.instance_url.trim()}
              label={t("project_hub.common.create")}
            />
          </>
        }
      >
        <HubSelect
          label={t("project_hub.settings.provider")}
          value={form.provider}
          onChange={(v) => setForm((f) => ({ ...f, provider: v as TIntegrationProvider }))}
          options={PROVIDERS.map((p) => ({ value: p, label: p }))}
        />
        <HubTextField
          type="url"
          label={t("project_hub.settings.instance_url")}
          value={form.instance_url}
          required
          onChange={(v) => setForm((f) => ({ ...f, instance_url: v }))}
        />
        <HubSelect
          label={t("project_hub.settings.instance_type")}
          value={form.instance_type}
          onChange={(v) => setForm((f) => ({ ...f, instance_type: v }))}
          options={["cloud", "self_managed", "server"].map((v) => ({ value: v, label: v }))}
        />
        <HubTextField
          label={t("project_hub.settings.edition")}
          value={form.edition}
          onChange={(v) => setForm((f) => ({ ...f, edition: v }))}
        />
        <HubTextField
          label={t("project_hub.settings.display_name")}
          value={form.display_name}
          onChange={(v) => setForm((f) => ({ ...f, display_name: v }))}
        />
        <HubTextField
          type="password"
          label={t("project_hub.settings.webhook_secret")}
          value={form.webhook_secret}
          onChange={(v) => setForm((f) => ({ ...f, webhook_secret: v }))}
        />
      </HubDialog>
    </HubSection>
  );
});
