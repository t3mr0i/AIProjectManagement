/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Project Hub (package-flow extension) — shared primitives.
 * Contract: docs/project-hub/API.md (v1.1.0). REST keys are snake_case.
 */

/** Separately granted business capabilities (PRD §5.2). Native roles are not equated with them. */
export type TProjectHubCapability =
  | "project.read"
  | "package.edit"
  | "package.approve_execution"
  | "run.start"
  | "run.cancel"
  | "review.approve_code"
  | "review.accept_outcome"
  | "merge.request"
  | "decision.publish"
  | "project.plan"
  | "integration.manage"
  | "workspace.admin";

export type TProjectHubPrincipalKind = "human" | "agent";

/** `GET W/capabilities/me/?project_id=` */
export type TProjectHubCapabilities = {
  capabilities: TProjectHubCapability[];
  principal_kind: TProjectHubPrincipalKind;
  extension_enabled: boolean;
};

/** Error envelope: `{"error": str, "code": str, "detail"?: {}}` (+ HTTP status added client side). */
export type TProjectHubApiError = {
  status: number | null;
  code: string;
  error: string;
  detail?: Record<string, unknown> | undefined;
};

/** Well known error codes of the contract. */
export type TProjectHubErrorCode =
  | "EXTENSION_DISABLED"
  | "NO_PROFILE"
  | "VERSION_CONFLICT"
  | "IDEMPOTENCY_MISMATCH"
  | "HUMAN_PRINCIPAL_REQUIRED"
  | "REVISION_NOT_READY"
  | "REVISION_STALE"
  | "CLAIM_HELD"
  | "STALE_FENCING_TOKEN"
  | "LEASE_EXPIRED"
  | "REVISION_NOT_APPROVED"
  | "APPROVAL_REVOKED"
  | "APPROVAL_EXPIRED"
  | "NATIVE_SOURCE_CHANGED"
  | "CLAIM_INVALID"
  | "PROJECT_ARCHIVED"
  | "HEAD_MISMATCH"
  | "REVIEW_REQUIRED"
  | "CAPABILITY_MISSING"
  | "DEPENDENCY_CYCLE";

/** `GET W/activation/` */
export type TProjectHubActivation = {
  workspace_enabled: boolean;
  projects: { project_id: string; is_enabled: boolean }[];
};

export type TProjectHubActivationUpdate = { is_enabled: boolean; reason: string };

export type TProjectHubCapabilityGrant = {
  id: string;
  member_id: string;
  capability: TProjectHubCapability;
  project_id?: string | null;
  granted_by?: string | null;
  created_at?: string;
};

export type TProjectHubAuditEntry = {
  id: string;
  action: string;
  actor_id?: string | null;
  actor_kind?: TProjectHubPrincipalKind | "system";
  project_id?: string | null;
  target?: Record<string, unknown>;
  reason?: string;
  created_at: string;
};

/** Trust classes of evidence (FR-R02). */
export type TProjectHubTrustClass = "local_self_report" | "runner_reported" | "provider_ci" | "human";
