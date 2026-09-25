/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TPHAIStatus,
  TPHAIUsage,
  TPHAskRequest,
  TPHAskResponse,
  TPHAssistRequest,
  TPHAssistResponse,
  TPHProposal,
  TPHProposalRequest,
} from "@plane/types";
import {
  ProjectHubBaseService,
  createIdempotencyKey,
  normalizeProjectHubError,
  projectHubProjectPath,
  projectHubWorkspacePath,
} from "./base.service";

type TStreamHandlers = {
  /** Called for every `delta` event with the new chunk and the text so far. */
  onDelta?: (chunk: string, text: string) => void;
  signal?: AbortSignal;
};

/**
 * Parses one Server-Sent-Events block (`event: x\ndata: {...}`) into `{event, data}`.
 * Unknown / malformed blocks return `null` and are skipped.
 */
const parseSseBlock = (block: string): { event: string; data: Record<string, unknown> } | null => {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
};

/** AI core: status, Ask AI, writing assist (+ streaming), proposals, project report, usage (API §5). */
export class ProjectHubAIService extends ProjectHubBaseService {
  getStatus(workspaceSlug: string) {
    return this.getJson<TPHAIStatus>(`${projectHubWorkspacePath(workspaceSlug)}/ai/status`);
  }

  /** Private answer; context is limited to what the requester can read. */
  ask(workspaceSlug: string, data: TPHAskRequest) {
    return this.postJson<TPHAskResponse>(`${projectHubWorkspacePath(workspaceSlug)}/ai/ask`, data);
  }

  assist(workspaceSlug: string, data: TPHAssistRequest) {
    return this.postJson<TPHAssistResponse>(`${projectHubWorkspacePath(workspaceSlug)}/ai/assist`, data);
  }

  /**
   * Streams `W/ai/assist/stream` (SSE over a POST, so `fetch` + `ReadableStream` instead of
   * `EventSource`). Session cookie auth like every other call; the REST API does not enforce CSRF.
   * Falls back to the non-streaming endpoint when the browser has no stream support or the stream
   * cannot be opened. Resolves with the full text.
   */
  async assistStream(workspaceSlug: string, data: TPHAssistRequest, handlers: TStreamHandlers = {}): Promise<string> {
    const fallback = async () => {
      const result = await this.assist(workspaceSlug, data);
      handlers.onDelta?.(result.text, result.text);
      return result.text;
    };
    if (typeof fetch === "undefined" || typeof TextDecoder === "undefined") return fallback();

    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${projectHubWorkspacePath(workspaceSlug)}/ai/assist/stream/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          "Idempotency-Key": createIdempotencyKey(),
        },
        body: JSON.stringify(data),
        signal: handlers.signal,
      });
    } catch (error) {
      if (handlers.signal?.aborted) throw normalizeProjectHubError(error);
      return fallback();
    }
    if (!response.ok) {
      let body: unknown = undefined;
      try {
        body = await response.json();
      } catch {
        // non-JSON error body
      }
      throw normalizeProjectHubError({ response: { status: response.status, data: body } });
    }
    if (!response.body) return fallback();

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let text = "";
    for (;;) {
      // oxlint-disable-next-line no-await-in-loop -- chunks must be read in order
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const parsed = parseSseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
        if (!parsed) continue;
        if (parsed.event === "done") return text;
        if (parsed.event === "delta" && typeof parsed.data.text === "string") {
          text += parsed.data.text;
          handlers.onDelta?.(parsed.data.text, text);
        }
      }
    }
    return text;
  }

  /** Concretize / interpret / report / answer → always a pending proposal, never an applied change. */
  requestProposal(workspaceSlug: string, projectId: string, data: TPHProposalRequest) {
    return this.postJson<TPHProposal>(`${projectHubProjectPath(workspaceSlug, projectId)}/proposals/`, data);
  }

  /** Project status report, stored as a reviewable `answer` proposal. */
  createProjectReport(workspaceSlug: string, projectId: string, instruction?: string) {
    return this.postJson<TPHProposal>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/ai/report`,
      instruction ? { instruction } : {}
    );
  }

  /** Workspace admins only (403 otherwise). */
  getUsage(workspaceSlug: string, days = 30) {
    return this.getJson<TPHAIUsage>(`${projectHubWorkspacePath(workspaceSlug)}/ai/usage`, { days });
  }

  /** Queue a rebuild of the workspace semantic index (workspace admins). */
  reindex(workspaceSlug: string) {
    return this.postJson<{ queued: boolean }>(`${projectHubWorkspacePath(workspaceSlug)}/ai/reindex`);
  }
}
