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
import { buildPackageIndicator, cn, getPhaseDescriptionKey } from "@plane/utils";
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

type Props = {
  status: Pick<TPackageStatus, "phase" | "flags" | "delivery">;
  /** `compact`: phase only + flag count (list rows). `full`: phase, step text and all flags. */
  variant?: "compact" | "full";
  className?: string;
};

/**
 * Compact Build–Review–Ship indicator (PLANE_DELTA §6). Phase text + icon + step number, and flags
 * such as "Done without delivery evidence" as separate labelled badges — never color alone.
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
        <ToneBadge
          tone={indicator.phaseTone}
          icon={PHASE_ICONS[indicator.phase]}
          label={phaseLabel}
          size="xs"
          title={t(getPhaseDescriptionKey(indicator.phase))}
        />
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
        <ToneBadge key={flag.key} tone={flag.tone} label={t(flag.labelKey)} />
      ))}
    </div>
  );
}
