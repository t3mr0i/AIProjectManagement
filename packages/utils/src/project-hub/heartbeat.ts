/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Default: a heartbeat older than 2 minutes is considered stale (lease default is 300 s). */
export const PROJECT_HUB_HEARTBEAT_STALE_SECONDS = 120;

const toMillis = (value: string | Date | null | undefined): number | null => {
  if (!value) return null;
  const ms = value instanceof Date ? value.getTime() : Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
};

/** Age in whole seconds, or `null` when the timestamp is missing or invalid. */
export const getAgeSeconds = (value: string | Date | null | undefined, now: Date = new Date()): number | null => {
  const ms = toMillis(value);
  if (ms === null) return null;
  return Math.max(0, Math.floor((now.getTime() - ms) / 1000));
};

export type THeartbeatState = "fresh" | "stale" | "expired" | "unknown";

/**
 * Classify a claim/run heartbeat.
 * - `unknown`: no heartbeat was ever reported (no authorized runner → local state unknown, AC32/INV-09).
 * - `expired`: the lease end has passed.
 * - `stale`: heartbeat older than the threshold while the lease is still running.
 */
export const getHeartbeatState = (
  lastHeartbeatAt: string | Date | null | undefined,
  leaseExpiresAt?: string | Date | null,
  now: Date = new Date(),
  staleAfterSeconds: number = PROJECT_HUB_HEARTBEAT_STALE_SECONDS
): THeartbeatState => {
  const leaseMs = toMillis(leaseExpiresAt ?? null);
  if (leaseMs !== null && leaseMs <= now.getTime()) return "expired";
  const age = getAgeSeconds(lastHeartbeatAt, now);
  if (age === null) return "unknown";
  return age > staleAfterSeconds ? "stale" : "fresh";
};

export const isHeartbeatStale = (
  lastHeartbeatAt: string | Date | null | undefined,
  leaseExpiresAt?: string | Date | null,
  now: Date = new Date(),
  staleAfterSeconds: number = PROJECT_HUB_HEARTBEAT_STALE_SECONDS
): boolean => {
  const state = getHeartbeatState(lastHeartbeatAt, leaseExpiresAt, now, staleAfterSeconds);
  return state === "stale" || state === "expired";
};

/** Compact age text parts for i18n ("{value} {unit} ago"). */
export const getAgeParts = (seconds: number): { value: number; unit: "seconds" | "minutes" | "hours" | "days" } => {
  if (seconds < 60) return { value: seconds, unit: "seconds" };
  if (seconds < 3600) return { value: Math.floor(seconds / 60), unit: "minutes" };
  if (seconds < 86400) return { value: Math.floor(seconds / 3600), unit: "hours" };
  return { value: Math.floor(seconds / 86400), unit: "days" };
};
