/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Stable cache keys for Project Hub resources (store + SWR share them). */
export const PH_KEYS = {
  capabilities: (ws: string, projectId?: string) => `ph:caps:${ws}:${projectId ?? ""}`,
  activation: (ws: string) => `ph:activation:${ws}`,
  grants: (ws: string) => `ph:grants:${ws}`,
  runners: (ws: string) => `ph:runners:${ws}`,
  providers: (ws: string) => `ph:providers:${ws}`,
  connections: (ws: string) => `ph:connections:${ws}`,
  health: (ws: string, connectionId: string) => `ph:health:${ws}:${connectionId}`,
  retention: (ws: string) => `ph:retention:${ws}`,
  conversations: (ws: string) => `ph:conversations:${ws}`,
  messages: (ws: string, conversationId: string) => `ph:messages:${ws}:${conversationId}`,
  notifications: (ws: string) => `ph:notifications:${ws}`,
  search: (ws: string, q: string, types: string) => `ph:search:${ws}:${types}:${q}`,
  roadmap: (ws: string, params: string) => `ph:roadmap:${ws}:${params}`,
  dependencies: (ws: string) => `ph:deps:${ws}`,
  rows: (ws: string, projectId: string) => `ph:rows:${ws}:${projectId}`,
  activity: (ws: string, projectId: string, since: string, until: string) =>
    `ph:activity:${ws}:${projectId}:${since}:${until}`,
  overview: (ws: string, projectId: string) => `ph:overview:${ws}:${projectId}`,
  milestones: (ws: string, projectId: string) => `ph:milestones:${ws}:${projectId}`,
  risks: (ws: string, projectId: string) => `ph:risks:${ws}:${projectId}`,
  uploads: (ws: string, projectId: string) => `ph:uploads:${ws}:${projectId}`,
  diagrams: (ws: string, projectId: string) => `ph:diagrams:${ws}:${projectId}`,
  repositories: (ws: string, projectId: string) => `ph:repos:${ws}:${projectId}`,
  decisions: (ws: string, projectId: string, issueId?: string) => `ph:decisions:${ws}:${projectId}:${issueId ?? ""}`,
  proposals: (ws: string, projectId: string, issueId?: string) => `ph:proposals:${ws}:${projectId}:${issueId ?? ""}`,
  // issue scoped — `issueId` is the native Plane issue id (workItemId)
  profile: (issueId: string) => `ph:issue:${issueId}:profile`,
  status: (issueId: string) => `ph:issue:${issueId}:status`,
  readiness: (issueId: string) => `ph:issue:${issueId}:readiness`,
  revisions: (issueId: string) => `ph:issue:${issueId}:revisions`,
  compare: (issueId: string, from: string, to: string) => `ph:issue:${issueId}:compare:${from}:${to}`,
  approvals: (issueId: string) => `ph:issue:${issueId}:approvals`,
  changeRecords: (issueId: string) => `ph:issue:${issueId}:changes`,
  runs: (issueId: string) => `ph:issue:${issueId}:runs`,
  review: (issueId: string) => `ph:issue:${issueId}:review`,
  mergeRequests: (issueId: string) => `ph:issue:${issueId}:mrs`,
  evidence: (issueId: string) => `ph:issue:${issueId}:evidence`,
  delivery: (issueId: string) => `ph:issue:${issueId}:delivery`,
  spec: (issueId: string) => `ph:issue:${issueId}:spec`,
  syncConflicts: (issueId: string) => `ph:issue:${issueId}:conflicts`,
  externalLinks: (issueId: string) => `ph:issue:${issueId}:links`,
  thread: (issueId: string) => `ph:issue:${issueId}:thread`,
};
