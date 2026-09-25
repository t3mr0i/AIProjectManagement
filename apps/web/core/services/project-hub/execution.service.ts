/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TClaimCreate,
  TPackageClaim,
  TPackageRun,
  TRunCreate,
  TRunnerKind,
  TRunnerProfile,
  TRunnerRegistration,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Runners, claims, runs (API §3). Runner-token endpoints (`R/...`) are never called from the browser. */
export class ProjectHubExecutionService extends ProjectHubBaseService {
  listRunners(workspaceSlug: string) {
    return this.getList<TRunnerProfile>(`${projectHubWorkspacePath(workspaceSlug)}/runners/`);
  }

  /** Human only; the token is returned exactly once. */
  registerRunner(workspaceSlug: string, data: { name: string; kind: TRunnerKind }) {
    return this.postJson<TRunnerRegistration>(`${projectHubWorkspacePath(workspaceSlug)}/runners/`, data);
  }

  deactivateRunner(workspaceSlug: string, runnerId: string) {
    return this.deleteJson<void>(`${projectHubWorkspacePath(workspaceSlug)}/runners/${runnerId}/`);
  }

  /** Claims with lease + heartbeat (web read projection). */
  listClaims(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getList<TPackageClaim>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/claims`
    );
  }

  createClaim(workspaceSlug: string, projectId: string, issueId: string, data: TClaimCreate) {
    return this.postJson<TPackageClaim>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/claims`,
      data
    );
  }

  listRuns(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getList<TPackageRun>(`${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/runs`);
  }

  startRun(workspaceSlug: string, projectId: string, issueId: string, data: TRunCreate) {
    return this.postJson<{ run: TPackageRun; run_token: string; manifest?: Record<string, unknown> }>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/runs`,
      data
    );
  }

  /** 202: accepted, run token invalidated. */
  cancelRun(workspaceSlug: string, projectId: string, runId: string) {
    return this.postJson<TPackageRun>(`${projectHubProjectPath(workspaceSlug, projectId)}/runs/${runId}/cancel`, {});
  }
}
