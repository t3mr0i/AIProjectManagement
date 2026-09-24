/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import type { TPHActivityEvent, TPHActivityGroup } from "@plane/types";
import { buildActivityGroups, groupActivityByDay, toDayKey } from "./activity";

const event = (
  id: string,
  occurred_at: string,
  issue_id: string | null
): TPHActivityEvent & { issue_id: string | null } => ({
  id,
  event_type: "run.progress",
  summary: `event ${id}`,
  occurred_at,
  source_kind: "runner",
  actor_kind: "agent",
  issue_id,
});

describe("project-hub activity helpers", () => {
  it("builds day keys in a given time zone", () => {
    expect(toDayKey("2026-09-24T23:30:00Z", "UTC")).toBe("2026-09-24");
    expect(toDayKey("2026-09-24T23:30:00Z", "Europe/Berlin")).toBe("2026-09-25");
    expect(toDayKey("garbage")).toBe("unknown");
  });

  it("groups raw events by package and day", () => {
    const groups = buildActivityGroups(
      [
        event("1", "2026-09-24T10:00:00Z", "p1"),
        event("2", "2026-09-24T09:00:00Z", "p1"),
        event("3", "2026-09-23T10:00:00Z", "p1"),
        event("4", "2026-09-24T11:00:00Z", null),
      ],
      "UTC"
    );
    expect(groups).toHaveLength(3);
    const p1Today = groups.find((g) => g.issue_id === "p1" && g.day === "2026-09-24");
    expect(p1Today?.event_count).toBe(2);
    expect(p1Today?.first_at).toBe("2026-09-24T09:00:00Z");
    expect(p1Today?.events.map((e) => e.id)).toEqual(["2", "1"]);
  });

  it("sorts days newest first and decisions first inside a day", () => {
    const base = { reasons: [] as string[], event_count: 1, events: [], summary: "" };
    const groups: TPHActivityGroup[] = [
      { ...base, issue_id: "a", day: "2026-09-23", first_at: "2026-09-23T08:00:00Z", last_at: "2026-09-23T08:00:00Z" },
      { ...base, issue_id: "b", day: "2026-09-24", first_at: "2026-09-24T08:00:00Z", last_at: "2026-09-24T09:00:00Z" },
      {
        ...base,
        issue_id: "c",
        day: "2026-09-24",
        first_at: "2026-09-24T07:00:00Z",
        last_at: "2026-09-24T07:00:00Z",
        decision_needed: true,
      },
    ];
    const sections = groupActivityByDay(groups);
    expect(sections.map((s) => s.day)).toEqual(["2026-09-24", "2026-09-23"]);
    expect(sections[0]?.groups.map((g) => g.issue_id)).toEqual(["c", "b"]);
  });
});
