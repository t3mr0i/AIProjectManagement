/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TPHActivityResponse,
  TPHDiagramDocument,
  TPHDiagramUpdateResult,
  TPHOverview,
  TPHRetentionPolicy,
  TPHSearchResult,
  TPHUploadRecord,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Activity, overview, search, uploads, diagrams, retention (API §5). */
export class ProjectHubKnowledgeService extends ProjectHubBaseService {
  /** `since` is `last_visit` or an ISO timestamp. Grouped by package & day. */
  getActivity(workspaceSlug: string, projectId: string, params: { since: string; until?: string; issue_id?: string }) {
    return this.getJson<TPHActivityResponse>(`${projectHubProjectPath(workspaceSlug, projectId)}/activity/`, {
      ...params,
      group: "package",
    });
  }

  setVisitMarker(workspaceSlug: string, projectId: string) {
    return this.postJson<unknown>(`${projectHubProjectPath(workspaceSlug, projectId)}/activity/visit`);
  }

  getOverview(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHOverview>(`${projectHubProjectPath(workspaceSlug, projectId)}/overview`);
  }

  search(workspaceSlug: string, q: string, types?: string[]) {
    return this.getJson<TPHSearchResult[] | { results: TPHSearchResult[] }>(
      `${projectHubWorkspacePath(workspaceSlug)}/search/`,
      { q, ...(types?.length ? { types: types.join(",") } : {}) }
    );
  }

  registerUpload(workspaceSlug: string, projectId: string, assetId: string, issueId?: string) {
    return this.postJson<TPHUploadRecord>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/uploads/${assetId}/register`,
      issueId ? { issue_id: issueId } : {}
    );
  }

  /** Not in the contract table; the server may expose uploads as a list — tolerated as optional. */
  listUploads(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHUploadRecord[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/uploads/`);
  }

  listDiagrams(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHDiagramDocument[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/`);
  }

  updateDiagram(
    workspaceSlug: string,
    projectId: string,
    diagramId: string,
    data: { semantic: unknown; layout: unknown; expected_version: number }
  ) {
    return this.putJson<TPHDiagramUpdateResult>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/diagrams/${diagramId}/`,
      data
    );
  }

  getRetention(workspaceSlug: string) {
    return this.getJson<TPHRetentionPolicy[] | { policies: TPHRetentionPolicy[] }>(
      `${projectHubWorkspacePath(workspaceSlug)}/retention/`
    );
  }

  updateRetention(workspaceSlug: string, policies: TPHRetentionPolicy[]) {
    return this.putJson<TPHRetentionPolicy[]>(`${projectHubWorkspacePath(workspaceSlug)}/retention/`, { policies });
  }

  applyRetention(workspaceSlug: string) {
    return this.postJson<unknown>(`${projectHubWorkspacePath(workspaceSlug)}/retention/apply`);
  }
}
