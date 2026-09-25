/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getApprovalValidity, parseCheckLines } from "./approval";

describe("project-hub approval helpers", () => {
  it("derives validity only from the server state", () => {
    expect(getApprovalValidity({ revoked_at: null, revoke_reason: "", state: "valid" })).toEqual({
      kind: "valid",
      reason: null,
    });
    expect(
      getApprovalValidity({ revoked_at: "2026-09-24T00:00:00Z", revoke_reason: "scope", state: "revoked" })
    ).toEqual({
      kind: "revoked",
      reason: "scope",
    });
    expect(getApprovalValidity({ revoked_at: null, revoke_reason: "", state: "expired" })).toEqual({
      kind: "invalid",
      reason: "expired",
    });
    expect(getApprovalValidity({ revoked_at: null, revoke_reason: "" }).kind).toBe("invalid");
  });

  it("parses check lines into argv lists", () => {
    expect(parseCheckLines("unit: pnpm test\nlint: pnpm   check:lint")).toEqual([
      { name: "unit", command: ["pnpm", "test"] },
      { name: "lint", command: ["pnpm", "check:lint"] },
    ]);
    expect(parseCheckLines("")).toEqual([]);
    expect(parseCheckLines("Bad Name: x")).toBeNull();
    expect(parseCheckLines("unit:")).toBeNull();
    expect(parseCheckLines("unit: a\nunit: b")).toBeNull();
  });
});
