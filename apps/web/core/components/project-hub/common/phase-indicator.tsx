/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
// plane imports
import {
  BuildOutline,
  DraftsOutline,
  PlayCircleOutline,
  RocketOutline,
  ShowOutline,
  TickCircleOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPackagePhase, TPackageStatus } from "@plane/types";
import { buildPackageIndicator, cn, getPhaseDescriptionKey, getPhaseLabelKey, getPhaseTone } from "@plane/utils";
// local imports
import { ToneBadge } from "./tone-badge";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

export const PHASE_ICONS: Record<TPackagePhase, TGlyph> = {
  drafts: DraftsOutline as TGlyph,
  ready: PlayCircleOutline as TGlyph,
  build: BuildOutline as TGlyph,
  review: ShowOutline as TGlyph,
  ship: RocketOutline as TGlyph,
  done: TickCircleOutline as TGlyph,
};

/** Text colour per phase for the bare glyph (list rows, group bars). Never the only signal. */
const PHASE_ICON_TINT: Record<TPackagePhase, string> = {
  drafts: "text-tertiary",
  ready: "text-accent-primary",
  build: "text-warning-primary",
  review: "text-accent-primary",
  ship: "text-accent-primary",
  done: "text-success-primary",
};

/** 16px phase glyph with a tooltip label (rows, group bars). */
export function HubPhaseIcon({ phase, className }: { phase: TPackagePhase; className?: string }) {
  const { t } = useTranslation();
  const Glyph = PHASE_ICONS[phase];
  const label = t(getPhaseLabelKey(phase));
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn("flex size-4 shrink-0 items-center justify-center", PHASE_ICON_TINT[phase], className)}
    >
      <Glyph className="size-4" aria-hidden="true" />
    </span>
  );
}

/** Icon + text phase badge (Drafts/Ready/Build/Review/Ship/Done) — never colour alone. */
export function HubPhaseBadge({
  phase,
  size = "xs",
  className,
}: {
  phase: TPackagePhase;
  size?: "xs" | "sm" | "md";
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline-flex max-w-full", className)}>
      <ToneBadge
        tone={getPhaseTone(phase)}
        icon={PHASE_ICONS[phase]}
        label={t(getPhaseLabelKey(phase))}
        size={size}
        title={t(getPhaseDescriptionKey(phase))}
      />
    </span>
  );
}

type Props = {
  status: Pick<TPackageStatus, "phase" | "flags" | "delivery">;
  /** `compact`: phase only + flag count (list rows). `full`: phase, step text and all flags. */
  variant?: "compact" | "full";
  className?: string;
};

/**
 * Build–Review–Ship indicator (PLANE_DELTA §6). Phase icon + text (+ step in `full`), and flags
 * such as "Done without delivery evidence" as separate labelled badges — never colour alone.
 */
export function PackagePhaseIndicator({ status, variant = "full", className }: Props) {
  const { t } = useTranslation();
  const indicator = buildPackageIndicator(status);
  const phaseLabel = t(indicator.phaseLabelKey);
  const flagLabels = indicator.flags.map((f) => t(f.labelKey));
  const stepText = t("project_hub.phase_step", { step: indicator.step, total: indicator.totalSteps });
  const ariaLabel = t("project_hub.indicator.aria", {
    phase: `${phaseLabel} (${stepText})`,
    details: flagLabels.join(", "),
  });

  if (variant === "compact") {
    const first = indicator.flags[0];
    return (
      <span className={cn("inline-flex items-center gap-1", className)} aria-label={ariaLabel} role="img">
        <HubPhaseBadge phase={indicator.phase} size="xs" />
        {first && (
          <ToneBadge
            tone={first.tone}
            label={
              indicator.flags.length > 1 ? `${t(first.labelKey)} +${indicator.flags.length - 1}` : t(first.labelKey)
            }
            size="xs"
            title={flagLabels.join(", ")}
          />
        )}
      </span>
    );
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <span className="sr-only">{t("project_hub.indicator.label")}:</span>
      <ToneBadge
        tone={indicator.phaseTone}
        icon={PHASE_ICONS[indicator.phase]}
        label={`${phaseLabel} · ${stepText}`}
        title={t(getPhaseDescriptionKey(indicator.phase))}
      />
      {indicator.flags.map((flag) => (
        <ToneBadge key={flag.key} tone={flag.tone} label={t(flag.labelKey)} size="xs" />
      ))}
    </div>
  );
}
