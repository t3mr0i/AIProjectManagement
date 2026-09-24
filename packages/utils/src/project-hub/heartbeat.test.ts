/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getAgeParts, getAgeSeconds, getHeartbeatState, isHeartbeatStale } from "./heartbeat";

const now = new Date("2026-09-24T12:00:00Z");

describe("project-hub heartbeat helpers", () => {
  it("computes ages and handles invalid input", () => {
    expect(getAgeSeconds("2026-09-24T11:59:00Z", now)).toBe(60);
    expect(getAgeSeconds(null, now)).toBeNull();
    expect(getAgeSeconds("not a date", now)).toBeNull();
  });

  it("classifies heartbeat state", () => {
    const lease = "2026-09-24T12:05:00Z";
    expect(getHeartbeatState("2026-09-24T11:59:30Z", lease, now)).toBe("fresh");
    expect(getHeartbeatState("2026-09-24T11:50:00Z", lease, now)).toBe("stale");
    expect(getHeartbeatState(null, lease, now)).toBe("unknown");
    expect(getHeartbeatState("2026-09-24T11:59:30Z", "2026-09-24T11:59:59Z", now)).toBe("expired");
  });

  it("treats stale and expired as stale", () => {
    expect(isHeartbeatStale("2026-09-24T11:50:00Z", null, now)).toBe(true);
    expect(isHeartbeatStale("2026-09-24T11:59:50Z", "2026-09-24T11:00:00Z", now)).toBe(true);
    expect(isHeartbeatStale("2026-09-24T11:59:50Z", null, now)).toBe(false);
    expect(isHeartbeatStale(null, null, now)).toBe(false);
  });

  it("splits ages into display units", () => {
    expect(getAgeParts(30)).toEqual({ value: 30, unit: "seconds" });
    expect(getAgeParts(125)).toEqual({ value: 2, unit: "minutes" });
    expect(getAgeParts(7200)).toEqual({ value: 2, unit: "hours" });
    expect(getAgeParts(200000)).toEqual({ value: 2, unit: "days" });
  });
});
