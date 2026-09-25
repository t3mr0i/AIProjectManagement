/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, CSSProperties, ReactNode, SVGProps } from "react";
import Link from "next/link";
// plane imports
import type { TProjectHubTone } from "@plane/utils";
import { cn } from "@plane/utils";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/** Dot colour per tone: `bg-current` + a text token, so the dot follows the theme. */
const TONE_DOT: Record<TProjectHubTone, string> = {
  neutral: "text-placeholder",
  info: "text-accent-primary",
  warning: "text-warning-primary",
  danger: "text-danger-primary",
  success: "text-success-primary",
  brand: "text-accent-primary",
};

export type THubChipProps = {
  label: ReactNode;
  /** Semantic dot colour. Ignored when `color` is given. */
  tone?: TProjectHubTone;
  /** Arbitrary dot colour (a label colour from the API, e.g. `#ff6b6b`). */
  color?: string;
  /** Leading glyph instead of a dot (icon + text, never colour alone). */
  icon?: TGlyph | ReactNode;
  /** `outline` = neutral border (default). `soft` = filled layer, no border. */
  variant?: "outline" | "soft";
  /** Optional trailing node (count, chevron…). */
  trailing?: ReactNode;
  /** Renders the chip as a link. */
  href?: string;
  onClick?: () => void;
  title?: string;
  className?: string;
};

const isGlyph = (icon: THubChipProps["icon"]): icon is TGlyph => typeof icon === "function";

/** 12px leading glyph: accepts a propel glyph component or a ready element. */
export function ChipGlyph({ icon, className }: { icon: TGlyph | ReactNode; className?: string }) {
  if (isGlyph(icon)) {
    const Glyph = icon;
    return <Glyph className={cn("size-3 shrink-0 text-tertiary", className)} aria-hidden="true" />;
  }
  return (
    <span
      className={cn("flex size-3 shrink-0 items-center justify-center [&>svg]:size-3", className)}
      aria-hidden="true"
    >
      {icon}
    </span>
  );
}

/**
 * Linear-style chip: 20px rounded pill, colour dot (or glyph) + 12px label, neutral border or
 * soft background. Used for labels, packages, projects and state in list rows and sidebars.
 */
export function HubChip({
  label,
  tone = "neutral",
  color,
  icon,
  variant = "outline",
  trailing,
  href,
  onClick,
  title,
  className,
}: THubChipProps) {
  const dotStyle: CSSProperties | undefined = color ? { backgroundColor: color } : undefined;
  const interactive = !!href || !!onClick;
  const classes = cn(
    "inline-flex h-5 max-w-full shrink-0 items-center gap-1 rounded-full px-1.5 text-caption-md-regular text-secondary",
    variant === "outline" ? "border border-subtle bg-layer-1" : "bg-layer-2",
    interactive &&
      "cursor-pointer transition-colors duration-100 hover:bg-layer-transparent-hover hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
    className
  );
  const content = (
    <>
      {icon ? (
        <ChipGlyph icon={icon} />
      ) : (
        <span
          className={cn("size-1.5 shrink-0 rounded-full bg-current", !color && TONE_DOT[tone])}
          style={dotStyle}
          aria-hidden="true"
        />
      )}
      <span className="min-w-0 truncate">{label}</span>
      {trailing && <span className="flex shrink-0 items-center text-tertiary">{trailing}</span>}
    </>
  );
  if (href)
    return (
      <Link href={href} title={title} className={classes} onClick={onClick}>
        {content}
      </Link>
    );
  if (onClick)
    return (
      <button type="button" title={title} className={classes} onClick={onClick}>
        {content}
      </button>
    );
  return (
    <span title={title} className={classes}>
      {content}
    </span>
  );
}
