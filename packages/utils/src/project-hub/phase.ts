/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPackageDelivery, TPackageFlag, TPackagePhase, TPackageStatus } from "@plane/types";

/** Visible phase order (PRD §8.2): Drafts → Ready/Next → Build → Review → Ship → Done. */
export const PROJECT_HUB_PHASES: readonly TPackagePhase[] = ["drafts", "ready", "build", "review", "ship", "done"];

export type TProjectHubTone = "neutral" | "info" | "warning" | "danger" | "success" | "brand";

/** i18n key for a phase label (namespace `project_hub`). */
export const getPhaseLabelKey = (phase: TPackagePhase): string => `project_hub.phase.${phase}`;

/** i18n key for a phase explanation. */
export const getPhaseDescriptionKey = (phase: TPackagePhase): string => `project_hub.phase_description.${phase}`;

export const getPhaseTone = (phase: TPackagePhase): TProjectHubTone => {
  switch (phase) {
    case "drafts":
      return "neutral";
    case "ready":
      return "info";
    case "build":
      return "brand";
    case "review":
      return "warning";
    case "ship":
      return "info";
    case "done":
      return "success";
    default:
      return "neutral";
  }
};

/** 1-based step index for "step x of 6" text, so the phase is never conveyed by color alone. */
export const getPhaseStep = (phase: TPackagePhase): number => PROJECT_HUB_PHASES.indexOf(phase) + 1;

export const getDeliveryLabelKey = (delivery: TPackageDelivery): string => `project_hub.delivery.${delivery}`;

export const getFlagLabelKey = (flag: TPackageFlag): string => `project_hub.flag.${flag}`;

const FLAG_TONES: Record<TPackageFlag, TProjectHubTone> = {
  blocked: "danger",
  scope_changed: "warning",
  sync_conflict: "danger",
  stale_evidence: "warning",
  integration_offline: "warning",
  native_done_without_delivery: "warning",
};

export const getFlagTone = (flag: TPackageFlag): TProjectHubTone => FLAG_TONES[flag] ?? "neutral";

const FLAG_PRIORITY: TPackageFlag[] = [
  "blocked",
  "sync_conflict",
  "native_done_without_delivery",
  "scope_changed",
  "stale_evidence",
  "integration_offline",
];

export type TProjectHubIndicatorFlag = {
  /** Either a server flag or a derived delivery hint. */
  key: TPackageFlag | "partially_integrated" | "delivery_unknown";
  labelKey: string;
  tone: TProjectHubTone;
};

export type TProjectHubIndicator = {
  phase: TPackagePhase;
  phaseLabelKey: string;
  phaseTone: TProjectHubTone;
  step: number;
  totalSteps: number;
  flags: TProjectHubIndicatorFlag[];
};

/**
 * Compact phase/evidence indicator (PLANE_DELTA §6). Flags are ordered by severity and a
 * `partially_integrated` delivery is surfaced as an explicit hint. Pure: derived only from the
 * server projection, never from native state (a native "Done" never implies delivery).
 */
export const buildPackageIndicator = (
  status: Pick<TPackageStatus, "phase" | "flags" | "delivery">
): TProjectHubIndicator => {
  const flags: TProjectHubIndicatorFlag[] = [...new Set(status.flags ?? [])]
    .toSorted((a, b) => FLAG_PRIORITY.indexOf(a) - FLAG_PRIORITY.indexOf(b))
    .map((flag) => ({ key: flag, labelKey: getFlagLabelKey(flag), tone: getFlagTone(flag) }));

  if (status.delivery === "partially_integrated") {
    flags.push({ key: "partially_integrated", labelKey: getDeliveryLabelKey("partially_integrated"), tone: "info" });
  }
  if (status.phase === "ship" && status.delivery === "unknown") {
    flags.push({ key: "delivery_unknown", labelKey: getDeliveryLabelKey("unknown"), tone: "neutral" });
  }

  return {
    phase: status.phase,
    phaseLabelKey: getPhaseLabelKey(status.phase),
    phaseTone: getPhaseTone(status.phase),
    step: getPhaseStep(status.phase),
    totalSteps: PROJECT_HUB_PHASES.length,
    flags,
  };
};

/** Group package rows into the S03 sections, preserving phase order and server row order. */
export const groupRowsByPhase = <T extends { phase: TPackagePhase }>(rows: T[]): Record<TPackagePhase, T[]> => {
  const groups = Object.fromEntries(PROJECT_HUB_PHASES.map((p) => [p, [] as T[]])) as Record<TPackagePhase, T[]>;
  for (const row of rows) {
    if (groups[row.phase]) groups[row.phase].push(row);
  }
  return groups;
};
