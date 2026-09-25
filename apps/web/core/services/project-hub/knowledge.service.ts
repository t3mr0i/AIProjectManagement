/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TPHActivityEntry,
  TPHActivityFeed,
  TPHDiagramCreate,
  TPHDiagramDetail,
  TPHDiagramDocument,
  TPHDiagramProposalAccepted,
  TPHDiagramSemantic,
  TPHDiagramLayout,
  TPHDiagramUpdateResult,
  TPHOverview,
  TPHProposal,
  TPHRetentionPolicy,
  TPHSearchResult,
  TPHUploadCandidate,
  TPHUploadRecord,
  TPHUploadRegister,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Activity, overview, search, uploads, diagrams, retention (API §5). */
export class ProjectHubKnowledgeService extends ProjectHubBaseService {
  /** `since` = `last_visit` | `today` | ISO. Grouped by package & day, technical events compacted. */
  getActivity(workspaceSlug: string, projectId: string, params: { since: string; until?: string; issue_id?: string }) {
    return this.getJson<TPHActivityFeed>(`${projectHubProjectPath(workspaceSlug, projectId)}/activity/`, params);
  }

  /** Expand compacted entries to their raw events. */
  getRawEvents(workspaceSlug: string, projectId: string, ids: string[]) {
    return this.getList<TPHActivityEntry>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/activity/`,
      { ids: ids.join(",") },
      "raw"
    );
  }

  setVisitMarker(workspaceSlug: string, projectId: string) {
    return this.postJson<{ last_visited_at: string; previous_visited_at: string | null }>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/activity/visit`
    );
  }

  getOverview(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHOverview>(`${projectHubProjectPath(workspaceSlug, projectId)}/overview`);
  }

  search(workspaceSlug: string, q: string, types?: string[]) {
    return this.getList<TPHSearchResult>(`${projectHubWorkspacePath(workspaceSlug)}/search/`, {
      q,
      ...(types?.length ? { types: types.join(",") } : {}),
    });
  }

  listUploads(workspaceSlug: string, projectId: string, params?: { issue_id?: string; scan_status?: string }) {
    return this.getList<TPHUploadRecord>(`${projectHubProjectPath(workspaceSlug, projectId)}/uploads/`, params);
  }

  /** Native FileAssets (attachments …) of the project that are not registered yet. */
  listUploadCandidates(workspaceSlug: string, projectId: string, params?: { issue_id?: string }) {
    return this.getList<TPHUploadCandidate>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/uploads/candidates`,
      params
    );
  }

  /** Scan + format classification of an existing native FileAsset (no second file store). */
  registerUpload(workspaceSlug: string, projectId: string, assetId: string, data: TPHUploadRegister = {}) {
    return this.postJson<TPHUploadRecord>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/uploads/${assetId}/register`,
      data
    );
  }

  listDiagrams(workspaceSlug: string, projectId: string, issueId?: string) {
    return this.getList<TPHDiagramDocument>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/`,
      issueId ? { issue_id: issueId } : undefined
    );
  }

  getDiagram(workspaceSlug: string, projectId: string, diagramId: string) {
    return this.getJson<TPHDiagramDetail>(`${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/${diagramId}/`);
  }

  createDiagram(workspaceSlug: string, projectId: string, data: TPHDiagramCreate) {
    return this.postJson<TPHDiagramDocument>(`${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/`, data);
  }

  /** 409 `VERSION_CONFLICT` when `expected_version` is outdated. */
  updateDiagram(
    workspaceSlug: string,
    projectId: string,
    diagramId: string,
    data: { semantic: TPHDiagramSemantic; layout: TPHDiagramLayout; expected_version: number }
  ) {
    return this.putJson<TPHDiagramUpdateResult>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/${diagramId}/`,
      data
    );
  }

  acceptDiagramProposal(
    workspaceSlug: string,
    projectId: string,
    diagramId: string,
    proposalId: string,
    criteriaEdgeIds?: string[]
  ) {
    return this.postJson<TPHDiagramProposalAccepted>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/${diagramId}/proposals/${proposalId}/accept`,
      criteriaEdgeIds ? { criteria_edge_ids: criteriaEdgeIds } : {}
    );
  }

  rejectDiagramProposal(workspaceSlug: string, projectId: string, diagramId: string, proposalId: string) {
    return this.postJson<{ proposal: TPHProposal }>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/${diagramId}/proposals/${proposalId}/reject`
    );
  }

  getRetention(workspaceSlug: string) {
    return this.getList<TPHRetentionPolicy>(
      `${projectHubWorkspacePath(workspaceSlug)}/retention/`,
      undefined,
      "policies"
    );
  }

  updateRetention(workspaceSlug: string, policies: TPHRetentionPolicy[]) {
    return this.putJson<{ policies: TPHRetentionPolicy[] }>(`${projectHubWorkspacePath(workspaceSlug)}/retention/`, {
      policies,
    });
  }

  applyRetention(workspaceSlug: string) {
    return this.postJson<unknown>(`${projectHubWorkspacePath(workspaceSlug)}/retention/apply`);
  }
}
