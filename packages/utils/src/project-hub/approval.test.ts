/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getApprovalValidity, parseCheckLines } from "./approval";

describe("project-hub approval helpers", () => {
  it("derives validity only from server fields", () => {
    expect(getApprovalValidity({ revoked_at: null })).toEqual({ kind: "valid", reason: null });
    expect(getApprovalValidity({ revoked_at: "2026-09-24T00:00:00Z", revoke_reason: "scope" })).toEqual({
      kind: "revoked",
      reason: "scope",
    });
    expect(getApprovalValidity({ revoked_at: null, state: "expired" })).toEqual({ kind: "invalid", reason: "expired" });
    expect(getApprovalValidity({ revoked_at: null, state: "active" }).kind).toBe("valid");
    expect(getApprovalValidity({ revoked_at: null, is_valid: false, invalid_reason: "stale" })).toEqual({
      kind: "invalid",
      reason: "stale",
    });
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
