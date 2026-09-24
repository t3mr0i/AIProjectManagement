/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
// plane imports
import type { BadgeVariant } from "@makeplane/propel/components/badge";
import { Badge } from "@makeplane/propel/components/badge";
import { Icon } from "@makeplane/propel/components/icon";
import {
  AlertCircleOutline,
  CircleDashedOutline,
  InfoOutline,
  PlayCircleOutline,
  TickCircleOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import type { TProjectHubTone } from "@plane/utils";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const TONE_VARIANT: Record<TProjectHubTone, BadgeVariant> = {
  neutral: "neutral",
  info: "info",
  warning: "warning",
  danger: "danger",
  success: "success",
  brand: "brand",
};

/** Every tone carries its own glyph so state is never conveyed by color alone (WCAG 1.4.1). */
const TONE_ICON: Record<TProjectHubTone, TGlyph> = {
  neutral: CircleDashedOutline as TGlyph,
  info: InfoOutline as TGlyph,
  warning: WarningTriangleOutline as TGlyph,
  danger: AlertCircleOutline as TGlyph,
  success: TickCircleOutline as TGlyph,
  brand: PlayCircleOutline as TGlyph,
};

type Props = {
  tone: TProjectHubTone;
  label: string;
  icon?: TGlyph;
  size?: "xs" | "sm" | "md";
  title?: string;
};

export function ToneBadge({ tone, label, icon, size = "sm", title }: Props) {
  const glyph = icon ?? TONE_ICON[tone];
  return (
    <span title={title} className="inline-flex max-w-full">
      <Badge variant={TONE_VARIANT[tone]} size={size} label={label} startIcon={<Icon icon={glyph} />} />
    </span>
  );
}
