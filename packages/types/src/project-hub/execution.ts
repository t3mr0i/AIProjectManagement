/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Runner, claims, runs (API §3). */

export type TRunnerKind = "local" | "customer" | "managed";

export type TRunnerProfile = {
  id: string;
  name: string;
  kind: TRunnerKind;
  owner_id: string;
  token_prefix: string;
  is_active: boolean;
  last_seen_at: string | null;
  created_at: string | null;
};

/** `POST W/runners/` → token is returned exactly once. */
export type TRunnerRegistration = {
  id: string;
  token: string;
  name?: string;
  kind?: TRunnerKind;
  token_prefix?: string;
};

export type TClaimStatus = "active" | "released" | "expired" | "revoked";

/** `claim_data` (+ web projection fields from `GET P/work-items/{id}/claims`). */
export type TPackageClaim = {
  id: string;
  work_item_id: string;
  repository_binding_id: string | null;
  exclusive: boolean;
  holder_id: string;
  runner_id: string | null;
  approval_id: string | null;
  fencing_token: number;
  lease_expires_at: string;
  status: TClaimStatus;
  last_heartbeat_at?: string | null;
  released_at?: string | null;
  created_at?: string | null;
  runner_name?: string | null;
  repository_name?: string | null;
};

export type TPackageClaimList = { results: TPackageClaim[] };

export type TClaimCreate = {
  approval_id?: string;
  repository_binding_id?: string;
  exclusive?: boolean;
  lease_seconds?: number;
};
export type TClaimCreated = TPackageClaim;

export type TRunStatus = "queued" | "claimed" | "running" | "waiting" | "failed" | "cancelled" | "finished";
export type TRunMode = "human" | "agent";

export type TPackageRun = {
  id: string;
  work_item_id: string;
  revision_id: string;
  approval_id: string;
  claim_id: string;
  runner_id: string | null;
  responsible_id: string;
  status: TRunStatus;
  mode: TRunMode;
  agent_adapter: string;
  base_commits: Record<string, string>;
  limits: Record<string, unknown>;
  spend_minor: number;
  started_at: string | null;
  finished_at: string | null;
  last_heartbeat_at: string | null;
  progress: { summary?: string; percent?: number; question?: string; [key: string]: unknown };
  result: Record<string, unknown>;
  cancel_requested_at: string | null;
  pause_reason: string;
  manifest_hash: string;
};

/** `GET P/work-items/{id}/runs` → `{results: [Run]}`. */
export type TPackageRunList = { results: TPackageRun[] };

export type TRunCreate = { approval_id: string; claim_id: string; mode: TRunMode; agent_adapter?: string };
