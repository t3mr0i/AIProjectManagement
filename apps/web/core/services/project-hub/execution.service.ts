/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TClaimCreate,
  TClaimCreated,
  TPackageClaim,
  TPackageRun,
  TPackageRunList,
  TRunCreate,
  TRunnerKind,
  TRunnerProfile,
  TRunnerRegistration,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Runners, claims, runs (API §3). Runner-token endpoints (`R/...`) are not called from the browser. */
export class ProjectHubExecutionService extends ProjectHubBaseService {
  listRunners(workspaceSlug: string) {
    return this.getJson<TRunnerProfile[]>(`${projectHubWorkspacePath(workspaceSlug)}/runners/`);
  }

  registerRunner(workspaceSlug: string, data: { name: string; kind: TRunnerKind }) {
    return this.postJson<TRunnerRegistration>(`${projectHubWorkspacePath(workspaceSlug)}/runners/`, data);
  }

  deactivateRunner(workspaceSlug: string, runnerId: string) {
    return this.deleteJson<void>(`${projectHubWorkspacePath(workspaceSlug)}/runners/${runnerId}/`);
  }

  /**
   * Claims have no list endpoint in the contract; the server may embed them in the runs listing.
   * `createClaim` is exposed for completeness (the runner normally claims).
   */
  createClaim(workspaceSlug: string, projectId: string, issueId: string, data: TClaimCreate) {
    return this.postJson<TClaimCreated>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/claims`,
      data
    );
  }

  listRuns(workspaceSlug: string, projectId: string, issueId: string) {
    return this.getJson<TPackageRunList | TPackageRun[] | { runs: TPackageRun[]; claims?: TPackageClaim[] }>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/runs`
    );
  }

  startRun(workspaceSlug: string, projectId: string, issueId: string, data: TRunCreate) {
    return this.postJson<{ run: TPackageRun; run_token: string; manifest?: Record<string, unknown> }>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/runs`,
      data
    );
  }

  cancelRun(workspaceSlug: string, projectId: string, runId: string) {
    return this.postJson<unknown>(`${projectHubProjectPath(workspaceSlug, projectId)}/runs/${runId}/cancel`, {});
  }
}
