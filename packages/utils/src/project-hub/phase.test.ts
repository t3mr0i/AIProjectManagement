/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { buildPackageIndicator, getPhaseLabelKey, getPhaseStep, groupRowsByPhase, PROJECT_HUB_PHASES } from "./phase";

describe("project-hub phase helpers", () => {
  it("maps phases to i18n keys and ordered steps", () => {
    expect(getPhaseLabelKey("build")).toBe("project_hub.phase.build");
    expect(PROJECT_HUB_PHASES).toEqual(["drafts", "ready", "build", "review", "ship", "done"]);
    expect(getPhaseStep("drafts")).toBe(1);
    expect(getPhaseStep("done")).toBe(6);
  });

  it("orders flags by severity and dedupes", () => {
    const indicator = buildPackageIndicator({
      phase: "done",
      delivery: "not_integrated",
      flags: ["integration_offline", "native_done_without_delivery", "blocked", "blocked"],
    });
    expect(indicator.flags.map((f) => f.key)).toEqual([
      "blocked",
      "native_done_without_delivery",
      "integration_offline",
    ]);
    expect(indicator.flags[1]?.labelKey).toBe("project_hub.flag.native_done_without_delivery");
    expect(indicator.totalSteps).toBe(6);
  });

  it("surfaces partial integration and unknown delivery as explicit hints", () => {
    expect(
      buildPackageIndicator({ phase: "ship", delivery: "partially_integrated", flags: [] }).flags.map((f) => f.key)
    ).toEqual(["partially_integrated"]);
    expect(buildPackageIndicator({ phase: "ship", delivery: "unknown", flags: [] }).flags.map((f) => f.key)).toEqual([
      "delivery_unknown",
    ]);
    expect(buildPackageIndicator({ phase: "build", delivery: "unknown", flags: [] }).flags).toEqual([]);
  });

  it("groups rows into all sections keeping order", () => {
    const groups = groupRowsByPhase([
      { id: "a", phase: "build" as const },
      { id: "b", phase: "drafts" as const },
      { id: "c", phase: "build" as const },
    ]);
    expect(groups.build.map((r) => r.id)).toEqual(["a", "c"]);
    expect(groups.drafts.map((r) => r.id)).toEqual(["b"]);
    expect(groups.done).toEqual([]);
  });

  it("treats a missing phase as drafts and tones server-only flags", () => {
    const indicator = buildPackageIndicator({
      phase: null,
      delivery: "unknown",
      flags: ["merge_pending_confirmation", "native_done_without_delivery_evidence"],
    });
    expect(indicator.phase).toBe("drafts");
    expect(indicator.step).toBe(1);
    expect(indicator.flags.map((f) => f.key)).toEqual([
      "native_done_without_delivery_evidence",
      "merge_pending_confirmation",
    ]);
    expect(indicator.flags[1]?.tone).toBe("info");
  });
});
