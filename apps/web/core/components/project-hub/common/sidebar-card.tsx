/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useId, useState } from "react";
import Link from "next/link";
// plane imports
import { ChevronRightOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

export type THubSidebarCardProps = {
  title: ReactNode;
  icon?: TGlyph;
  /** Header-end control (icon button, count…). Sibling of the toggle, never nested in it. */
  trailing?: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** `rows` (default): children are `HubPropertyRow`s, no inner padding. `content`: padded body. */
  body?: "rows" | "content";
  children: ReactNode;
  className?: string;
};

/**
 * Collapsible titled card for right detail sidebars (Linear's Properties / Labels / Project cards).
 * Subtle layer-2 header bar with a chevron; the body stacks `HubPropertyRow`s.
 */
export function HubSidebarCard({
  title,
  icon: Glyph,
  trailing,
  defaultOpen = true,
  open,
  onOpenChange,
  body = "rows",
  children,
  className,
}: THubSidebarCardProps) {
  const { t } = useTranslation();
  const panelId = useId();
  const [internal, setInternal] = useState(defaultOpen);
  const isOpen = open ?? internal;
  const toggle = () => {
    const next = !isOpen;
    if (open === undefined) setInternal(next);
    onOpenChange?.(next);
  };
  return (
    <section
      className={cn("flex min-w-0 flex-col overflow-hidden rounded-md border border-subtle bg-layer-1", className)}
    >
      <div className="flex h-8 items-center gap-1 bg-layer-2 pr-1.5 pl-2">
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls={panelId}
          onClick={toggle}
          className="flex h-full min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none focus-visible:ring-inset"
        >
          <ChevronRightOutline
            className={cn("size-3.5 shrink-0 text-tertiary transition-transform duration-100", isOpen && "rotate-90")}
            aria-hidden="true"
          />
          {Glyph && <Glyph className="size-4 shrink-0 text-tertiary" aria-hidden="true" />}
          <span className="truncate text-13 font-medium text-primary">{title}</span>
          <span className="sr-only">{isOpen ? t("project_hub.common.collapse") : t("project_hub.common.expand")}</span>
        </button>
        {trailing && <div className="flex shrink-0 items-center gap-1">{trailing}</div>}
      </div>
      {isOpen && (
        <div id={panelId} className={cn("flex min-w-0 flex-col", body === "content" ? "gap-2 p-3" : "py-1")}>
          {children}
        </div>
      )}
    </section>
  );
}

export type THubPropertyRowProps = {
  icon?: TGlyph;
  label: ReactNode;
  /** Value node (text, chip, avatar). Omitted → `placeholder` in muted colour. */
  value?: ReactNode;
  placeholder?: ReactNode;
  /** Makes the value a button (opens a picker). */
  onClick?: () => void;
  /** Makes the value a link. */
  href?: string;
  /** Custom right side (e.g. a propel Select). Replaces `value`. */
  children?: ReactNode;
  className?: string;
};

/**
 * One property line: `[icon] label ………… value`. 32px, label muted, value in primary text; the
 * value becomes a quiet button/link when interactive.
 */
export function HubPropertyRow({
  icon: Glyph,
  label,
  value,
  placeholder,
  onClick,
  href,
  children,
  className,
}: THubPropertyRowProps) {
  const { t } = useTranslation();
  const isEmpty = value === undefined || value === null || value === "";
  const valueNode = isEmpty ? (
    <span className="text-placeholder">{placeholder ?? t("project_hub.common.none")}</span>
  ) : (
    value
  );
  const valueClasses =
    "flex h-6 min-w-0 max-w-full items-center gap-1.5 truncate rounded-sm px-1.5 text-13 text-primary";
  const interactiveClasses =
    "cursor-pointer transition-colors duration-100 hover:bg-layer-transparent-hover focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-strong";
  let right: ReactNode;
  if (children) right = children;
  else if (href)
    right = (
      <Link href={href} className={cn(valueClasses, interactiveClasses)}>
        {valueNode}
      </Link>
    );
  else if (onClick)
    right = (
      <button type="button" onClick={onClick} className={cn(valueClasses, interactiveClasses, "-mx-1.5")}>
        {valueNode}
      </button>
    );
  else right = <span className={cn(valueClasses, "px-0")}>{valueNode}</span>;

  return (
    <div className={cn("flex min-h-8 min-w-0 items-center gap-2 px-3", className)}>
      <div className="flex w-24 shrink-0 items-center gap-1.5 text-caption-md-regular text-tertiary">
        {Glyph && <Glyph className="size-3.5 shrink-0" aria-hidden="true" />}
        <span className="truncate">{label}</span>
      </div>
      <div className="flex min-w-0 flex-1 items-center justify-end overflow-hidden">{right}</div>
    </div>
  );
}
