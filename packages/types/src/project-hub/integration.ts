/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TProjectHubTrustClass } from "./common";
import type { TExecutionApproval, TPackageCriterion, TPackageRevision } from "./package";

/** Integrations, delivery, review (API §4). */

export type TIntegrationProvider = "gitlab" | "jira" | "linear" | "azure_devops" | "generic_git" | "github";

export type TCapabilitySupport = "supported" | "partial" | "unsupported" | "unknown";

/** Adapter capability declaration (`GET W/providers/`). */
export type TProviderDeclaration = {
  provider: TIntegrationProvider;
  display_name?: string;
  editions?: string[];
  capabilities: Record<string, TCapabilitySupport | boolean | string>;
  notes?: string[];
};

export type TConnectionStatus = "active" | "degraded" | "offline" | "disabled";

export type TIntegrationConnection = {
  id: string;
  provider: TIntegrationProvider;
  instance_url: string;
  instance_type: string;
  edition: string;
  display_name: string;
  status: TConnectionStatus;
  capabilities?: Record<string, TCapabilitySupport | boolean | string>;
  field_ownership?: Record<string, "platform" | "external" | string>;
  last_successful_sync_at?: string | null;
  backlog_count?: number;
  last_error?: string;
  created_at?: string;
};

export type TIntegrationConnectionCreate = {
  provider: TIntegrationProvider;
  instance_url: string;
  instance_type: string;
  edition: string;
  display_name: string;
  webhook_secret?: string;
};

export type TConnectionHealth = {
  status: TConnectionStatus;
  last_successful_sync_at: string | null;
  backlog_count: number;
  affected_capabilities: string[];
  last_error: string | null;
};

export type TRepositoryBinding = {
  id: string;
  connection_id: string;
  external_id: string;
  path_with_namespace: string;
  default_branch: string;
  role: string;
  branch_rules?: Record<string, unknown>;
  is_active?: boolean;
  observed_commit?: string;
};

export type TExternalLink = {
  id: string;
  connection_id: string;
  object_type: string;
  external_id: string;
  external_key: string;
  url: string;
  represents_package: boolean;
  field_ownership: Record<string, string>;
  last_synced_at?: string | null;
  sync_state?: "ok" | "conflict" | "stale" | "disconnected";
};

export type TMergeRequestState = "open" | "merged" | "closed";

export type TMergeRequestLink = {
  id: string;
  repository_binding_id: string;
  repository_name?: string;
  external_id: string;
  title: string;
  url: string;
  source_branch: string;
  target_branch: string;
  head_sha: string;
  target_sha: string;
  state: TMergeRequestState;
  merged_commit_sha?: string;
  last_event_at?: string | null;
};

export type TEvidenceResult = "passed" | "failed" | "not_run" | "unknown";

export type TPackageEvidence = {
  id: string;
  kind: string;
  name: string;
  source: string;
  trust: TProjectHubTrustClass | "commit_message";
  result: TEvidenceResult;
  repository_binding_id?: string | null;
  commit_sha: string;
  artifact_ref?: string;
  criterion_ids: string[];
  run_id?: string | null;
  occurred_at: string;
  url?: string;
  /** Set by the server when the evidence was checked against an older commit than the current head. */
  is_stale?: boolean;
  checked_commit?: string;
  current_commit?: string;
};

export type TCriterionEvidenceState = "proven" | "failed" | "not_proven";

export type TReviewCriterion = TPackageCriterion & {
  state: TCriterionEvidenceState;
  evidence: TPackageEvidence[];
  explanation?: string;
};

export type TReviewKind = "code" | "outcome";
export type TReviewDecision = "approved" | "changes_requested";

export type TReviewApproval = {
  id: string;
  kind: TReviewKind;
  revision_id: string;
  merge_request_id: string | null;
  head_sha: string;
  target_sha?: string;
  approved_by: string;
  decision: TReviewDecision;
  comment: string;
  created_at: string;
  invalidated_at: string | null;
  invalidated_reason: string;
};

export type TReviewApprovalCreate = {
  kind: TReviewKind;
  merge_request_id?: string;
  head_sha?: string;
  decision: TReviewDecision;
  comment: string;
};

/** `GET P/work-items/{id}/review` */
export type TPackageReviewView = {
  intent: Pick<
    TPackageRevision,
    "id" | "number" | "content_hash" | "intent" | "outcome" | "non_goals" | "scope"
  > | null;
  change_summary: { summary?: string; commits?: { sha: string; message: string }[]; files_changed?: number } | null;
  criteria: TReviewCriterion[];
  open_points: string[];
  approvals: TReviewApproval[];
  merge_requests?: TMergeRequestLink[];
  execution_approval?: TExecutionApproval | null;
};

export type TMergeRequestMerge = { expected_head_sha: string };

export type TDeliveryStage = "integrated" | "artifact_built" | "deployed" | "released" | "rolled_back";

export type TDeliveryEntry = {
  id: string;
  repository_binding_id: string | null;
  repository_name?: string | null;
  stage: TDeliveryStage;
  commit_sha: string;
  artifact_ref: string;
  environment: string;
  source: string;
  trust: string;
  occurred_at: string;
  reverts_id?: string | null;
};

/** `GET P/work-items/{id}/delivery` — per repo/environment chain + history. */
export type TPackageDeliveryView = {
  chains: {
    repository_binding_id: string | null;
    repository_name: string | null;
    environment: string | null;
    current_stage: TDeliveryStage | "unknown";
    entries: TDeliveryEntry[];
  }[];
  history: TDeliveryEntry[];
  aggregate?: { delivery: string; rule?: string };
};

export type TSyncConflict = {
  id: string;
  link_id: string | null;
  field: string;
  platform_value: unknown;
  external_value: unknown;
  platform_changed_at: string | null;
  external_changed_at: string | null;
  status: "open" | "resolved";
  resolution?: string;
};

export type TSpecSyncStateValue = "clean" | "ahead" | "behind" | "conflict";

export type TSpecState = {
  items: {
    id?: string;
    repository_binding_id: string | null;
    repository_name?: string | null;
    spec_path: string;
    base_commit: string;
    published_revision_id: string | null;
    published_revision_number?: number | null;
    published_commit: string;
    state: TSpecSyncStateValue;
    conflict?: { base?: string; platform?: string; git?: string; fields?: string[] } | null;
  }[];
};

export type TSpecExport = { repository_binding_id: string; expected_base_commit: string };
export type TSpecImport = { content: string; commit: string };
