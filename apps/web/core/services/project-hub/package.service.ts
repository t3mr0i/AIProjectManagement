/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TChangeRecord,
  TChangeRecordKind,
  TChangeRecordStatus,
  TExecutionApproval,
  TExecutionApprovalCreate,
  TPackageActivate,
  TPackageProfile,
  TPackageProfileUpdate,
  TPackageReadiness,
  TPackageRevision,
  TPackageRevisionCompare,
  TPackageRow,
  TPackageStatus,
  TPackageView,
  TProjectHubActivation,
  TProjectHubActivationUpdate,
  TProjectHubAuditEntry,
  TProjectHubCapabilities,
  TProjectHubCapability,
  TProjectHubCapabilityGrant,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Activation, capabilities, audit, packages, revisions, approvals (API §1–§2). */
export class ProjectHubPackageService extends ProjectHubBaseService {
  // ---- activation & capabilities (I01)
  getActivation(workspaceSlug: string) {
    return this.getJson<TProjectHubActivation>(`${projectHubWorkspacePath(workspaceSlug)}/activation/`);
  }

  setWorkspaceActivation(workspaceSlug: string, data: TProjectHubActivationUpdate) {
    return this.putJson<TProjectHubActivation>(`${projectHubWorkspacePath(workspaceSlug)}/activation/`, data);
  }

  setProjectActivation(workspaceSlug: string, projectId: string, data: TProjectHubActivationUpdate) {
    return this.putJson<unknown>(`${projectHubProjectPath(workspaceSlug, projectId)}/activation/`, data);
  }

  getMyCapabilities(workspaceSlug: string, projectId?: string) {
    return this.getJson<TProjectHubCapabilities>(
      `${projectHubWorkspacePath(workspaceSlug)}/capabilities/me/`,
      projectId ? { project_id: projectId } : undefined
    );
  }

  listCapabilityGrants(workspaceSlug: string) {
    return this.getJson<TProjectHubCapabilityGrant[]>(`${projectHubWorkspacePath(workspaceSlug)}/capability-grants/`);
  }

  createCapabilityGrant(
    workspaceSlug: string,
    data: { member_id: string; capability: TProjectHubCapability; project_id?: string }
  ) {
    return this.postJson<TProjectHubCapabilityGrant>(
      `${projectHubWorkspacePath(workspaceSlug)}/capability-grants/`,
      data
    );
  }

  revokeCapabilityGrant(workspaceSlug: string, grantId: string) {
    return this.deleteJson<void>(`${projectHubWorkspacePath(workspaceSlug)}/capability-grants/${grantId}/`);
  }

  listAudit(workspaceSlug: string, params?: { project_id?: string; action?: string }) {
    return this.getJson<TProjectHubAuditEntry[]>(`${projectHubWorkspacePath(workspaceSlug)}/audit/`, params);
  }

  // ---- packages (I02)
  listPackages(workspaceSlug: string, projectId: string, view: TPackageView = "all") {
    return this.getJson<TPackageRow[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/packages/`, { view });
  }

  private workItemPath(workspaceSlug: string, projectId: string, issueId: string) {
    return `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}`;
  }

  activateProfile(workspaceSlug: string, projectId: string, issueId: string, data: TPackageActivate = {}) {
    return this.postJson<TPackageProfile>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/profile`, data);
  }

  getProfile(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageProfile>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/profile`);
  }

  updateProfile(workspaceSlug: string, projectId: string, issueId: string, data: TPackageProfileUpdate) {
    return this.patchJson<TPackageProfile>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/profile`, data);
  }

  getReadiness(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageReadiness>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/readiness`);
  }

  listRevisions(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageRevision[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/revisions`);
  }

  createRevision(workspaceSlug: string, projectId: string, issueId: string) {
    return this.postJson<TPackageRevision>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/revisions`, {});
  }

  getRevision(workspaceSlug: string, projectId: string, issueId: string, revisionId: string) {
    return this.getJson<TPackageRevision>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/revisions/${revisionId}`
    );
  }

  compareRevisions(workspaceSlug: string, projectId: string, issueId: string, from: string, to: string) {
    return this.getJson<TPackageRevisionCompare>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/revisions/compare`,
      { from, to }
    );
  }

  listExecutionApprovals(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TExecutionApproval[]>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/execution-approvals`
    );
  }

  createExecutionApproval(workspaceSlug: string, projectId: string, issueId: string, data: TExecutionApprovalCreate) {
    return this.postJson<TExecutionApproval>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/execution-approvals`,
      data
    );
  }

  revokeExecutionApproval(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    approvalId: string,
    reason: string
  ) {
    return this.postJson<TExecutionApproval>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/execution-approvals/${approvalId}/revoke`,
      { reason }
    );
  }

  listChangeRecords(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TChangeRecord[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/change-records`);
  }

  createChangeRecord(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: { kind: TChangeRecordKind; title: string; description: string }
  ) {
    return this.postJson<TChangeRecord>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/change-records`, data);
  }

  updateChangeRecord(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    recordId: string,
    data: { status: TChangeRecordStatus }
  ) {
    return this.patchJson<TChangeRecord>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/change-records/${recordId}`,
      data
    );
  }

  getStatus(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageStatus>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/status`);
  }
}
