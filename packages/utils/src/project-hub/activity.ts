/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPHActivityEvent, TPHActivityGroup } from "@plane/types";

/** YYYY-MM-DD in the given IANA time zone (default: browser/local). */
export const toDayKey = (value: string | Date, timeZone?: string): string => {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
};

export type TActivityDaySection = {
  day: string;
  groups: TPHActivityGroup[];
};

/**
 * Arrange server activity groups into day sections (newest day first); inside a day, groups with
 * a needed decision come first, then by latest event. Imported historic events keep their original
 * day because the day is derived from `last_at`/`day` of the server, never from receipt time.
 */
export const groupActivityByDay = (groups: TPHActivityGroup[]): TActivityDaySection[] => {
  const byDay = new Map<string, TPHActivityGroup[]>();
  for (const group of groups) {
    const day = group.day || toDayKey(group.last_at);
    const list = byDay.get(day) ?? [];
    list.push(group);
    byDay.set(day, list);
  }
  return [...byDay.entries()]
    .toSorted(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([day, list]) => ({
      day,
      groups: list.toSorted((a, b) => {
        if (!!a.decision_needed !== !!b.decision_needed) return a.decision_needed ? -1 : 1;
        return Date.parse(b.last_at) - Date.parse(a.last_at);
      }),
    }));
};

/**
 * Client-side fallback: build package/day groups from raw events when the server returns an
 * ungrouped list. Events without a package land in a `null` package group.
 */
export const buildActivityGroups = (
  events: (TPHActivityEvent & { issue_id?: string | null; package_name?: string })[],
  timeZone?: string
): TPHActivityGroup[] => {
  const map = new Map<string, TPHActivityGroup>();
  for (const event of events) {
    const day = toDayKey(event.occurred_at, timeZone);
    const key = `${event.issue_id ?? "none"}::${day}`;
    const existing = map.get(key);
    if (existing) {
      existing.events.push(event);
      existing.event_count += 1;
      if (event.occurred_at < existing.first_at) existing.first_at = event.occurred_at;
      if (event.occurred_at > existing.last_at) existing.last_at = event.occurred_at;
    } else {
      map.set(key, {
        issue_id: event.issue_id ?? null,
        package_name: event.package_name ?? "",
        day,
        summary: event.summary,
        reasons: [],
        event_count: 1,
        first_at: event.occurred_at,
        last_at: event.occurred_at,
        events: [event],
      });
    }
  }
  for (const group of map.values()) {
    group.events.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at));
  }
  return [...map.values()];
};
