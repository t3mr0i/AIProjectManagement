/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AxiosRequestConfig, AxiosResponse } from "axios";
// plane imports
import { API_BASE_URL } from "@plane/constants";
import type { TProjectHubApiError } from "@plane/types";
// services
import { APIService } from "@/services/api.service";

/** `P = /api/workspaces/{slug}/projects/{project_id}/package-flow` */
export const projectHubProjectPath = (workspaceSlug: string, projectId: string) =>
  `/api/workspaces/${workspaceSlug}/projects/${projectId}/package-flow`;

/** `W = /api/workspaces/{slug}/package-flow` */
export const projectHubWorkspacePath = (workspaceSlug: string) => `/api/workspaces/${workspaceSlug}/package-flow`;

type TAxiosLikeError = {
  response?: { status?: number; data?: unknown };
  message?: string;
};

/**
 * Normalizes transport errors into the contract envelope `{status, code, error, detail}` so the UI
 * can render permission / conflict / offline states (PRD §11.4) instead of a generic failure.
 */
export const normalizeProjectHubError = (error: unknown): TProjectHubApiError => {
  const err = (error ?? {}) as TAxiosLikeError;
  if (!err.response) {
    return { status: null, code: "NETWORK_ERROR", error: err.message ?? "Network error" };
  }
  const status = err.response.status ?? null;
  const data = (err.response.data ?? {}) as Record<string, unknown>;
  return {
    status,
    code: typeof data.code === "string" ? data.code : `HTTP_${status ?? "ERROR"}`,
    error: typeof data.error === "string" ? data.error : typeof data.detail === "string" ? data.detail : "",
    detail: data.detail && typeof data.detail === "object" ? (data.detail as Record<string, unknown>) : undefined,
  };
};

/** Random idempotency key for writes (API conventions: `Idempotency-Key`). */
export const createIdempotencyKey = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export abstract class ProjectHubBaseService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  protected async unwrap<T>(request: Promise<AxiosResponse<T>>): Promise<T> {
    try {
      const response = await request;
      return response?.data;
    } catch (error) {
      throw normalizeProjectHubError(error);
    }
  }

  protected getJson<T>(url: string, params?: Record<string, unknown>): Promise<T> {
    return this.unwrap<T>(this.get(url, params ? { params } : {}));
  }

  /** Writes always carry an `Idempotency-Key`; retries of the same UI action reuse it. */
  protected postJson<T>(url: string, data: unknown = {}, idempotencyKey: string = createIdempotencyKey()): Promise<T> {
    const config: AxiosRequestConfig = { headers: { "Idempotency-Key": idempotencyKey } };
    return this.unwrap<T>(this.post(url, data as object, config));
  }

  protected patchJson<T>(url: string, data: unknown = {}): Promise<T> {
    return this.unwrap<T>(this.patch(url, data as object, { headers: { "Idempotency-Key": createIdempotencyKey() } }));
  }

  protected putJson<T>(url: string, data: unknown = {}): Promise<T> {
    return this.unwrap<T>(this.put(url, data as object, { headers: { "Idempotency-Key": createIdempotencyKey() } }));
  }

  protected deleteJson<T>(url: string): Promise<T> {
    return this.unwrap<T>(this.delete(url));
  }
}
