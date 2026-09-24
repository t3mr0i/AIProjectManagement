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
  owner_id?: string;
  token_prefix?: string;
  is_active: boolean;
  last_seen_at: string | null;
  created_at?: string;
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

export type TPackageClaim = {
  id: string;
  work_item_id?: string;
  repository_binding_id: string | null;
  repository_name?: string | null;
  exclusive: boolean;
  holder_id: string;
  runner_id: string | null;
  runner_name?: string | null;
  approval_id?: string | null;
  fencing_token: number;
  lease_expires_at: string;
  last_heartbeat_at: string | null;
  status: TClaimStatus;
  released_at?: string | null;
  created_at?: string;
};

export type TClaimCreate = {
  approval_id?: string;
  repository_binding_id?: string;
  exclusive?: boolean;
  lease_seconds?: number;
};
export type TClaimCreated = { id: string; fencing_token: number; lease_expires_at: string };

export type TRunStatus = "queued" | "claimed" | "running" | "waiting" | "failed" | "cancelled" | "finished";
export type TRunMode = "human" | "agent";

export type TPackageRun = {
  id: string;
  revision_id: string;
  revision_number?: number;
  approval_id: string;
  claim_id: string;
  runner_id: string | null;
  runner_name?: string | null;
  responsible_id: string;
  status: TRunStatus;
  mode: TRunMode;
  agent_adapter?: string;
  base_commits?: Record<string, string>;
  limits?: Record<string, unknown>;
  spend_minor?: number;
  started_at: string | null;
  finished_at: string | null;
  last_heartbeat_at: string | null;
  progress?: { summary?: string; percent?: number; question?: string; [key: string]: unknown };
  result?: Record<string, unknown>;
  cancel_requested_at?: string | null;
  pause_reason?: string;
  manifest_hash?: string;
  created_at?: string;
};

/** `GET P/work-items/{id}/runs` → `{results: [Run]}` (claims may be embedded by the server). */
export type TPackageRunList = { results: TPackageRun[]; claims?: TPackageClaim[] };

export type TRunCreate = { approval_id: string; claim_id: string; mode: TRunMode; agent_adapter?: string };
