/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPHActivityEntry, TPHActivityFeed, TPHActivityGroup } from "@plane/types";

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

const entryStart = (e: TPHActivityEntry) => (e.kind === "summary" ? e.first_at : e.occurred_at);
const entryCount = (e: TPHActivityEntry) => (e.kind === "summary" ? e.count : 1);

/**
 * Project the server feed (`groups[].days[].entries[]`) into one UI group per package and day.
 * The day comes from the server (original event date; imported history keeps its date). Reasons
 * are the non-empty event reasons; `decision_needed` marks packages with open decisions; an agent
 * actor marks the group as agent work under human responsibility.
 */
export const adaptActivityFeed = (feed: Pick<TPHActivityFeed, "groups" | "open_decisions">): TPHActivityGroup[] => {
  const openByIssue = new Set((feed.open_decisions ?? []).map((d) => d.issue_id).filter(Boolean));
  const out: TPHActivityGroup[] = [];
  for (const group of feed.groups ?? []) {
    for (const day of group.days ?? []) {
      const entries = day.entries ?? [];
      if (entries.length === 0) continue;
      const times = entries.flatMap((e) => [entryStart(e), e.occurred_at]).filter(Boolean);
      const sortedTimes = times.toSorted();
      const reasons = [
        ...new Set(entries.map((e) => (e.kind === "event" ? e.reason : "")).filter((r): r is string => !!r)),
      ];
      const hasAgent = entries.some((e) => e.kind === "event" && e.actor_kind === "agent");
      const onlySystem = entries.every((e) => e.kind === "event" && e.actor_kind === "system");
      out.push({
        issue_id: group.issue_id,
        package_name: group.issue_name,
        identifier: group.identifier,
        day: day.date,
        summary: entries[0]?.summary ?? "",
        reasons,
        decision_needed: !!group.issue_id && openByIssue.has(group.issue_id),
        responsible_kind: hasAgent ? "agent" : onlySystem ? "system" : "human",
        event_count: entries.reduce((sum, e) => sum + entryCount(e), 0),
        first_at: sortedTimes[0] ?? group.last_at,
        last_at: sortedTimes[sortedTimes.length - 1] ?? group.last_at,
        entries,
      });
    }
  }
  return out;
};

export type TActivityDaySection = {
  day: string;
  groups: TPHActivityGroup[];
};

/**
 * Arrange activity groups into day sections (newest day first); inside a day, groups with a needed
 * decision come first, then by latest event.
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
