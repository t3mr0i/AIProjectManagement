/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { deriveCriterionState, getTrustLabelKey, safeCriterionState, shortHash } from "./evidence";

describe("project-hub evidence helpers", () => {
  it("never treats a commit message claim or self report as proof", () => {
    expect(deriveCriterionState([{ trust: "commit_message", result: "passed" }])).toBe("not_proven");
    expect(deriveCriterionState([{ trust: "local_self_report", result: "passed" }])).toBe("not_proven");
    expect(safeCriterionState("proven", [{ trust: "commit_message", result: "passed" }])).toBe("not_proven");
  });

  it("accepts CI, runner and human evidence as proof unless stale", () => {
    expect(deriveCriterionState([{ trust: "provider_ci", result: "passed" }])).toBe("proven");
    expect(deriveCriterionState([{ trust: "provider_ci", result: "passed", is_stale: true }])).toBe("not_proven");
    expect(deriveCriterionState([{ trust: "human", result: "passed" }])).toBe("proven");
  });

  it("reports failures before passes", () => {
    expect(
      deriveCriterionState([
        { trust: "provider_ci", result: "passed" },
        { trust: "runner_reported", result: "failed" },
      ])
    ).toBe("failed");
    expect(safeCriterionState("failed", [])).toBe("failed");
    expect(safeCriterionState(undefined, [])).toBe("not_proven");
  });

  it("formats trust labels and hashes", () => {
    expect(getTrustLabelKey("provider_ci")).toBe("project_hub.trust.provider_ci");
    expect(getTrustLabelKey("mystery")).toBe("project_hub.trust.unknown");
    expect(shortHash("0123456789abcdef")).toBe("01234567");
    expect(shortHash(null)).toBe("");
  });
});
