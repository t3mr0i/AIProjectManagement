/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import {
  getDependencyCyclePath,
  getProjectHubErrorKind,
  getProjectHubErrorMessageKey,
  toProjectHubApiError,
} from "./errors";

describe("project-hub error helpers", () => {
  it("maps statuses and codes to UI states", () => {
    expect(getProjectHubErrorKind({ status: 403, code: "EXTENSION_DISABLED", error: "" })).toBe("disabled");
    expect(getProjectHubErrorKind({ status: 403, code: "FORBIDDEN", error: "" })).toBe("permission");
    expect(getProjectHubErrorKind({ status: 409, code: "VERSION_CONFLICT", error: "" })).toBe("conflict");
    expect(getProjectHubErrorKind({ status: null, code: "NETWORK_ERROR", error: "" })).toBe("offline");
    expect(getProjectHubErrorKind({ status: 404, code: "NO_PROFILE", error: "" })).toBe("not_found");
    expect(getProjectHubErrorKind({ status: 500, code: "X", error: "" })).toBe("unknown");
  });

  it("prefers specific code messages", () => {
    expect(getProjectHubErrorMessageKey({ status: 409, code: "HEAD_MISMATCH", error: "" })).toBe(
      "project_hub.errors.code.HEAD_MISMATCH"
    );
    expect(getProjectHubErrorMessageKey({ status: 409, code: "OTHER", error: "" })).toBe(
      "project_hub.errors.kind.conflict"
    );
  });

  it("normalizes unknown throwables and reads cycle paths", () => {
    expect(toProjectHubApiError(new Error("boom"))).toEqual({ status: null, code: "UNKNOWN", error: "boom" });
    expect(
      getDependencyCyclePath({ status: 422, code: "DEPENDENCY_CYCLE", error: "", detail: { path: ["a", "b", "a"] } })
    ).toEqual(["a", "b", "a"]);
    expect(getDependencyCyclePath(null)).toEqual([]);
  });
});
