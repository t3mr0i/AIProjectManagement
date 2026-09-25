/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// components
import { PageHead } from "@/components/core/page-title";
// local imports
import { ProjectHubGate } from "./gate";
import { HubErrorState, HubLoading } from "./states";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

export type THubViewTab = {
  key: string;
  label: string;
  icon?: TGlyph;
  /** Muted count after the label. */
  count?: number;
  /** Link tab (route-based views). Otherwise `onTabChange` is called. */
  href?: string;
};

export type THubViewTabsProps = {
  tabs: THubViewTab[];
  activeKey: string;
  onTabChange?: (key: string) => void;
  "aria-label"?: string;
  className?: string;
};

/** Small pill view-switch ("All / Active / Backlog", "Timeline / Table"). */
export function HubViewTabs({ tabs, activeKey, onTabChange, className, "aria-label": ariaLabel }: THubViewTabsProps) {
  return (
    <div role="tablist" aria-label={ariaLabel} className={cn("flex min-w-0 items-center gap-0.5", className)}>
      {tabs.map((tab) => {
        const active = tab.key === activeKey;
        const Glyph = tab.icon;
        const classes = cn(
          "flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2 text-13 transition-colors duration-100 focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
          active
            ? "bg-layer-2 font-medium text-primary"
            : "text-secondary hover:bg-layer-transparent-hover hover:text-primary"
        );
        const content = (
          <>
            {Glyph && <Glyph className="size-3.5 shrink-0" aria-hidden="true" />}
            <span>{tab.label}</span>
            {tab.count !== undefined && <span className="text-caption-md-regular text-tertiary">{tab.count}</span>}
          </>
        );
        if (tab.href)
          return (
            <Link key={tab.key} href={tab.href} role="tab" aria-selected={active} className={classes}>
              {content}
            </Link>
          );
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onTabChange?.(tab.key)}
            className={classes}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}

export type THubPageHeaderProps = {
  /** Visible title — only for settings-style pages. List/board pages rely on the breadcrumb. */
  title?: ReactNode;
  description?: ReactNode;
  /** View pills on the left of the bar. */
  tabs?: THubViewTabsProps;
  /** Icon controls (filter, display) right of the tabs. */
  controls?: ReactNode;
  /** Primary/secondary actions, right-aligned. */
  actions?: ReactNode;
  className?: string;
};

/**
 * 44px header row under the native breadcrumb bar: view tabs on the left, icon controls and
 * actions on the right. Renders nothing when it has no content. With `title` it becomes the
 * settings-style heading (title + one muted line).
 */
export function HubPageHeader({ title, description, tabs, controls, actions, className }: THubPageHeaderProps) {
  const hasLeft = !!title || !!tabs;
  const hasRight = !!controls || !!actions;
  if (!hasLeft && !hasRight) return null;
  return (
    <div
      className={cn(
        "flex w-full min-w-0 shrink-0 items-center gap-3 border-b border-subtle px-4 md:px-6",
        title ? "min-h-11 py-2" : "h-11",
        className
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {title && (
          <div className="flex min-w-0 flex-col">
            <h1 className="truncate text-body-sm-medium text-primary">{title}</h1>
            {description && <p className="truncate text-caption-md-regular text-tertiary">{description}</p>}
          </div>
        )}
        {tabs && <HubViewTabs {...tabs} />}
      </div>
      {hasRight && (
        <div className="flex shrink-0 items-center gap-1.5">
          {controls && <div className="flex items-center gap-0.5">{controls}</div>}
          {actions && <div className="flex items-center gap-1.5">{actions}</div>}
        </div>
      )}
    </div>
  );
}

export type THubPageProps = {
  /** Document title (browser tab). Rendered as a heading only with `showTitle`. */
  title: string;
  /** Muted line under the heading (only with `showTitle`). */
  description?: string;
  /** Settings-style pages show the H1; list/board pages must not repeat the breadcrumb. */
  showTitle?: boolean;
  tabs?: THubViewTabsProps;
  controls?: ReactNode;
  actions?: ReactNode;
  /** Content width: `default` (max 6xl, centered), `full` (edge to edge), `narrow` (settings, 640px). */
  width?: "default" | "full" | "narrow";
  /** Remove the content padding (lists that own their gutters). */
  flush?: boolean;
  children: ReactNode;
  /** Applied to the content column. `max-w-none` still works as before. */
  className?: string;
};

const WIDTH_CLASS: Record<NonNullable<THubPageProps["width"]>, string> = {
  default: "mx-auto max-w-6xl",
  full: "max-w-none",
  narrow: "mx-auto max-w-2xl",
};

/** Standard Project Hub page: header row + content column (same surface as native list pages). */
export function HubPage({
  title,
  description,
  showTitle = false,
  tabs,
  controls,
  actions,
  width = "default",
  flush = false,
  children,
  className,
}: THubPageProps) {
  return (
    <div className="flex size-full flex-col overflow-y-auto">
      <PageHead title={title} />
      <HubPageHeader
        title={showTitle ? title : undefined}
        description={showTitle ? description : undefined}
        tabs={tabs}
        controls={controls}
        actions={actions}
      />
      <main
        className={cn(
          "flex w-full min-w-0 flex-col gap-4",
          WIDTH_CLASS[width],
          !flush && "px-4 py-4 md:px-6",
          className
        )}
      >
        {children}
      </main>
    </div>
  );
}

/** Page-level feature gate: disabled extension renders the designed "disabled" state, not a 404. */
export const HubPageGate = observer(function HubPageGate({
  workspaceSlug,
  projectId,
  children,
}: {
  workspaceSlug: string;
  projectId?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <ProjectHubGate
      workspaceSlug={workspaceSlug}
      projectId={projectId}
      loading={
        <div className="p-6">
          <HubLoading rows={4} />
        </div>
      }
      fallback={
        <div className="mx-auto max-w-2xl p-6">
          <PageHead title={t("project_hub.name")} />
          <HubErrorState error={{ status: 403, code: "EXTENSION_DISABLED", error: "" }} />
        </div>
      }
    >
      {children}
    </ProjectHubGate>
  );
});
