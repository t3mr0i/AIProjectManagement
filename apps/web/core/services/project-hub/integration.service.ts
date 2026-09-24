/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TConnectionHealth,
  TExternalLink,
  TIntegrationConnection,
  TIntegrationConnectionCreate,
  TMergeRequestLink,
  TPackageDeliveryView,
  TPackageEvidence,
  TPackageReviewView,
  TProviderDeclaration,
  TRepositoryBinding,
  TReviewApproval,
  TReviewApprovalCreate,
  TSpecExport,
  TSpecImport,
  TSpecState,
  TSyncConflict,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Integrations, delivery, review, spec sync (API §4, §6 spec). */
export class ProjectHubIntegrationService extends ProjectHubBaseService {
  listProviders(workspaceSlug: string) {
    return this.getJson<TProviderDeclaration[]>(`${projectHubWorkspacePath(workspaceSlug)}/providers/`);
  }

  listConnections(workspaceSlug: string) {
    return this.getJson<TIntegrationConnection[]>(`${projectHubWorkspacePath(workspaceSlug)}/connections/`);
  }

  createConnection(workspaceSlug: string, data: TIntegrationConnectionCreate) {
    return this.postJson<TIntegrationConnection>(`${projectHubWorkspacePath(workspaceSlug)}/connections/`, data);
  }

  updateConnection(workspaceSlug: string, connectionId: string, data: Partial<TIntegrationConnection>) {
    return this.patchJson<TIntegrationConnection>(
      `${projectHubWorkspacePath(workspaceSlug)}/connections/${connectionId}/`,
      data
    );
  }

  disconnect(workspaceSlug: string, connectionId: string) {
    return this.deleteJson<void>(`${projectHubWorkspacePath(workspaceSlug)}/connections/${connectionId}/`);
  }

  getConnectionHealth(workspaceSlug: string, connectionId: string) {
    return this.getJson<TConnectionHealth>(
      `${projectHubWorkspacePath(workspaceSlug)}/connections/${connectionId}/health`
    );
  }

  /** 202 = accepted, not finished. */
  reconcile(workspaceSlug: string, connectionId: string) {
    return this.postJson<unknown>(`${projectHubWorkspacePath(workspaceSlug)}/connections/${connectionId}/reconcile`);
  }

  listRepositories(workspaceSlug: string, projectId: string) {
    return this.getJson<TRepositoryBinding[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/repositories/`);
  }

  private workItemPath(workspaceSlug: string, projectId: string, issueId: string) {
    return `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}`;
  }

  listExternalLinks(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TExternalLink[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/external-links`);
  }

  listMergeRequests(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TMergeRequestLink[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/merge-requests`);
  }

  listEvidence(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageEvidence[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/evidence`);
  }

  getReview(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageReviewView>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/review`);
  }

  /** Human only; the server rejects agent principals (INV-03). */
  createReviewApproval(workspaceSlug: string, projectId: string, issueId: string, data: TReviewApprovalCreate) {
    return this.postJson<TReviewApproval>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/reviews/${issueId}/approvals`,
      data
    );
  }

  /** Gate + provider merge; 409 `HEAD_MISMATCH` / `REVIEW_REQUIRED` / `CAPABILITY_MISSING`. */
  merge(workspaceSlug: string, projectId: string, linkId: string, expectedHeadSha: string) {
    return this.postJson<unknown>(`${projectHubProjectPath(workspaceSlug, projectId)}/merge-requests/${linkId}/merge`, {
      expected_head_sha: expectedHeadSha,
    });
  }

  getDelivery(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageDeliveryView>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/delivery`);
  }

  listSyncConflicts(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TSyncConflict[]>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/sync-conflicts`);
  }

  resolveSyncConflict(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    conflictId: string,
    resolution: "platform" | "external"
  ) {
    return this.postJson<TSyncConflict>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/sync-conflicts/${conflictId}/resolve`,
      { resolution }
    );
  }

  getSpec(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TSpecState>(`${this.workItemPath(workspaceSlug, projectId, issueId)}/spec`);
  }

  exportSpec(workspaceSlug: string, projectId: string, issueId: string, data: TSpecExport) {
    return this.postJson<{ content?: string; path?: string }>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/spec/export`,
      data
    );
  }

  importSpec(workspaceSlug: string, projectId: string, issueId: string, data: TSpecImport) {
    return this.postJson<{ revision_id?: string; conflict?: unknown }>(
      `${this.workItemPath(workspaceSlug, projectId, issueId)}/spec/import`,
      data
    );
  }
}
