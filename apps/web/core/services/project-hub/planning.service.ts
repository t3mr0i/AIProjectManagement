/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TPHDependency,
  TPHDependencyCreate,
  TPHMilestone,
  TPHMilestoneCreate,
  TPHRisk,
  TPHRoadmap,
  TPHScenario,
  TPHScenarioChange,
  TPHScenarioImpact,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Milestones, dependencies, roadmap, scenarios, risks (API §6). */
export class ProjectHubPlanningService extends ProjectHubBaseService {
  listMilestones(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHMilestone[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/milestones/`);
  }

  createMilestone(workspaceSlug: string, projectId: string, data: TPHMilestoneCreate) {
    return this.postJson<TPHMilestone>(`${projectHubProjectPath(workspaceSlug, projectId)}/milestones/`, data);
  }

  updateMilestone(workspaceSlug: string, projectId: string, milestoneId: string, data: Partial<TPHMilestoneCreate>) {
    return this.patchJson<TPHMilestone>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/milestones/${milestoneId}/`,
      data
    );
  }

  deleteMilestone(workspaceSlug: string, projectId: string, milestoneId: string) {
    return this.deleteJson<void>(`${projectHubProjectPath(workspaceSlug, projectId)}/milestones/${milestoneId}/`);
  }

  listDependencies(workspaceSlug: string, params?: { project_ids?: string }) {
    return this.getJson<TPHDependency[]>(`${projectHubWorkspacePath(workspaceSlug)}/dependencies/`, params);
  }

  /** 422 `DEPENDENCY_CYCLE` with `detail.path`. */
  createDependency(workspaceSlug: string, data: TPHDependencyCreate) {
    return this.postJson<TPHDependency>(`${projectHubWorkspacePath(workspaceSlug)}/dependencies/`, data);
  }

  confirmDependency(workspaceSlug: string, dependencyId: string) {
    return this.postJson<TPHDependency>(
      `${projectHubWorkspacePath(workspaceSlug)}/dependencies/${dependencyId}/confirm`
    );
  }

  getRoadmap(workspaceSlug: string, params: { project_ids?: string; team_id?: string; from?: string; to?: string }) {
    return this.getJson<TPHRoadmap>(`${projectHubWorkspacePath(workspaceSlug)}/roadmap/`, params);
  }

  createScenario(workspaceSlug: string, data: { name: string; changes: TPHScenarioChange[] }) {
    return this.postJson<TPHScenario>(`${projectHubWorkspacePath(workspaceSlug)}/scenarios/`, data);
  }

  getScenarioImpact(workspaceSlug: string, scenarioId: string) {
    return this.getJson<TPHScenarioImpact>(`${projectHubWorkspacePath(workspaceSlug)}/scenarios/${scenarioId}/impact`);
  }

  applyScenario(workspaceSlug: string, scenarioId: string) {
    return this.postJson<TPHScenario>(`${projectHubWorkspacePath(workspaceSlug)}/scenarios/${scenarioId}/apply`);
  }

  listRisks(workspaceSlug: string, projectId: string) {
    return this.getJson<TPHRisk[]>(`${projectHubProjectPath(workspaceSlug, projectId)}/risks/`);
  }
}
