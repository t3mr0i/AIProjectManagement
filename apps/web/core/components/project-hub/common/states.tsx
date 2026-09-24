/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import { Banner } from "@makeplane/propel/components/banner";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import {
  AlertCircleOutline,
  CloudOffOutline,
  InfoOutline,
  LockOutline,
  SearchOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { Loader } from "@plane/blocks/skeleton";
import { useTranslation } from "@plane/i18n";
import type { TProjectHubApiError } from "@plane/types";
import { cn, getProjectHubErrorKind, getProjectHubErrorMessageKey } from "@plane/utils";
// local imports
import type { THubResource } from "./use-hub-resource";
import { useOnlineStatus } from "./use-online-status";
import { useHubFormatters } from "./use-relative-time";

/** Loading skeleton with an accessible busy label. */
export function HubLoading({ rows = 3, className }: { rows?: number; className?: string }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={cn("w-full", className)}>
      <span className="sr-only">{t("project_hub.states.loading")}</span>
      <Loader className="flex flex-col gap-2">
        {Array.from({ length: rows }, (_, i) => (
          <Loader.Item key={i} height="36px" width="100%" />
        ))}
      </Loader>
    </div>
  );
}

/** Compact empty state (no illustration — dense work tool). */
export function HubEmpty({ title, description, action }: { title?: string; description?: string; action?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-subtle px-4 py-5">
      <p className="text-body-sm-medium text-secondary">{title ?? t("project_hub.states.empty_title")}</p>
      {description && <p className="text-body-xs-regular text-tertiary">{description}</p>}
      {action}
    </div>
  );
}

type TErrorProps = {
  error: TProjectHubApiError | null;
  onRetry?: () => void;
  className?: string;
};

/**
 * Full error state for a section. Distinguishes permission-denied, extension-disabled, not-found,
 * offline and generic failures — each with a concrete next step (DESIGN_BRIEF S05).
 */
export function HubErrorState({ error, onRetry, className }: TErrorProps) {
  const { t } = useTranslation();
  const kind = getProjectHubErrorKind(error);
  const config = (() => {
    switch (kind) {
      case "permission":
        return {
          icon: LockOutline,
          title: t("project_hub.states.permission_title"),
          description: t("project_hub.states.permission_description"),
          retry: false,
        };
      case "disabled":
        return {
          icon: LockOutline,
          title: t("project_hub.states.disabled_title"),
          description: t("project_hub.states.disabled_description"),
          retry: false,
        };
      case "not_found":
        return {
          icon: SearchOutline,
          title: t("project_hub.states.not_found_title"),
          description: t("project_hub.states.not_found_description"),
          retry: false,
        };
      case "offline":
        return {
          icon: CloudOffOutline,
          title: t("project_hub.states.offline_title"),
          description: t("project_hub.errors.kind.offline"),
          retry: true,
        };
      default:
        return {
          icon: AlertCircleOutline,
          title: t("project_hub.states.error_title"),
          description: t(getProjectHubErrorMessageKey(error)),
          retry: true,
        };
    }
  })();

  return (
    <div
      role="alert"
      className={cn("flex items-start gap-3 rounded-md border border-subtle bg-layer-1 px-4 py-4", className)}
    >
      <Icon icon={config.icon} size="md" tint="secondary" />
      <div className="flex flex-col gap-1">
        <p className="text-body-sm-medium text-primary">{config.title}</p>
        <p className="text-body-xs-regular text-secondary">{config.description}</p>
        {error?.error && kind !== "permission" && (
          <p className="text-caption-sm-regular text-tertiary">{error.error}</p>
        )}
        {config.retry && onRetry && (
          <div className="pt-1">
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label={t("project_hub.common.retry")}
              onClick={onRetry}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/** Conflict (409) banner: never silently overwrite; offer reloading the latest server state. */
export function HubConflictBanner({ onReload, onDismiss }: { onReload: () => void; onDismiss?: () => void }) {
  const { t } = useTranslation();
  return (
    <Banner
      placement="inline"
      variant="warning"
      role="alert"
      icon={<Icon icon={WarningTriangleOutline} />}
      title={t("project_hub.states.conflict_title")}
      description={t("project_hub.states.conflict_description")}
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("project_hub.states.reload_latest")}
          onClick={onReload}
        />
      }
      onDismiss={onDismiss}
      dismissLabel={t("project_hub.common.close")}
    />
  );
}

/** Partial state: some sections failed but others are shown. */
export function HubPartialBanner({ sections }: { sections: string[] }) {
  const { t } = useTranslation();
  if (sections.length === 0) return null;
  return (
    <Banner
      placement="inline"
      variant="neutral"
      role="status"
      icon={<Icon icon={InfoOutline} />}
      title={t("project_hub.states.partial_title")}
      description={t("project_hub.states.partial_description", { sections: sections.join(", ") })}
    />
  );
}

/**
 * Offline / stale banner. Shown when the browser is offline or when a refresh failed while older
 * data is still displayed — the view is then never presented as live.
 */
export const HubFreshnessBanner = observer(function HubFreshnessBanner({
  resource,
}: {
  resource: Pick<THubResource<unknown>, "data" | "error" | "fetchedAt" | "refresh">;
}) {
  const { t } = useTranslation();
  const online = useOnlineStatus();
  const { formatDateTime } = useHubFormatters();
  const hasData = resource.data !== undefined;
  if (!online) {
    return (
      <Banner
        placement="inline"
        variant="warning"
        role="status"
        icon={<Icon icon={CloudOffOutline} />}
        title={t("project_hub.states.offline_title")}
        description={t("project_hub.states.offline_description")}
      />
    );
  }
  if (hasData && resource.error && getProjectHubErrorKind(resource.error) !== "conflict") {
    return (
      <Banner
        placement="inline"
        variant="warning"
        role="status"
        icon={<Icon icon={WarningTriangleOutline} />}
        title={t("project_hub.states.stale_title")}
        description={t("project_hub.states.stale_description", { time: formatDateTime(resource.fetchedAt) })}
        actions={
          <Button
            stretch="auto"
            variant="secondary"
            size="sm"
            label={t("project_hub.common.retry")}
            onClick={() => void resource.refresh()}
          />
        }
      />
    );
  }
  return null;
});

type TBoundaryProps<T> = {
  resource: THubResource<T>;
  children: (data: T) => ReactNode;
  loadingRows?: number;
  /** Treat as empty (render `empty` instead of children). */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
};

/**
 * Renders the designed states for one resource: Loading → Error (incl. permission/disabled/offline)
 * → Empty → content, plus Stale/Offline banner above content when a refresh failed.
 */
export const HubResourceBoundary = observer(function HubResourceBoundary<T>({
  resource,
  children,
  loadingRows,
  isEmpty,
  empty,
}: TBoundaryProps<T>) {
  if (resource.data === undefined) {
    if (resource.error) return <HubErrorState error={resource.error} onRetry={() => void resource.refresh()} />;
    return <HubLoading rows={loadingRows} />;
  }
  const data = resource.data;
  return (
    <div className="flex flex-col gap-3">
      <HubFreshnessBanner resource={resource} />
      {isEmpty?.(data) ? (empty ?? <HubEmpty />) : children(data)}
    </div>
  );
}) as <T>(props: TBoundaryProps<T>) => ReactNode;
