/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TProjectHubTrustClass } from "./common";
import type { TPackageDelivery, TPackageFlag, TPackageStatusRepository } from "./package";

/** Integrations, delivery, review, spec sync (API §4, §6). Shapes follow the Django serializers. */

export type TIntegrationProvider = "gitlab" | "jira" | "linear" | "azure_devops" | "generic_git" | "github";

export type TCapabilitySupport = "supported" | "partial" | "unsupported" | "requires_configuration";

/** Adapter capability declaration; `GET W/providers/` → `{providers: [...]}`. */
export type TProviderDeclaration = {
  provider: TIntegrationProvider;
  display_name: string;
  kind: "git" | "tracker" | string;
  capabilities: Record<string, TCapabilitySupport>;
  editions: string[];
  instance_types: string[];
  min_requirements: string;
  auth_methods: string[];
  webhook_auth: string;
  rate_limits: string;
  event_types: string[];
  field_mapping: Record<string, unknown>;
  notes: string[];
};

export type TConnectionStatus = "active" | "degraded" | "offline" | "disabled";

export type TIntegrationConnection = {
  id: string;
  workspace_id: string;
  provider: TIntegrationProvider;
  instance_url: string;
  instance_type: string;
  edition: string;
  display_name: string;
  status: TConnectionStatus;
  capabilities: Record<string, TCapabilitySupport>;
  webhook_secret_configured: boolean;
  credential_configured: boolean;
  last_successful_sync_at: string | null;
  last_error: string;
  backlog_count: number;
  field_ownership: Record<string, "platform" | "external" | string>;
  webhook_path: string;
  created_at: string | null;
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
  connection_id: string;
  provider: TIntegrationProvider;
  status: TConnectionStatus | "stale";
  last_successful_sync_at: string | null;
  backlog_count: number;
  affected_capabilities: string[];
  last_error: string;
  /** false when degraded/offline/stale: the UI must not present data as live. */
  live: boolean;
  statement?: string;
};

export type TRepositoryBinding = {
  id: string;
  project_id: string;
  connection_id: string;
  provider: TIntegrationProvider;
  instance_url: string;
  external_id: string;
  path_with_namespace: string;
  default_branch: string;
  branch_rules: Record<string, unknown>;
  capabilities: Record<string, TCapabilitySupport>;
  role: string;
  is_active: boolean;
  observed_commit: string;
};

export type TExternalLink = {
  id: string;
  work_item_id: string;
  connection_id: string;
  provider: TIntegrationProvider;
  object_type: string;
  external_id: string;
  external_key: string;
  url: string;
  represents_package: boolean;
  field_ownership: Record<string, string>;
  observed_fields: Record<string, unknown>;
  last_synced_at: string | null;
  sync_state: "ok" | "conflict" | "stale" | "disconnected";
};

export type TMergeRequestState = "open" | "merged" | "closed";

/** A commit message is a claim, never proof (J07). */
export type TCommitClaim = { sha: string; message: string; status: "claimed"; merge_request_id?: string };

export type TMergeRequestLink = {
  id: string;
  binding_id: string;
  repository: string;
  external_id: string;
  title: string;
  url: string;
  source_branch: string;
  target_branch: string;
  head_sha: string;
  target_sha: string;
  state: TMergeRequestState;
  merged_commit_sha: string;
  merge_method: string;
  pending_merge: Record<string, unknown> | null;
  commits: TCommitClaim[];
  last_event_at: string | null;
};

export type TEvidenceResult = "passed" | "failed" | "not_run" | "unknown";

export type TPackageEvidence = {
  id: string;
  kind: string;
  name: string;
  source: string;
  trust: TProjectHubTrustClass;
  result: TEvidenceResult;
  binding_id: string | null;
  commit_sha: string;
  artifact_ref: string;
  criterion_ids: string[];
  occurred_at: string;
  url: string;
  /** Review view only: whether this trust class may prove the criterion. */
  accepted?: boolean;
};

export type TCriterionEvidenceState = "proven" | "failed" | "not_proven";

export type TReviewCriterion = {
  id: string;
  statement: string;
  verification: string;
  required: boolean;
  /** `trusted_ci` | `human` | `runner` | `any` */
  required_trust: string;
  state: TCriterionEvidenceState;
  reason: string;
  evidence: TPackageEvidence[];
};

export type TReviewKind = "code" | "outcome";
export type TReviewDecision = "approved" | "changes_requested";
export type TReviewValidity = "valid" | "changes_requested" | "invalidated" | "stale_revision" | "stale_head";

export type TReviewApproval = {
  id: string;
  kind: TReviewKind;
  decision: TReviewDecision;
  merge_request_id: string | null;
  head_sha: string;
  target_sha: string;
  revision_id: string;
  policy_version: string;
  approved_by: string;
  created_at: string;
  valid: boolean;
  validity: TReviewValidity;
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

export type TReviewOpenPoint =
  | { kind: "criterion_not_proven"; criterion_id: string; state: TCriterionEvidenceState; reason: string }
  | { kind: "code_review_required"; merge_request_id: string; head_sha: string; invalidated: boolean }
  | { kind: "outcome_acceptance_missing" }
  | { kind: "no_approved_revision" }
  | { kind: "revision_changed_since_approval" }
  | { kind: "open_question"; id: string; title: string };

export type TOfflineIntegration = {
  connection_id: string;
  provider: TIntegrationProvider;
  status: TConnectionStatus | "stale";
  last_successful_sync_at: string | null;
};

/** Delivery projection (`delivery_summary`), embedded in review and delivery views. */
export type TDeliverySummary = {
  delivery: TPackageDelivery;
  repositories: TPackageStatusRepository[];
  flags: TPackageFlag[];
  integrations: TOfflineIntegration[];
  last_known_at: string | null;
  visibility: "known_provider_states_only";
  /** Always `unknown`: local/uncommitted work is never inferred (AC32). */
  local_state: "unknown";
};

/** `GET P/work-items/{id}/review` */
export type TPackageReviewView = {
  work_item_id: string;
  revision: {
    id: string;
    number: number;
    title: string;
    intent: string;
    outcome: string;
    content_hash: string;
  } | null;
  change_summary: { merge_requests: number; commits: number; links: string[]; note: string };
  criteria: TReviewCriterion[];
  merge_requests: TMergeRequestLink[];
  approvals: TReviewApproval[];
  claims: TCommitClaim[];
  claims_note: string;
  open_points: TReviewOpenPoint[];
  delivery: TDeliverySummary;
};

export type TMergeRequestMerge = { expected_head_sha: string; squash?: boolean };

export type TDeliveryStage = "integrated" | "artifact_built" | "deployed" | "released" | "rolled_back";

export type TDeliveryEntry = {
  id: string;
  binding_id: string | null;
  stage: TDeliveryStage;
  commit_sha: string;
  artifact_ref: string;
  environment: string;
  source: string;
  trust: string;
  occurred_at: string;
  /** id of the delivery this one reverts (rollback history) */
  reverts: string | null;
  sources: unknown[];
};

/** `GET P/work-items/{id}/delivery` = delivery summary + append-only history (incl. rollbacks). */
export type TPackageDeliveryView = TDeliverySummary & { history: TDeliveryEntry[] };

export type TSyncConflict = {
  id: string;
  work_item_id: string;
  link_id: string | null;
  field: string;
  platform: { value: unknown; changed_at: string | null };
  external: { value: unknown; changed_at: string | null; source: TIntegrationProvider | null };
  status: "open" | "resolved";
  resolution: "" | TSyncConflictResolution;
};

/** Body of `POST .../sync-conflicts/{id}/resolve`: `{resolution}`. */
export type TSyncConflictResolution = "keep_platform" | "take_external";

export type TSpecSyncStateValue = "clean" | "ahead" | "behind" | "conflict";

export type TSpecConflictBlock = {
  block_id: string;
  file: string;
  kind: string;
  base: string | null;
  platform: string | null;
  git: string | null;
};

export type TSpecSyncState = {
  id: string | null;
  work_item_id: string;
  repository_binding_id: string | null;
  spec_path: string;
  state: TSpecSyncStateValue;
  base_commit: string;
  published_commit: string;
  published_revision_id: string | null;
  conflict: { commit?: string; blocks?: TSpecConflictBlock[]; resolutions?: Record<string, unknown> };
  updated_at: string | null;
};

/** `GET P/work-items/{id}/spec` */
export type TSpecState = {
  work_item_id: string;
  working_revision_id: string | null;
  approved_revision_id: string | null;
  states: TSpecSyncState[];
};

export type TSpecExport = { repository_binding_id: string; expected_base_commit: string; revision_id?: string };
export type TSpecImport = { content: string; commit: string; repository_binding_id?: string };
