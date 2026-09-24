/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TExecutionApproval } from "@plane/types";

export type TApprovalValidity = { kind: "valid" | "revoked" | "invalid"; reason: string | null };

const VALID_STATES = new Set(["active", "valid", "approved"]);

/**
 * Display validity strictly from server fields: revoked → revoked; a non-valid server `state`
 * or `is_valid === false` → invalid (with reason); otherwise valid. Never inferred optimistically.
 */
export const getApprovalValidity = (
  approval: Pick<TExecutionApproval, "revoked_at" | "revoke_reason" | "state" | "is_valid" | "invalid_reason">
): TApprovalValidity => {
  if (approval.revoked_at || approval.state === "revoked")
    return { kind: "revoked", reason: approval.revoke_reason ?? null };
  if (approval.state && !VALID_STATES.has(approval.state))
    return { kind: "invalid", reason: approval.invalid_reason ?? approval.state };
  if (approval.is_valid === false) return { kind: "invalid", reason: approval.invalid_reason ?? null };
  return { kind: "valid", reason: null };
};

const CHECK_NAME = /^[a-z0-9][a-z0-9_.-]{0,63}$/;

/**
 * Parse "name: arg1 arg2" lines into check definitions (argv lists, never shell strings).
 * Returns `null` for the whole input when a line is malformed or a name repeats.
 */
export const parseCheckLines = (input: string): { name: string; command: string[] }[] | null => {
  const lines = input
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const names = new Set<string>();
  const checks: { name: string; command: string[] }[] = [];
  for (const line of lines) {
    const idx = line.indexOf(":");
    if (idx <= 0) return null;
    const name = line.slice(0, idx).trim();
    const command = line
      .slice(idx + 1)
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!CHECK_NAME.test(name) || names.has(name) || command.length === 0) return null;
    names.add(name);
    checks.push({ name, command });
  }
  return checks.length > 20 ? null : checks;
};
