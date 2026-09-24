/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TCriterionEvidenceState, TPackageEvidence } from "@plane/types";

type TEvidenceLike = Pick<TPackageEvidence, "result" | "trust"> & { is_stale?: boolean | undefined };

/**
 * Trust classes that may prove a criterion. A claim in a commit message is never a proof
 * (J07), and neither is a local self report on its own.
 */
const PROVING_TRUST = new Set<string>(["runner_reported", "provider_ci", "human"]);

export const canEvidenceProve = (evidence: TEvidenceLike): boolean =>
  PROVING_TRUST.has(evidence.trust) && !evidence.is_stale;

/**
 * Derive the display state of a criterion from its evidence when the server does not send one.
 * - any fresh failed evidence → `failed`
 * - at least one fresh passed evidence from a proving trust class → `proven`
 * - otherwise → `not_proven` (commit-message claims, self reports, stale or unknown results)
 */
export const deriveCriterionState = (evidence: TEvidenceLike[]): TCriterionEvidenceState => {
  if (evidence.some((e) => e.result === "failed" && !e.is_stale)) return "failed";
  if (evidence.some((e) => e.result === "passed" && canEvidenceProve(e))) return "proven";
  return "not_proven";
};

/**
 * Guard the server state as well: never display `proven` if every supporting item is a commit
 * message claim or self report. Returns the safe state.
 */
export const safeCriterionState = (
  serverState: TCriterionEvidenceState | undefined,
  evidence: TEvidenceLike[]
): TCriterionEvidenceState => {
  const derived = deriveCriterionState(evidence);
  if (serverState === "proven" && derived !== "proven") return "not_proven";
  return serverState ?? derived;
};

/** i18n key of an evidence trust class label. */
export const getTrustLabelKey = (trust: string): string => {
  const known = ["local_self_report", "runner_reported", "provider_ci", "human", "commit_message"];
  return known.includes(trust) ? `project_hub.trust.${trust}` : "project_hub.trust.unknown";
};

/** Short commit/hash display (first 8 chars), empty-safe. */
export const shortHash = (value: string | null | undefined, length = 8): string =>
  value ? value.slice(0, length) : "";
