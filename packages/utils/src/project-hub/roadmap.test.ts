/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { computeTimelineWindow, getTimelinePosition, hasReliableDate } from "./roadmap";

describe("project-hub roadmap helpers", () => {
  it("detects unreliable dates", () => {
    expect(hasReliableDate(null)).toBe(false);
    expect(hasReliableDate("2026-10-01", "unknown")).toBe(false);
    expect(hasReliableDate("2026-10-01", "estimated")).toBe(true);
    expect(hasReliableDate("nope")).toBe(false);
  });

  it("computes a padded window and clamped positions", () => {
    const now = new Date("2026-09-24T00:00:00Z");
    const window = computeTimelineWindow(["2026-10-01T00:00:00Z", null], now, 0);
    expect(window.start).toBe(now.getTime());
    expect(getTimelinePosition("2026-10-01T00:00:00Z", window)).toBe(100);
    expect(getTimelinePosition("2020-01-01T00:00:00Z", window)).toBe(0);
    expect(getTimelinePosition(null, window)).toBeNull();
  });
});
