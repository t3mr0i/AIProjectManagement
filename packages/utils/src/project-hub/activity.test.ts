/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import type { TPHActivityFeed, TPHActivityGroup } from "@plane/types";
import { adaptActivityFeed, groupActivityByDay, toDayKey } from "./activity";

const feed: Pick<TPHActivityFeed, "groups" | "open_decisions"> = {
  groups: [
    {
      issue_id: "p1",
      issue_name: "Export",
      identifier: "PRJ-1",
      last_at: "2026-09-24T10:00:00Z",
      days: [
        {
          date: "2026-09-24",
          entries: [
            {
              kind: "summary",
              event_type: "run.progress",
              count: 3,
              summary: "3 progress updates (3 observed)",
              raw_ids: ["a", "b", "c"],
              first_at: "2026-09-24T08:00:00Z",
              occurred_at: "2026-09-24T10:00:00Z",
            },
            {
              kind: "event",
              id: "e1",
              source: "package_flow",
              event_type: "run.started",
              summary: "Run started",
              reason: "approved revision 2",
              actor_kind: "agent",
              actor_id: "r1",
              occurred_at: "2026-09-24T07:00:00Z",
              is_fixture: false,
            },
          ],
        },
        { date: "2026-09-23", entries: [] },
      ],
    },
    {
      issue_id: null,
      issue_name: null,
      identifier: null,
      last_at: "2026-09-22T10:00:00Z",
      days: [
        {
          date: "2026-09-22",
          entries: [
            {
              kind: "native",
              id: "n1",
              source: "plane",
              event_type: "native.updated",
              field: "name",
              summary: "updated name",
              old_value: "a",
              new_value: "b",
              actor_id: "u1",
              occurred_at: "2026-09-22T10:00:00Z",
            },
          ],
        },
      ],
    },
  ],
  open_decisions: [
    {
      id: "d1",
      title: "Pick CSV",
      kind: "decision",
      status: "proposed",
      issue_id: "p1",
      confirmed_at: null,
      created_at: "",
    },
  ],
};

describe("project-hub activity helpers", () => {
  it("builds day keys in a given time zone", () => {
    expect(toDayKey("2026-09-24T23:30:00Z", "UTC")).toBe("2026-09-24");
    expect(toDayKey("2026-09-24T23:30:00Z", "Europe/Berlin")).toBe("2026-09-25");
    expect(toDayKey("garbage")).toBe("unknown");
  });

  it("adapts the server feed into package/day groups", () => {
    const groups = adaptActivityFeed(feed);
    expect(groups).toHaveLength(2);
    const [pkg, project] = groups;
    expect(pkg?.day).toBe("2026-09-24");
    expect(pkg?.event_count).toBe(4);
    expect(pkg?.first_at).toBe("2026-09-24T07:00:00Z");
    expect(pkg?.last_at).toBe("2026-09-24T10:00:00Z");
    expect(pkg?.reasons).toEqual(["approved revision 2"]);
    expect(pkg?.decision_needed).toBe(true);
    expect(pkg?.responsible_kind).toBe("agent");
    expect(pkg?.identifier).toBe("PRJ-1");
    expect(project?.issue_id).toBeNull();
    expect(project?.responsible_kind).toBe("human");
  });

  it("sorts days newest first and decisions first inside a day", () => {
    const base = { reasons: [] as string[], event_count: 1, entries: [], summary: "" };
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
