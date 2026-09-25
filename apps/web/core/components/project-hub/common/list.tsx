/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, KeyboardEvent, MouseEvent, ReactNode, RefObject, SVGProps } from "react";
import { useCallback, useId, useState } from "react";
import Link from "next/link";
// plane imports
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Icon } from "@makeplane/propel/components/icon";
import { AddOutline, ChevronRightOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const isGlyph = (icon: TGlyph | ReactNode): icon is TGlyph => typeof icon === "function";

/** 16px glyph slot used by group bars and rows (accepts a propel glyph or a ready element). */
function SlotIcon({ icon, className }: { icon: TGlyph | ReactNode; className?: string }) {
  if (isGlyph(icon)) {
    const Glyph = icon;
    return <Glyph className={cn("size-4 shrink-0 text-tertiary", className)} aria-hidden="true" />;
  }
  return (
    <span
      className={cn("flex size-4 shrink-0 items-center justify-center [&>svg]:size-4", className)}
      aria-hidden="true"
    >
      {icon}
    </span>
  );
}

/* -------------------------------------------------------------------------------------------------
 * HubList
 * -----------------------------------------------------------------------------------------------*/

export type THubListProps = {
  children: ReactNode;
  className?: string;
  /** Accessible name of the list (a heading id via `aria-labelledby` also works on the wrapper). */
  "aria-label"?: string;
  /** `flat` (default): no outer frame, rows separated by hairlines. `card`: bordered, rounded. */
  variant?: "flat" | "card";
};

/** List container: hairline separators between rows, optional card frame. */
export function HubList({ children, className, variant = "flat", "aria-label": ariaLabel }: THubListProps) {
  return (
    <div
      role={ariaLabel ? "group" : undefined}
      aria-label={ariaLabel}
      className={cn(
        "flex w-full min-w-0 flex-col",
        variant === "card" && "overflow-hidden rounded-md border border-subtle bg-layer-1",
        className
      )}
    >
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------------------------------
 * HubGroupBar / HubListGroup
 * -----------------------------------------------------------------------------------------------*/

export type THubGroupBarProps = {
  title: ReactNode;
  icon?: TGlyph | ReactNode;
  /** Muted count after the name. */
  count?: number;
  /** Collapse state (controlled by `HubListGroup`; omit for a static bar). */
  expanded?: boolean;
  onToggle?: () => void;
  /** Renders a quiet `+` at the end. */
  onAdd?: () => void;
  addLabel?: string;
  /** Extra trailing controls (before `+`). */
  trailing?: ReactNode;
  /** Muted one-liner after the count (kept short — it must not wrap). */
  hint?: ReactNode;
  sticky?: boolean;
  /** Id of the element the bar controls (`aria-controls`). */
  controlsId?: string;
  /** Id for the title node so sections can use `aria-labelledby`. */
  titleId?: string;
  className?: string;
};

/**
 * Linear-style group bar: subtle filled layer-2 bar, ~32px, chevron + icon + name + muted count and
 * a quiet `+` on the right. Sticky while its group scrolls. Shared by lists and the activity timeline.
 */
export function HubGroupBar({
  title,
  icon,
  count,
  expanded,
  onToggle,
  onAdd,
  addLabel,
  trailing,
  hint,
  sticky = true,
  controlsId,
  titleId,
  className,
}: THubGroupBarProps) {
  const { t } = useTranslation();
  const collapsible = onToggle !== undefined;
  const label = (
    <>
      {collapsible && (
        <ChevronRightOutline
          className={cn(
            "size-3.5 shrink-0 text-tertiary transition-transform duration-100",
            expanded !== false && "rotate-90"
          )}
          aria-hidden="true"
        />
      )}
      {icon && <SlotIcon icon={icon} />}
      <span className="truncate text-13 font-medium text-primary">{title}</span>
      {count !== undefined && <span className="shrink-0 text-13 text-tertiary">{count}</span>}
      {hint && <span className="hidden min-w-0 truncate text-caption-md-regular text-tertiary md:inline">{hint}</span>}
    </>
  );
  return (
    <div
      className={cn(
        "group/hub-group-bar flex h-8 w-full min-w-0 items-center gap-1.5 bg-layer-2 pr-2 pl-3",
        sticky && "sticky top-0 z-[2]",
        className
      )}
    >
      {collapsible ? (
        <button
          type="button"
          aria-expanded={expanded !== false}
          aria-controls={controlsId}
          onClick={onToggle}
          className="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none focus-visible:ring-inset"
        >
          <span id={titleId} className="contents">
            {label}
          </span>
          <span className="sr-only">
            {expanded !== false ? t("project_hub.common.collapse") : t("project_hub.common.expand")}
          </span>
        </button>
      ) : (
        <div id={titleId} className="flex h-full min-w-0 flex-1 items-center gap-1.5">
          {label}
        </div>
      )}
      {trailing && <div className="flex shrink-0 items-center gap-1">{trailing}</div>}
      {onAdd && (
        <span className="flex shrink-0 items-center opacity-0 transition-opacity duration-100 group-hover/hub-group-bar:opacity-100 focus-within:opacity-100">
          <IconButton
            variant="ghost"
            size="xs"
            aria-label={addLabel ?? t("project_hub.common.add")}
            icon={<Icon icon={AddOutline} />}
            onClick={onAdd}
          />
        </span>
      )}
    </div>
  );
}

export type THubListGroupProps = Omit<THubGroupBarProps, "expanded" | "onToggle" | "controlsId" | "titleId"> & {
  /** Number of rows inside; drives the count, `hideWhenEmpty` and the empty line. */
  count: number;
  /** Empty groups are hidden by default (UI_GUIDELINES "Groups"). */
  showEmpty?: boolean;
  /** One muted line rendered when the group is shown while empty. */
  emptyLabel?: ReactNode;
  defaultCollapsed?: boolean;
  /** Controlled collapse state. */
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  children: ReactNode;
  className?: string;
};

/**
 * Grouped list section: sticky `HubGroupBar` + rows. Hidden while empty unless `showEmpty`;
 * collapsible with the chevron (uncontrolled by default).
 */
export function HubListGroup({
  count,
  showEmpty = false,
  emptyLabel,
  defaultCollapsed = false,
  collapsed,
  onCollapsedChange,
  children,
  className,
  ...bar
}: THubListGroupProps) {
  const { t } = useTranslation();
  const panelId = useId();
  const titleId = useId();
  const [internal, setInternal] = useState(defaultCollapsed);
  const isCollapsed = collapsed ?? internal;
  const toggle = useCallback(() => {
    const next = !isCollapsed;
    if (collapsed === undefined) setInternal(next);
    onCollapsedChange?.(next);
  }, [collapsed, isCollapsed, onCollapsedChange]);

  if (count === 0 && !showEmpty) return null;

  return (
    <section aria-labelledby={titleId} className={cn("flex min-w-0 flex-col", className)}>
      <HubGroupBar
        {...bar}
        count={count}
        expanded={!isCollapsed}
        onToggle={toggle}
        controlsId={panelId}
        titleId={titleId}
      />
      {!isCollapsed && (
        <div id={panelId} className="flex min-w-0 flex-col">
          {count === 0 ? (
            <HubListEmptyLine>{emptyLabel ?? t("project_hub.states.empty_title")}</HubListEmptyLine>
          ) : (
            children
          )}
        </div>
      )}
    </section>
  );
}

/** One muted line for an intentionally shown empty group (never a boxed message). */
export function HubListEmptyLine({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("flex h-9 items-center px-3 text-caption-md-regular text-tertiary", className)}>{children}</p>
  );
}

/* -------------------------------------------------------------------------------------------------
 * HubListRow
 * -----------------------------------------------------------------------------------------------*/

export type THubListRowProps = {
  /** The whole row is this link. */
  href?: string;
  onClick?: (event: MouseEvent<HTMLElement>) => void;
  /** Leading slot before the identifier (priority icon, checkbox, drag handle). */
  leading?: ReactNode;
  /** Muted identifier, e.g. `HUB-12`. Fixed min width keeps titles aligned. */
  identifier?: ReactNode;
  /** Status / phase glyph before the title (16px). */
  icon?: TGlyph | ReactNode;
  title: ReactNode;
  /** Trailing meta: chips, dates, avatar… Rendered right-aligned, never wrapping. */
  meta?: ReactNode;
  /** Last trailing slot (avatar or quick actions), kept visible while `meta` shrinks. */
  trailing?: ReactNode;
  /** Keyboard cursor (list navigation): visible background + left accent. */
  focused?: boolean;
  /** Selected row (two-pane lists). */
  selected?: boolean;
  /** Stable id for keyboard navigation (`data-keyboard-nav-id`). */
  navId?: string;
  id?: string;
  /** Indent nested rows (px). */
  indent?: number;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  /** Open in a new tab. */
  target?: string;
};

const ROW_BASE =
  "group/hub-row relative flex h-9 w-full min-w-0 items-center gap-2 border-b border-subtle px-3 text-13 text-primary transition-colors duration-100 last:border-b-0";
const ROW_INTERACTIVE =
  "cursor-pointer hover:bg-layer-transparent-hover focus-visible:outline-none focus-visible:bg-accent-primary/10 focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-accent-strong";

/**
 * ~36px single-line list row: `[leading] [identifier] [icon] [title…] ……… [meta] [trailing]`.
 * Renders as a link when `href` is given; nothing inside wraps (titles truncate).
 */
export function HubListRow({
  href,
  onClick,
  leading,
  identifier,
  icon,
  title,
  meta,
  trailing,
  focused,
  selected,
  navId,
  id,
  indent,
  disabled,
  className,
  target,
  "aria-label": ariaLabel,
}: THubListRowProps) {
  const interactive = !disabled && (!!href || !!onClick);
  const classes = cn(
    ROW_BASE,
    interactive && ROW_INTERACTIVE,
    selected && "bg-layer-transparent-selected",
    focused &&
      "bg-accent-primary/10 before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-accent-primary hover:bg-accent-primary/10",
    disabled && "opacity-60",
    className
  );
  const content = (
    <>
      {leading && <span className="flex shrink-0 items-center gap-1 [&>svg]:size-4">{leading}</span>}
      {identifier !== undefined && identifier !== null && (
        <span className="w-16 shrink-0 truncate text-caption-md-regular text-tertiary tabular-nums">{identifier}</span>
      )}
      {icon && <SlotIcon icon={icon} />}
      <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
      {meta && (
        <span className="flex min-w-0 shrink items-center gap-1.5 overflow-hidden whitespace-nowrap">{meta}</span>
      )}
      {trailing && <span className="flex shrink-0 items-center gap-1.5">{trailing}</span>}
    </>
  );
  const style = indent ? { paddingLeft: `${12 + indent}px` } : undefined;
  const shared = {
    id,
    "data-keyboard-nav-id": navId,
    "data-hub-row": "",
    "aria-label": ariaLabel,
    "aria-current": selected ? ("true" as const) : undefined,
    className: classes,
    style,
  };
  if (href && !disabled)
    return (
      <Link href={href} target={target} onClick={onClick} {...shared}>
        {content}
      </Link>
    );
  if (onClick && !disabled)
    return (
      <button type="button" {...shared} className={cn(shared.className, "text-left")} onClick={onClick}>
        {content}
      </button>
    );
  return <div {...shared}>{content}</div>;
}

/* -------------------------------------------------------------------------------------------------
 * Keyboard navigation (j/k, arrows, Enter)
 * -----------------------------------------------------------------------------------------------*/

const ROW_SELECTOR = "[data-hub-row]";

/**
 * Attach to a list container: j/k or ↑/↓ move focus between `HubListRow`s, Home/End jump, Enter
 * activates the focused row (its link or click). Focus is the visible cursor (rows have a ring).
 */
export const useHubListNavigation = (containerRef: RefObject<HTMLElement | null>) =>
  useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      const target = event.target as HTMLElement | null;
      if (!target || target.closest("input, textarea, select, [contenteditable=true]")) return;
      const container = containerRef.current;
      if (!container) return;
      const rows = Array.from(container.querySelectorAll<HTMLElement>(ROW_SELECTOR)).filter(
        (el) => !el.closest("[hidden]")
      );
      if (rows.length === 0) return;
      const current = target.closest<HTMLElement>(ROW_SELECTOR);
      const index = current ? rows.indexOf(current) : -1;
      let next: number | null = null;
      switch (event.key) {
        case "j":
        case "ArrowDown":
          next = Math.min(index + 1, rows.length - 1);
          break;
        case "k":
        case "ArrowUp":
          next = Math.max(index - 1, 0);
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = rows.length - 1;
          break;
        case "Enter":
          if (current && current.tagName !== "A") current.click();
          return;
        default:
          return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      event.preventDefault();
      rows[next]?.focus();
    },
    [containerRef]
  );
