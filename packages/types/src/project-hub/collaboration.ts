/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPackagePhase } from "./package";

/** Collaboration, AI, knowledge (API §5). */

export type TConversationKind = "project" | "package" | "direct";

export type TPHConversation = {
  id: string;
  kind: TConversationKind;
  title: string;
  project_id: string | null;
  issue_id: string | null;
  participant_ids: string[];
  unread_count?: number;
  last_message_at?: string | null;
  is_archived?: boolean;
};

export type TPHConversationCreate = {
  kind: TConversationKind;
  project_id?: string;
  issue_id?: string;
  participant_ids?: string[];
  title?: string;
};

export type TPHSourceRef = {
  type: string;
  id: string;
  title?: string;
  version?: string | number;
  project_id?: string | null;
  url?: string;
};

export type TPHAiContext = {
  used_sources?: TPHSourceRef[];
  blocked_sources?: (TPHSourceRef & { reason?: string })[];
  audience?: string[];
};

export type TPHMessage = {
  id: string;
  conversation_id: string;
  author_id: string | null;
  author_kind: "human" | "ai" | "system";
  parent_id: string | null;
  body: string;
  version: number;
  mentions: string[];
  created_at: string;
  edited_at: string | null;
  ai_context?: TPHAiContext;
  reply_count?: number;
};

export type TPHContextPreviewRequest = {
  conversation_id?: string;
  selection: { type: string; id: string; version?: string | number }[];
  project_ids: string[];
};

export type TPHContextPreview = {
  allowed: TPHSourceRef[];
  blocked: (TPHSourceRef & { reason?: string })[];
  audience?: { member_ids?: string[]; description?: string };
};

export type TPHDecisionPreviewRequest = {
  conversation_id: string;
  message_ids: string[];
  issue_id?: string;
  instruction: string;
};

export type TPHDecisionPreview = {
  preview_id?: string;
  /** When the instruction or target is unclear, the server asks exactly one clarification question. */
  clarification?: string | null;
  title?: string;
  text?: string;
  rationale?: string;
  issue_id?: string | null;
  sources?: TPHSourceRef[];
  audience_change?: { from?: string; to?: string; description?: string } | null;
};

export type TPHDecisionCreate = {
  preview_id?: string;
  title?: string;
  text?: string;
  rationale?: string;
  issue_id?: string;
  source_message_ids: string[];
  idempotency_key: string;
};

export type TPHDecision = {
  id: string;
  title: string;
  text: string;
  rationale: string;
  issue_id: string | null;
  scope?: string;
  status: "proposed" | "confirmed" | "superseded" | "withdrawn";
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  source_message_ids?: string[];
  source_changed_since_decision?: boolean;
  created_at: string;
};

export type TPHClarifyStep = {
  status: "question" | "checkpoint" | "closed";
  question?: string | null;
  recommendation?: string | null;
  questions_asked: number;
  summary?: string | null;
  open_blockers?: string[];
  session_id?: string;
};

export type TPHProposalKind =
  | "clarification"
  | "draft_edit"
  | "diagram_interpretation"
  | "decision_preview"
  | "priority_suggestion"
  | "dependency_suggestion"
  | "answer";

export type TPHProposalStatement = {
  text: string;
  /** observed | confirmed | inferred | proposed (PRD §14.2) */
  kind?: "observed" | "confirmed" | "inferred" | "proposed";
};

export type TPHProposal = {
  id: string;
  kind: TPHProposalKind;
  status: "pending" | "accepted" | "rejected" | "stale";
  issue_id: string | null;
  content: {
    summary?: string;
    changes?: { field: string; from?: unknown; to?: unknown }[];
    statements?: TPHProposalStatement[];
    [key: string]: unknown;
  };
  sources?: TPHSourceRef[];
  created_at: string;
};

export type TPHDiagramDocument = {
  id: string;
  name: string;
  diagram_type: string;
  issue_id: string | null;
  page_id: string | null;
  semantic: { nodes?: unknown[]; edges?: unknown[] };
  layout: Record<string, unknown>;
  version: number;
};

export type TPHDiagramUpdateResult = {
  layout_only: boolean;
  semantic_diff: Record<string, unknown>;
  proposal_id?: string | null;
};

export type TPHUploadScanStatus = "pending" | "clean" | "quarantined" | "failed";
export type TPHUploadFormatSupport = "native_edit" | "comment" | "preview" | "download";

export type TPHUploadRecord = {
  id: string;
  asset_id: string;
  name?: string;
  issue_id: string | null;
  owner_id?: string | null;
  declared_mime: string;
  detected_mime: string;
  scan_status: TPHUploadScanStatus;
  scan_detail: string;
  format_support: TPHUploadFormatSupport;
  created_at?: string;
};

export type TPHSearchResultType = "package" | "decision" | "page" | "message" | "event" | "upload" | string;

export type TPHSearchResult = {
  type: TPHSearchResultType;
  id: string;
  title: string;
  snippet: string;
  project_id: string | null;
  source: string;
  updated_at: string | null;
  url?: string;
  issue_id?: string | null;
};

export type TPHActivityEvent = {
  id: string;
  event_type: string;
  summary: string;
  occurred_at: string;
  received_at?: string;
  source_kind: "platform" | "provider" | "runner";
  source_id?: string;
  actor_kind: "human" | "agent" | "system";
  actor_id?: string;
  is_imported?: boolean;
  is_fixture?: boolean;
  payload?: Record<string, unknown>;
};

export type TPHActivityGroup = {
  issue_id: string | null;
  package_name?: string;
  sequence_id?: number | null;
  project_identifier?: string | null;
  day: string;
  summary: string;
  reasons: string[];
  outcome?: string | null;
  phase?: TPackagePhase | null;
  decision_needed?: boolean;
  responsible_id?: string | null;
  responsible_kind?: "human" | "agent" | "system";
  event_count: number;
  first_at: string;
  last_at: string;
  events: TPHActivityEvent[];
};

export type TPHActivityResponse = {
  since: string | null;
  until: string | null;
  groups: TPHActivityGroup[];
  open_decisions?: { id: string; title: string; issue_id?: string | null }[];
  source_health?: { source: string; last_synced_at: string | null; status?: string }[];
};

export type TPHOverview = {
  active: unknown[];
  ready: unknown[];
  review: unknown[];
  shipped: unknown[];
  open_decisions: { id: string; title: string; issue_id?: string | null }[];
  next_work: { issue_id: string; name: string; reasons: string[] }[];
};

export type TPHNotificationItem = {
  id: string;
  project_id: string | null;
  category: "mention" | "decision_needed" | "blocked" | "review_request" | "technical" | string;
  delivery: "immediate" | "digest";
  bundle_key?: string;
  count: number;
  title: string;
  target: { type?: string; id?: string; issue_id?: string; url?: string };
  read_at: string | null;
  created_at: string;
};

export type TPHRetentionCategory = "messages" | "audit" | "run_logs" | "raw_events" | "ai_outputs" | "exports";

export type TPHRetentionPolicy = { category: TPHRetentionCategory | string; retain_days: number | null };
