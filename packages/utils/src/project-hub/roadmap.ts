/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPHDateConfidence } from "@plane/types";

const DAY_MS = 86_400_000;

/** A date is only reliable when it exists, parses and is not marked `unknown`. */
export const hasReliableDate = (value: string | null | undefined, confidence?: TPHDateConfidence): boolean => {
  if (!value || confidence === "unknown") return false;
  return !Number.isNaN(Date.parse(value));
};

export type TTimelineWindow = { start: number; end: number };

/**
 * Compute a time window around the given dates with padding, defaulting to a short window around
 * `now` (a few short projects should not render an empty year, DESIGN_BRIEF M03).
 */
export const computeTimelineWindow = (
  dates: (string | null | undefined)[],
  now: Date = new Date(),
  paddingDays = 7
): TTimelineWindow => {
  const values = dates.map((d) => (d ? Date.parse(d) : Number.NaN)).filter((v) => !Number.isNaN(v));
  const nowMs = now.getTime();
  const min = values.length ? Math.min(...values, nowMs) : nowMs - 14 * DAY_MS;
  const max = values.length ? Math.max(...values, nowMs) : nowMs + 42 * DAY_MS;
  return { start: min - paddingDays * DAY_MS, end: max + paddingDays * DAY_MS };
};

/** Relative position (0..100 %) of a date within a window, clamped. */
export const getTimelinePosition = (value: string | null | undefined, window: TTimelineWindow): number | null => {
  if (!value) return null;
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const span = window.end - window.start;
  if (span <= 0) return 0;
  return Math.min(100, Math.max(0, ((ms - window.start) / span) * 100));
};
