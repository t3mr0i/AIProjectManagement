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
import {
  CircleDashedOutline,
  CloseCircleOutline,
  HelpOutline,
  LinkOutline,
  SettingsOutline,
  TickCircleOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type {
  TConnectionHealth,
  TConnectionStatus,
  TIntegrationConnection,
  TIntegrationProvider,
  TProviderDeclaration,
} from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { HubSelect } from "../common/select";
import { HubEmptyState, HubNotice, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { SettingsCard, SettingsConfirmDialog, SettingsSection } from "./settings-rows";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const PROVIDERS: TIntegrationProvider[] = ["gitlab", "github", "jira", "linear", "azure_devops", "generic_git"];

type THealthStatus = TConnectionStatus | "stale";

/** Dot colour per health status; the status text always accompanies it. */
const STATUS_DOT: Record<THealthStatus, string> = {
  active: "text-success-primary",
  degraded: "text-warning-primary",
  stale: "text-warning-primary",
  offline: "text-danger-primary",
  disabled: "text-placeholder",
};

type TSupport = "supported" | "partial" | "unsupported" | "requires_configuration" | "unknown";

const supportOf = (value: unknown): TSupport => {
  if (value === "supported" || value === "partial" || value === "unsupported" || value === "requires_configuration")
    return value;
  return "unknown";
};

/** Icon + text per support level — never colour alone (WCAG 1.4.1). */
const SUPPORT_ICON: Record<TSupport, { icon: TGlyph; className: string }> = {
  supported: { icon: TickCircleOutline as TGlyph, className: "text-success-primary" },
  partial: { icon: CircleDashedOutline as TGlyph, className: "text-warning-primary" },
  requires_configuration: { icon: SettingsOutline as TGlyph, className: "text-accent-primary" },
  unsupported: { icon: CloseCircleOutline as TGlyph, className: "text-placeholder" },
  unknown: { icon: HelpOutline as TGlyph, className: "text-placeholder" },
};

function SupportCell({ support }: { support: TSupport }) {
  const { t } = useTranslation();
  const { icon: Glyph, className } = SUPPORT_ICON[support];
  return (
    <span
      className="inline-flex items-center gap-1 text-caption-md-regular whitespace-nowrap text-secondary"
      title={t(`project_hub.settings.support.${support}`)}
    >
      <Glyph className={cn("size-3.5 shrink-0", className)} aria-hidden="true" />
      <span>{t(`project_hub.settings.support_short.${support}`)}</span>
      <span className="sr-only">{t(`project_hub.settings.support.${support}`)}</span>
    </span>
  );
}

/** Compact provider × capability matrix inside a card. */
function ProviderMatrix({ providers }: { providers: TProviderDeclaration[] }) {
  const { t } = useTranslation();
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
  const capabilityKeys = [...new Set(providers.flatMap((p) => Object.keys(p.capabilities ?? {})))].sort();
  return (
    <SettingsCard aria-label={t("project_hub.settings.providers")}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-max border-collapse text-left">
          <caption className="sr-only">{t("project_hub.settings.providers")}</caption>
          <thead>
            <tr className="h-8 bg-layer-2 text-caption-md-medium text-tertiary">
              <th scope="col" className="pr-3 pl-3 font-medium">
                {t("project_hub.settings.capability_column")}
              </th>
              {providers.map((p) => (
                <th key={p.provider} scope="col" className="pr-3 font-medium whitespace-nowrap">
                  {p.display_name ?? p.provider}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {capabilityKeys.map((cap) => (
              <tr key={cap} className="h-8 border-t border-subtle">
                <th scope="row" className="pr-3 pl-3 text-13 font-medium whitespace-nowrap text-primary">
                  {cap}
                </th>
                {providers.map((p) => (
                  <td key={p.provider} className="pr-3">
                    <SupportCell support={supportOf(p.capabilities?.[cap])} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-subtle px-3 py-1.5">
        {(Object.keys(SUPPORT_ICON) as TSupport[]).map((s) => {
          const { icon: Glyph, className } = SUPPORT_ICON[s];
          return (
            <span key={s} className="inline-flex items-center gap-1 text-caption-sm-regular text-tertiary">
              <Glyph className={cn("size-3", className)} aria-hidden="true" />
              {t(`project_hub.settings.support.${s}`)}
            </span>
          );
        })}
      </div>
    </SettingsCard>
  );
}

const ConnectionRow = observer(function ConnectionRow({
  workspaceSlug,
  connection,
  onDisconnect,
}: {
  workspaceSlug: string;
  connection: TIntegrationConnection;
  onDisconnect: () => void;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatAge } = useHubFormatters();
  const health = useHubResource<TConnectionHealth>(PH_KEYS.health(workspaceSlug, connection.id), () =>
    store.integrationService.getConnectionHealth(workspaceSlug, connection.id)
  );
  const [busy, setBusy] = useState(false);

  const reconcile = async () => {
    setBusy(true);
    try {
      await store.integrationService.reconcile(workspaceSlug, connection.id);
      // 202: accepted, not finished
      showHubSuccessToast(t("project_hub.settings.reconcile_started"));
      store.invalidate(PH_KEYS.health(workspaceSlug, connection.id));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  const ownership = Object.entries(connection.field_ownership ?? {});
  const status: THealthStatus = health.data?.status ?? connection.status;
  const statusLabel = t(`project_hub.settings.connection_status.${status}`);
  const lastSync = health.data?.last_successful_sync_at ?? connection.last_successful_sync_at;
  const backlog = health.data?.backlog_count;
  const problem = health.data && (health.data.last_error || health.data.affected_capabilities.length > 0);

  return (
    <div className="flex min-w-0 flex-col border-b border-subtle last:border-b-0">
      <div className="flex h-9 min-w-0 items-center gap-2 pr-1.5 pl-3 text-13">
        <span className="flex size-4 shrink-0 items-center justify-center" title={statusLabel}>
          <span className={cn("size-2 rounded-full bg-current", STATUS_DOT[status])} aria-hidden="true" />
          <span className="sr-only">{statusLabel}</span>
        </span>
        <span className="min-w-0 truncate font-medium text-primary">
          {connection.display_name || connection.instance_url}
        </span>
        <HubChip variant="soft" icon={LinkOutline as TGlyph} label={connection.provider} />
        <span className="hidden min-w-0 flex-1 truncate text-caption-md-regular text-tertiary sm:inline">
          {connection.instance_url} · {connection.instance_type}
          {connection.edition ? ` ${connection.edition}` : ""}
        </span>
        <span className="flex-1 sm:hidden" />
        <span className="shrink-0 text-caption-md-regular whitespace-nowrap text-tertiary">
          {health.isLoading && !health.data
            ? t("project_hub.states.loading")
            : `${statusLabel} · ${t("project_hub.settings.last_sync", { time: formatAge(lastSync) })}${
                backlog !== undefined ? ` · ${t("project_hub.settings.backlog", { count: backlog })}` : ""
              }`}
        </span>
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          loading={busy}
          label={t("project_hub.settings.reconcile")}
          onClick={() => void reconcile()}
        />
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          label={t("project_hub.settings.disconnect")}
          onClick={onDisconnect}
        />
      </div>
      {health.error && !health.data && (
        <div className="px-3 pb-2">
          <HubNotice
            tone="warning"
            icon={WarningTriangleOutline as TGlyph}
            title={t("project_hub.settings.health_unavailable")}
            action={
              <Button
                variant="ghost"
                size="sm"
                stretch="auto"
                label={t("project_hub.common.retry")}
                onClick={() => void health.refresh()}
              />
            }
          />
        </div>
      )}
      {problem && health.data && (
        <div className="px-3 pb-2">
          <HubNotice
            tone="warning"
            icon={WarningTriangleOutline as TGlyph}
            title={
              health.data.last_error
                ? t("project_hub.settings.last_error", { error: health.data.last_error })
                : t("project_hub.settings.affected_capabilities", {
                    list: health.data.affected_capabilities.join(", "),
                  })
            }
            description={
              health.data.last_error && health.data.affected_capabilities.length > 0
                ? t("project_hub.settings.affected_capabilities", {
                    list: health.data.affected_capabilities.join(", "),
                  })
                : undefined
            }
          />
        </div>
      )}
      {ownership.length > 0 && (
        <details className="group/ownership px-3 pb-2">
          <summary className="-ml-1 inline-flex h-6 cursor-pointer list-none items-center gap-1 rounded-sm px-1 text-caption-md-regular text-tertiary transition-colors duration-100 hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none">
            {t("project_hub.settings.field_ownership")}
            <span className="text-placeholder">{ownership.length}</span>
          </summary>
          <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 pl-1 text-caption-md-regular">
            {ownership.map(([field, owner]) => (
              <div key={field} className="contents">
                <dt className="text-secondary">{field}</dt>
                <dd className="text-tertiary">
                  {owner === "external"
                    ? t("project_hub.settings.owner_external")
                    : owner === "platform"
                      ? t("project_hub.settings.owner_platform")
                      : owner}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
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
  const [busy, setBusy] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<TIntegrationConnection | null>(null);
  const [form, setForm] = useState({
    provider: "gitlab" as TIntegrationProvider,
    instance_url: "",
    instance_type: "cloud",
    edition: "",
    display_name: "",
    webhook_secret: "",
  });

  const create = async () => {
    setBusy("create");
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
      setBusy(null);
    }
  };

  const disconnect = async () => {
    if (!disconnecting) return;
    setBusy(disconnecting.id);
    try {
      await store.integrationService.disconnect(workspaceSlug, disconnecting.id);
      store.invalidate(PH_KEYS.connections(workspaceSlug));
      setDisconnecting(null);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const addAction = (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      label={t("project_hub.settings.connection_add")}
      onClick={() => setIsOpen(true)}
    />
  );

  return (
    <SettingsSection
      title={t("project_hub.settings.integrations")}
      description={t("project_hub.settings.integrations_description")}
      actions={addAction}
    >
      <div className="flex flex-col gap-6 pt-1">
        <SettingsSection
          as="h3"
          title={t("project_hub.settings.connections")}
          description={t("project_hub.settings.disconnect_description")}
        >
          <HubResourceBoundary
            resource={connections}
            loadingRows={2}
            isEmpty={(d) => d.length === 0}
            empty={
              <HubEmptyState
                size="sm"
                icon={LinkOutline as TGlyph}
                title={t("project_hub.settings.connections_empty")}
                description={t("project_hub.settings.connections_empty_description")}
                action={
                  <Button
                    variant="tertiary"
                    size="sm"
                    stretch="auto"
                    label={t("project_hub.settings.connection_add")}
                    onClick={() => setIsOpen(true)}
                  />
                }
              />
            }
          >
            {(data) => (
              <SettingsCard aria-label={t("project_hub.settings.connections")}>
                {data.map((connection) => (
                  <ConnectionRow
                    key={connection.id}
                    workspaceSlug={workspaceSlug}
                    connection={connection}
                    onDisconnect={() => setDisconnecting(connection)}
                  />
                ))}
              </SettingsCard>
            )}
          </HubResourceBoundary>
        </SettingsSection>

        <SettingsSection
          as="h3"
          title={t("project_hub.settings.providers")}
          description={t("project_hub.settings.providers_description")}
        >
          <HubResourceBoundary resource={providers} loadingRows={2} isEmpty={(d) => d.length === 0}>
            {(data) => <ProviderMatrix providers={data} />}
          </HubResourceBoundary>
        </SettingsSection>
      </div>

      <HubDialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        isBusy={busy === "create"}
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
              loading={busy === "create"}
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

      <SettingsConfirmDialog
        isOpen={!!disconnecting}
        busy={!!disconnecting && busy === disconnecting.id}
        title={t("project_hub.settings.disconnect_confirm_title")}
        description={
          disconnecting &&
          t("project_hub.settings.disconnect_confirm_description", {
            name: disconnecting.display_name || disconnecting.instance_url,
          })
        }
        confirmLabel={t("project_hub.settings.disconnect")}
        onConfirm={() => void disconnect()}
        onClose={() => setDisconnecting(null)}
      />
    </SettingsSection>
  );
});
