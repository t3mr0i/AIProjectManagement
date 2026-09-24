/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
// plane imports
import type {
  TPackageProfile,
  TPackageProfileUpdate,
  TPackageRow,
  TPackageStatus,
  TProjectHubApiError,
  TProjectHubCapabilities,
  TProjectHubCapability,
} from "@plane/types";
// services
import {
  ProjectHubCollaborationService,
  ProjectHubExecutionService,
  ProjectHubIntegrationService,
  ProjectHubKnowledgeService,
  ProjectHubPackageService,
  ProjectHubPlanningService,
} from "@/services/project-hub";
// local imports
import { PH_KEYS } from "./keys";

const DISABLED_CAPABILITIES: TProjectHubCapabilities = {
  capabilities: [],
  principal_kind: "human",
  extension_enabled: false,
};

/** Package rows used for native list badges are refreshed at most every minute. */
const ROWS_TTL_MS = 60_000;

export interface IProjectHubStore {
  // observables
  resources: Map<string, unknown>;
  fetchedAt: Map<string, number>;
  // services
  packageService: ProjectHubPackageService;
  executionService: ProjectHubExecutionService;
  integrationService: ProjectHubIntegrationService;
  collaborationService: ProjectHubCollaborationService;
  planningService: ProjectHubPlanningService;
  knowledgeService: ProjectHubKnowledgeService;
  // generic cache
  getResource: <T>(key: string) => T | undefined;
  setResource: <T>(key: string, value: T) => void;
  load: <T>(key: string, fetcher: () => Promise<T>) => Promise<T>;
  invalidate: (prefix: string) => void;
  // capabilities / feature flag (UX only — the backend policy is the real guard)
  fetchCapabilities: (workspaceSlug: string, projectId?: string) => Promise<TProjectHubCapabilities>;
  getCapabilities: (workspaceSlug: string, projectId?: string) => TProjectHubCapabilities | undefined;
  isEnabled: (workspaceSlug: string | undefined, projectId?: string) => boolean;
  hasCapability: (workspaceSlug: string, projectId: string | undefined, capability: TProjectHubCapability) => boolean;
  // package rows (list badges)
  ensureProjectRows: (workspaceSlug: string, projectId: string) => void;
  getRowForIssue: (workspaceSlug: string, projectId: string, issueId: string) => TPackageRow | undefined;
  // package profile
  fetchProfile: (workspaceSlug: string, projectId: string, issueId: string) => Promise<TPackageProfile | null>;
  activateProfile: (workspaceSlug: string, projectId: string, issueId: string) => Promise<TPackageProfile>;
  updateProfile: (
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: TPackageProfileUpdate
  ) => Promise<TPackageProfile>;
  fetchStatus: (workspaceSlug: string, projectId: string, issueId: string) => Promise<TPackageStatus | null>;
  invalidateIssue: (issueId: string) => void;
}

export class ProjectHubStore implements IProjectHubStore {
  resources = observable.map<string, unknown>({}, { deep: false });
  fetchedAt = observable.map<string, number>();
  private inflight = new Map<string, Promise<unknown>>();
  /** Throttle for list-badge prefetches (kept separate from `fetchedAt` so pages still load on failure). */
  private rowsAttemptAt = new Map<string, number>();

  packageService = new ProjectHubPackageService();
  executionService = new ProjectHubExecutionService();
  integrationService = new ProjectHubIntegrationService();
  collaborationService = new ProjectHubCollaborationService();
  planningService = new ProjectHubPlanningService();
  knowledgeService = new ProjectHubKnowledgeService();

  constructor() {
    makeObservable(this, {
      setResource: action,
      invalidate: action,
    });
  }

  // ---------------------------------------------------------------- generic cache

  getResource = <T>(key: string): T | undefined => this.resources.get(key) as T | undefined;

  setResource = <T>(key: string, value: T) => {
    this.resources.set(key, value);
    this.fetchedAt.set(key, Date.now());
  };

  /** Fetch and cache; concurrent calls for the same key share one request. */
  load = <T>(key: string, fetcher: () => Promise<T>): Promise<T> => {
    const existing = this.inflight.get(key) as Promise<T> | undefined;
    if (existing) return existing;
    const promise = fetcher()
      .then((value) => {
        runInAction(() => this.setResource(key, value));
        return value;
      })
      .finally(() => {
        this.inflight.delete(key);
      });
    this.inflight.set(key, promise);
    return promise;
  };

  invalidate = (prefix: string) => {
    for (const key of this.fetchedAt.keys()) {
      if (key.startsWith(prefix)) this.fetchedAt.set(key, 0);
    }
  };

  // ---------------------------------------------------------------- capabilities

  fetchCapabilities = async (workspaceSlug: string, projectId?: string): Promise<TProjectHubCapabilities> => {
    const key = PH_KEYS.capabilities(workspaceSlug, projectId);
    try {
      return await this.load(key, () => this.packageService.getMyCapabilities(workspaceSlug, projectId));
    } catch (_error) {
      // Extension not installed / unreachable / no permission → treat as disabled (UX only).
      runInAction(() => this.setResource(key, DISABLED_CAPABILITIES));
      return DISABLED_CAPABILITIES;
    }
  };

  getCapabilities = (workspaceSlug: string, projectId?: string) =>
    this.getResource<TProjectHubCapabilities>(PH_KEYS.capabilities(workspaceSlug, projectId));

  isEnabled = (workspaceSlug: string | undefined, projectId?: string): boolean => {
    if (!workspaceSlug) return false;
    return !!this.getCapabilities(workspaceSlug, projectId)?.extension_enabled;
  };

  hasCapability = (workspaceSlug: string, projectId: string | undefined, capability: TProjectHubCapability) => {
    const caps = this.getCapabilities(workspaceSlug, projectId);
    return !!caps?.extension_enabled && caps.capabilities.includes(capability);
  };

  // ---------------------------------------------------------------- package rows (badges)

  ensureProjectRows = (workspaceSlug: string, projectId: string) => {
    const key = PH_KEYS.rows(workspaceSlug, projectId);
    const lastLoaded = this.fetchedAt.get(key) ?? 0;
    const lastAttempt = this.rowsAttemptAt.get(key) ?? 0;
    const now = Date.now();
    if (now - Math.max(lastLoaded, lastAttempt) < ROWS_TTL_MS || this.inflight.has(key)) return;
    // one attempt per project and TTL — avoids request storms from many list rows
    this.rowsAttemptAt.set(key, now);
    this.load(key, () => this.packageService.listPackages(workspaceSlug, projectId, "all")).catch(() => undefined);
  };

  getRowForIssue = (workspaceSlug: string, projectId: string, issueId: string) =>
    this.getResource<TPackageRow[]>(PH_KEYS.rows(workspaceSlug, projectId))?.find((r) => r.work_item_id === issueId);

  // ---------------------------------------------------------------- profile

  /** Profile or `null` for a normal issue (404 `NO_PROFILE`). Pure fetcher — caching is done by `load`. */
  fetchProfile = async (workspaceSlug: string, projectId: string, issueId: string) => {
    try {
      return await this.packageService.getProfile(workspaceSlug, projectId, issueId);
    } catch (error) {
      if ((error as TProjectHubApiError)?.status === 404) return null;
      throw error;
    }
  };

  activateProfile = async (workspaceSlug: string, projectId: string, issueId: string) => {
    const profile = await this.packageService.activateProfile(workspaceSlug, projectId, issueId, {});
    runInAction(() => {
      this.setResource(PH_KEYS.profile(issueId), profile);
      this.invalidateIssue(issueId);
      this.invalidate(PH_KEYS.rows(workspaceSlug, projectId));
    });
    return profile;
  };

  /**
   * Draft text fields are harmless, so the edit is applied optimistically and rolled back on error
   * (e.g. `VERSION_CONFLICT`). Approvals, merges and claims never use this path.
   */
  updateProfile = async (workspaceSlug: string, projectId: string, issueId: string, data: TPackageProfileUpdate) => {
    const key = PH_KEYS.profile(issueId);
    const previous = this.getResource<TPackageProfile>(key);
    if (previous) {
      const { expected_version: _v, ...fields } = data;
      runInAction(() => this.resources.set(key, { ...previous, ...fields }));
    }
    try {
      const profile = await this.packageService.updateProfile(workspaceSlug, projectId, issueId, data);
      runInAction(() => {
        this.setResource(key, profile);
        this.invalidate(PH_KEYS.readiness(issueId));
      });
      return profile;
    } catch (error) {
      if (previous) runInAction(() => this.resources.set(key, previous));
      throw error;
    }
  };

  /** Status projection or `null` when the issue has no profile. Pure fetcher. */
  fetchStatus = async (workspaceSlug: string, projectId: string, issueId: string) => {
    try {
      return await this.packageService.getStatus(workspaceSlug, projectId, issueId);
    } catch (error) {
      if ((error as TProjectHubApiError)?.status === 404) return null;
      throw error;
    }
  };

  invalidateIssue = (issueId: string) => {
    this.invalidate(`ph:issue:${issueId}:`);
  };
}
