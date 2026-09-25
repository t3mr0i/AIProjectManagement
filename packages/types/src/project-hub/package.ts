/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Packages, revisions, approvals (API §2). `work_item_id` is always the native Plane issue id. */

export type TPackageProfileKind = "light" | "deep";
export type TPackageType = "code" | "analysis" | "design" | "decision";
export type TPackageCompletionCriterion = "delivery_and_acceptance" | "accepted_deliverable";

export type TPackageLifecycle = "draft" | "ready" | "active" | "review" | "completed" | "cancelled" | "archived";
export type TPackagePhase = "drafts" | "ready" | "build" | "review" | "ship" | "done";
export type TPackageDelivery =
  | "not_integrated"
  | "partially_integrated"
  | "integrated"
  | "deployed"
  | "released"
  | "rolled_back"
  | "unknown";
export type TPackageFlag =
  | "blocked"
  | "scope_changed"
  | "sync_conflict"
  | "stale_evidence"
  | "integration_offline"
  | "native_done_without_delivery"
  | "native_done_without_delivery_evidence"
  | "merge_pending_confirmation";

/**
 * Criterion `verification` decides which evidence trust class can prove it (server `required_trust`):
 * `ci`/`ci:<name>`/`test` → provider CI, `manual`/`review` → human or CI, `runner` → runner or CI,
 * `any`/`local` → any class. Unknown values conservatively require CI.
 */
export type TPackageCriterion = { id: string; text: string; verification?: string; required?: boolean };

/**
 * Scope object. Readiness requires at least one `in_scope` item; `touches` containing
 * permissions/auth/security adds the security review policy.
 */
export type TPackageScope = {
  in_scope?: string[];
  touches?: string[];
  diagram_notes?: unknown[];
  [key: string]: unknown;
};

/** Deep profiles require `risk.notes` for readiness. */
export type TPackageRisk = {
  notes?: string;
  level?: "low" | "medium" | "high";
  rollback?: string;
  [key: string]: unknown;
};

export type TPackageNativeSnapshot = {
  name: string;
  priority: string | null;
  state_group: string | null;
  state_name: string | null;
  is_draft: boolean;
  sequence_id: number | null;
  project_identifier: string | null;
};

export type TPackageProfile = {
  id: string;
  work_item_id: string;
  project_id: string;
  workspace_id: string;
  profile_kind: TPackageProfileKind;
  package_type: TPackageType;
  completion_criterion: TPackageCompletionCriterion;
  intent: string;
  outcome: string;
  non_goals: string[];
  scope: TPackageScope;
  criteria: TPackageCriterion[];
  risk: TPackageRisk;
  working_revision_id: string | null;
  approved_revision_id: string | null;
  version: number;
  flags: TPackageFlag[];
  updated_at: string | null;
  native: TPackageNativeSnapshot;
};

/** Editable working-draft fields (PATCH profile). `expected_version` guards concurrent edits. */
export type TPackageProfileUpdate = Partial<
  Pick<
    TPackageProfile,
    | "intent"
    | "outcome"
    | "non_goals"
    | "scope"
    | "criteria"
    | "risk"
    | "profile_kind"
    | "package_type"
    | "completion_criterion"
  >
> & { expected_version: number };

export type TPackageActivate = { profile_kind?: TPackageProfileKind; package_type?: TPackageType };

export type TPackageReadiness = {
  ready: boolean;
  missing: { field: string; message: string }[];
  policies: { id: string; message: string }[];
  profile_kind: TPackageProfileKind;
};

export type TPackageRevision = {
  id: string;
  work_item_id: string;
  number: number;
  title: string;
  intent: string;
  outcome: string;
  non_goals: string[];
  scope: TPackageScope;
  criteria: TPackageCriterion[];
  decisions: unknown[];
  artifacts: unknown[];
  profile_kind: TPackageProfileKind;
  package_type: TPackageType;
  source_versions: Record<string, unknown>;
  content_hash: string;
  created_by: string | null;
  created_at: string;
  is_approved: boolean;
  is_stale: boolean;
  contract?: Record<string, unknown>;
};

export type TPackageRevisionFieldDiff = { field: string; from: unknown; to: unknown };

type TRevisionRef = { id: string; number: number; content_hash: string };

/** `GET revisions/compare?from=&to=` (ids or numbers) — field-level diff plus criteria diff. */
export type TPackageRevisionCompare = {
  from: TRevisionRef;
  to: TRevisionRef;
  changes: TPackageRevisionFieldDiff[];
  criteria: {
    added: TPackageCriterion[];
    removed: TPackageCriterion[];
    changed: { id: string; from: TPackageCriterion; to: TPackageCriterion }[];
  };
};

export type TExecutionRepositoryScope = {
  binding_id: string;
  base_commit: string;
  target_branch: string;
  allowed_paths: string[];
};

export type TExecutionLimits = { max_seconds?: number; max_spend_minor?: number; currency?: string };

/** Approved check command (argv list, never a shell string). */
export type TExecutionCheck = { name: string; command: string[]; trusted?: boolean };

export type TExecutionApprovalCreate = {
  revision_id: string;
  repository_scope: TExecutionRepositoryScope[];
  allowed_actions: string[];
  runner_profile_id?: string;
  limits: TExecutionLimits;
  /** max 20, `name` slug `[a-z0-9][a-z0-9_.-]{0,63}`, unique */
  checks?: TExecutionCheck[];
  expires_in_hours?: number;
};

/** Server-computed approval state; the UI never derives validity on its own. */
export type TExecutionApprovalState = "valid" | "revoked" | "expired";

export type TExecutionApproval = {
  id: string;
  work_item_id: string;
  revision_id: string;
  revision_hash: string;
  approved_by: string;
  approved_at: string;
  expires_at: string;
  policy_version: string;
  repository_scope: TExecutionRepositoryScope[];
  allowed_actions: string[];
  runner_profile_id: string | null;
  limits: TExecutionLimits;
  checks: TExecutionCheck[];
  state: TExecutionApprovalState;
  revoked_at: string | null;
  revoke_reason: string;
  /** execution-authorization 1.1.0 JSON */
  contract?: Record<string, unknown>;
};

export type TChangeRecordKind = "technical_task" | "change" | "openspec_change";
export type TChangeRecordStatus = "open" | "done" | "dropped";

export type TChangeRecord = {
  id: string;
  work_item_id: string;
  created_by: string | null;
  kind: TChangeRecordKind;
  title: string;
  description: string;
  status: TChangeRecordStatus;
  revision_id?: string | null;
  links?: { type?: string; url?: string; label?: string }[];
  created_at?: string;
  updated_at?: string;
};

export type TDeliveryEnvironment = {
  name: string;
  state: "deployed" | "rolled_back";
  commit_sha: string;
  occurred_at: string;
};

/** Per repository delivery projection (server `_binding_state`). */
export type TPackageStatusRepository = {
  binding_id: string;
  name: string;
  role: string;
  provider: string;
  instance_url: string;
  delivery: TPackageDelivery;
  merge_request_state: "open" | "merged" | "closed" | null;
  integrated_commit_sha: string | null;
  environments: TDeliveryEnvironment[];
  pending_merge: boolean;
};

export type TPackageStatus = {
  work_item_id: string;
  is_package: boolean;
  lifecycle: TPackageLifecycle | null;
  phase: TPackagePhase | null;
  delivery: TPackageDelivery;
  flags: TPackageFlag[];
  native_state_group: string | null;
  repositories: TPackageStatusRepository[];
  explanations: string[];
  approved_revision_id?: string | null;
  working_revision_id?: string | null;
};

/** Row of `GET P/packages/?view=` → `{results, count, view}`. Rows always have a profile. */
export type TPackageRow = TPackageStatus & {
  phase: TPackagePhase;
  name: string;
  sequence_id: number | null;
  project_id: string;
  project_identifier: string | null;
  priority: string | null;
  is_draft: boolean;
  assignee_ids: string[];
  updated_at: string | null;
  /** Runs waiting for an answer (`pause_reason = question`). */
  open_questions: number;
};

export type TPackageList = { results: TPackageRow[]; count: number; view: string };

export type TPackageView = "drafts" | "ready" | "build" | "review" | "ship" | "done" | "all";
