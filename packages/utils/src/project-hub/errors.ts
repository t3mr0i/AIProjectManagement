/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TProjectHubApiError } from "@plane/types";

export type TProjectHubErrorKind =
  | "permission"
  | "disabled"
  | "not_found"
  | "conflict"
  | "validation"
  | "rate_limited"
  | "offline"
  | "unknown";

/** Normalize anything thrown by a request into the contract error envelope. */
export const toProjectHubApiError = (input: unknown): TProjectHubApiError => {
  if (input && typeof input === "object") {
    const obj = input as Record<string, unknown>;
    if (typeof obj.code === "string" && "status" in obj) {
      return {
        status: typeof obj.status === "number" ? obj.status : null,
        code: obj.code,
        error: typeof obj.error === "string" ? obj.error : "",
        detail: (obj.detail as Record<string, unknown> | undefined) ?? undefined,
      };
    }
  }
  return { status: null, code: "UNKNOWN", error: input instanceof Error ? input.message : "" };
};

/** Map an API error to the UI state that must be rendered (PRD §11.4). */
export const getProjectHubErrorKind = (error: TProjectHubApiError | null | undefined): TProjectHubErrorKind => {
  if (!error) return "unknown";
  if (error.code === "EXTENSION_DISABLED") return "disabled";
  if (error.code === "NETWORK_ERROR" || error.status === 0) return "offline";
  switch (error.status) {
    case 401:
    case 403:
      return "permission";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 422:
    case 400:
      return "validation";
    case 429:
      return "rate_limited";
    default:
      return error.status === null ? "offline" : "unknown";
  }
};

/** i18n key for a specific contract error code; falls back to the generic kind message. */
export const getProjectHubErrorMessageKey = (error: TProjectHubApiError | null | undefined): string => {
  const known = [
    "EXTENSION_DISABLED",
    "NO_PROFILE",
    "VERSION_CONFLICT",
    "IDEMPOTENCY_MISMATCH",
    "HUMAN_PRINCIPAL_REQUIRED",
    "REVISION_NOT_READY",
    "REVISION_STALE",
    "CLAIM_HELD",
    "STALE_FENCING_TOKEN",
    "LEASE_EXPIRED",
    "REVISION_NOT_APPROVED",
    "APPROVAL_REVOKED",
    "APPROVAL_EXPIRED",
    "NATIVE_SOURCE_CHANGED",
    "CLAIM_INVALID",
    "PROJECT_ARCHIVED",
    "HEAD_MISMATCH",
    "REVIEW_REQUIRED",
    "CAPABILITY_MISSING",
    "DEPENDENCY_CYCLE",
  ];
  if (error && known.includes(error.code)) return `project_hub.errors.code.${error.code}`;
  return `project_hub.errors.kind.${getProjectHubErrorKind(error)}`;
};

/** Extract the cycle path of a `DEPENDENCY_CYCLE` error for display. */
export const getDependencyCyclePath = (error: TProjectHubApiError | null | undefined): string[] => {
  const path = error?.detail?.path;
  return Array.isArray(path) ? path.map((p) => String(p)) : [];
};
