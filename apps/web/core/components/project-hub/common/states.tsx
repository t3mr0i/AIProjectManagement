/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  AlertCircleOutline,
  CloudOffOutline,
  InboxOutline,
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

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/** Loading skeleton: 36px row ghosts with an accessible busy label. */
export function HubLoading({ rows = 3, className }: { rows?: number; className?: string }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={cn("w-full", className)}>
      <span className="sr-only">{t("project_hub.states.loading")}</span>
      <Loader className="flex flex-col gap-1">
        {Array.from({ length: rows }, (_, i) => (
          <Loader.Item key={i} height="36px" width="100%" />
        ))}
      </Loader>
    </div>
  );
}

export type THubEmptyStateProps = {
  /** Outline glyph (propel icon). Defaults to an inbox. */
  icon?: TGlyph;
  title?: ReactNode;
  /** Second muted line (keep it to one sentence). */
  description?: ReactNode;
  /** At most one quiet action (a `Button` variant="secondary"/"tertiary" or a link). */
  action?: ReactNode;
  /** `sm` for panes and sidebar cards, `md` (default) for page/section bodies. */
  size?: "sm" | "md";
  /** Accessible role: `status` for empty results, `alert` for errors. */
  role?: "status" | "alert";
  className?: string;
};

/** Centered outline icon + one muted line + optional quiet action (no boxes, no dashed borders). */
export function HubEmptyState({
  icon: Glyph = InboxOutline as TGlyph,
  title,
  description,
  action,
  size = "md",
  role = "status",
  className,
}: THubEmptyStateProps) {
  const { t } = useTranslation();
  return (
    <div
      role={role}
      className={cn(
        "flex w-full flex-col items-center justify-center text-center",
        size === "md" ? "gap-2 px-4 py-10" : "gap-1.5 px-3 py-6",
        className
      )}
    >
      <Glyph className={cn("shrink-0 text-placeholder", size === "md" ? "size-6" : "size-5")} aria-hidden="true" />
      <div className="flex max-w-sm flex-col gap-0.5">
        <p className="text-13 text-secondary">{title ?? t("project_hub.states.empty_title")}</p>
        {description && <p className="text-caption-md-regular text-tertiary">{description}</p>}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

/** Compat alias for the previous empty component (same props, new look). */
export function HubEmpty({
  title,
  description,
  action,
  icon,
  size,
  className,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  icon?: TGlyph;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <HubEmptyState
      title={title}
      description={description}
      action={action}
      icon={icon}
      size={size}
      className={className}
    />
  );
}

type TErrorProps = {
  error: TProjectHubApiError | null;
  onRetry?: () => void;
  /** `sm` for panes and sidebar cards. */
  size?: "sm" | "md";
  className?: string;
};

/**
 * Error state for a section, styled like the empty state. Distinguishes permission-denied,
 * extension-disabled, not-found, offline and generic failures — each with a concrete next step.
 */
export function HubErrorState({ error, onRetry, size = "md", className }: TErrorProps) {
  const { t } = useTranslation();
  const kind = getProjectHubErrorKind(error);
  const config = (() => {
    switch (kind) {
      case "permission":
        return {
          icon: LockOutline as TGlyph,
          title: t("project_hub.states.permission_title"),
          description: t("project_hub.states.permission_description"),
          retry: false,
        };
      case "disabled":
        return {
          icon: LockOutline as TGlyph,
          title: t("project_hub.states.disabled_title"),
          description: t("project_hub.states.disabled_description"),
          retry: false,
        };
      case "not_found":
        return {
          icon: SearchOutline as TGlyph,
          title: t("project_hub.states.not_found_title"),
          description: t("project_hub.states.not_found_description"),
          retry: false,
        };
      case "offline":
        return {
          icon: CloudOffOutline as TGlyph,
          title: t("project_hub.states.offline_title"),
          description: t("project_hub.errors.kind.offline"),
          retry: true,
        };
      default:
        return {
          icon: AlertCircleOutline as TGlyph,
          title: t("project_hub.states.error_title"),
          description: t(getProjectHubErrorMessageKey(error)),
          retry: true,
        };
    }
  })();
  const detail = error?.error && kind !== "permission" ? error.error : undefined;

  return (
    <HubEmptyState
      role="alert"
      size={size}
      icon={config.icon}
      title={config.title}
      description={
        detail ? (
          <>
            {config.description}
            <span className="block truncate text-caption-sm-regular text-placeholder">{detail}</span>
          </>
        ) : (
          config.description
        )
      }
      action={
        config.retry && onRetry ? (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t("project_hub.common.retry")}
            onClick={onRetry}
          />
        ) : undefined
      }
      className={className}
    />
  );
}

type TNoticeProps = {
  icon: TGlyph;
  tone?: "neutral" | "warning";
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  role?: "status" | "alert";
  className?: string;
};

/**
 * One-line inline notice (stale / offline / conflict / partial): 32px, icon + text + quiet action.
 * Calm by design — no filled banner, just a subtle layer with a hairline.
 */
export function HubNotice({
  icon: Glyph,
  tone = "neutral",
  title,
  description,
  action,
  onDismiss,
  role = "status",
  className,
}: TNoticeProps) {
  const { t } = useTranslation();
  return (
    <div
      role={role}
      className={cn(
        "flex min-h-8 w-full min-w-0 items-center gap-2 rounded-md border border-subtle bg-layer-2 py-1 pr-1 pl-2.5 text-caption-md-regular",
        className
      )}
    >
      <Glyph
        className={cn("size-3.5 shrink-0", tone === "warning" ? "text-warning-primary" : "text-tertiary")}
        aria-hidden="true"
      />
      <p className="min-w-0 flex-1 truncate text-secondary">
        <span className="font-medium text-primary">{title}</span>
        {description && <span className="text-tertiary"> · {description}</span>}
      </p>
      {action && <div className="flex shrink-0 items-center">{action}</div>}
      {onDismiss && (
        <Button variant="ghost" size="sm" stretch="auto" label={t("project_hub.common.close")} onClick={onDismiss} />
      )}
    </div>
  );
}

/** Conflict (409): never silently overwrite; offer reloading the latest server state. */
export function HubConflictBanner({ onReload, onDismiss }: { onReload: () => void; onDismiss?: () => void }) {
  const { t } = useTranslation();
  return (
    <HubNotice
      role="alert"
      tone="warning"
      icon={WarningTriangleOutline as TGlyph}
      title={t("project_hub.states.conflict_title")}
      description={t("project_hub.states.conflict_description")}
      action={
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          label={t("project_hub.states.reload_latest")}
          onClick={onReload}
        />
      }
      onDismiss={onDismiss}
    />
  );
}

/** Partial state: some sections failed but others are shown. */
export function HubPartialBanner({ sections }: { sections: string[] }) {
  const { t } = useTranslation();
  if (sections.length === 0) return null;
  return (
    <HubNotice
      icon={InfoOutline as TGlyph}
      title={t("project_hub.states.partial_title")}
      description={t("project_hub.states.partial_description", { sections: sections.join(", ") })}
    />
  );
}

/**
 * Offline / stale notice. Shown when the browser is offline or when a refresh failed while older
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
      <HubNotice
        tone="warning"
        icon={CloudOffOutline as TGlyph}
        title={t("project_hub.states.offline_title")}
        description={t("project_hub.states.offline_description")}
      />
    );
  }
  if (hasData && resource.error && getProjectHubErrorKind(resource.error) !== "conflict") {
    return (
      <HubNotice
        tone="warning"
        icon={WarningTriangleOutline as TGlyph}
        title={t("project_hub.states.stale_title")}
        description={t("project_hub.states.stale_description", { time: formatDateTime(resource.fetchedAt) })}
        action={
          <Button
            variant="ghost"
            size="sm"
            stretch="auto"
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
  /** `sm` for panes and sidebar cards (compact error state). */
  size?: "sm" | "md";
};

/**
 * Renders the designed states for one resource: Loading → Error (incl. permission/disabled/offline)
 * → Empty → content, plus Stale/Offline notice above content when a refresh failed.
 */
export const HubResourceBoundary = observer(function HubResourceBoundary<T>({
  resource,
  children,
  loadingRows,
  isEmpty,
  empty,
  size,
}: TBoundaryProps<T>) {
  if (resource.data === undefined) {
    if (resource.error)
      return <HubErrorState error={resource.error} size={size} onRetry={() => void resource.refresh()} />;
    return <HubLoading rows={loadingRows} />;
  }
  const data = resource.data;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <HubFreshnessBanner resource={resource} />
      {isEmpty?.(data) ? (empty ?? <HubEmptyState size={size} />) : children(data)}
    </div>
  );
}) as <T>(props: TBoundaryProps<T>) => ReactNode;
