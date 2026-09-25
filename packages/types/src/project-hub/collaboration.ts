/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Collaboration, AI, knowledge (API §5). Shapes follow the Django serializers. */

export type TConversationKind = "project" | "package" | "direct";

export type TPHConversation = {
  id: string;
  kind: TConversationKind;
  title: string;
  project_id: string | null;
  issue_id: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  /** Only for direct messages. */
  participant_ids?: string[];
  last_read_at?: string | null;
  unread_count?: number;
};

export type TPHConversationCreate = {
  kind: TConversationKind;
  project_id?: string;
  issue_id?: string;
  participant_ids?: string[];
  title?: string;
};

export type TPHSourceRef = { type: string; id: string; version?: string | number };

export type TPHBlockedSource = { ref: TPHSourceRef; reason: string };

export type TPHVisibleSource = {
  ref: TPHSourceRef;
  title: string | null;
  status: "allowed" | "blocked";
  reason?: string;
  stale?: boolean;
};

/** `ai_context` of an AI message (FR-C02): used and blocked sources for the audience. */
export type TPHAiContext = {
  status?: string;
  provider?: string;
  sources_used?: TPHSourceRef[];
  blocked?: TPHBlockedSource[];
  visible?: TPHVisibleSource[];
  explicit_selection?: TPHSourceRef[];
  statements?: { text: string; status: string; sources: unknown[] }[];
  notes?: string[];
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
  source_links: unknown[];
  ai_context: TPHAiContext | Record<string, never>;
  edited_at: string | null;
  created_at: string;
};

/** `POST .../messages/` also returns the AI answer when `@AI` was mentioned. */
export type TPHMessageCreated = TPHMessage & { ai_answer: TPHMessage | null };

export type TPHContextPreviewRequest = {
  conversation_id?: string;
  selection: TPHSourceRef[];
  project_ids: string[];
};

/** `POST W/ai/context-preview` */
export type TPHContextPreview = {
  allowed: { ref: TPHSourceRef; title: string | null; confirmed?: boolean; stale?: boolean }[];
  blocked: TPHBlockedSource[];
  visible: TPHVisibleSource[];
  audience_size: number;
};

export type TPHDecisionPreviewRequest = {
  conversation_id: string;
  message_ids: string[];
  issue_id?: string;
  instruction: string;
};

/** `POST P/decisions/preview` → exactly one clarification question or a preview. */
export type TPHDecisionPreview =
  | {
      type: "clarification";
      question: string;
      reason: string;
      options?: { issue_id: string; identifier: string; name: string }[];
    }
  | {
      type: "preview";
      preview_id: string;
      title: string;
      text: string;
      rationale: string;
      issue_id: string | null;
      scope: "package" | "project";
      source_message_ids: string[];
      source_versions: Record<string, number>;
      private_source: boolean;
      requires_reviewed_summary: boolean;
      statements: { text: string; status: string; sources: TPHSourceRef[] }[];
      target: { issue_id: string | null; project_id: string };
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
  project_id: string | null;
  issue_id: string | null;
  title: string;
  text: string;
  rationale: string;
  scope: string;
  status: "proposed" | "confirmed" | "superseded" | "withdrawn";
  kind: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  idempotency_key: string;
  source_changed_since_decision: boolean;
  source_deleted: boolean;
  created_at: string;
  source_snapshot?: unknown;
};

/** `POST P/work-items/{id}/clarify` body. */
export type TPHClarifyRequest = { answer?: string; stop?: boolean; continue?: boolean };

/** `POST P/work-items/{id}/clarify` → question | checkpoint | complete. Nothing is applied automatically. */
export type TPHClarifyStep =
  | {
      type: "question";
      session_id: string;
      topic: string;
      question: string;
      why: string;
      /** A suggestion, never an applied value. */
      recommendation: string | null;
      skipped: unknown[];
      questions_asked: number;
    }
  | {
      type: "checkpoint" | "complete";
      reason: string;
      session_id: string;
      questions_asked: number;
      draft_proposal_id: string | null;
      draft: TPHProposalContent | null;
      open_topics: string[];
      can_continue: boolean;
      approval_required: false;
      applied: false;
      skipped?: unknown[];
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
  /** observed | confirmed | inferred | proposed (PRD §14.2); `kind` in diagram proposals, `status` elsewhere */
  kind?: string;
  status?: string;
  sources?: unknown[];
};

/** Content differs per proposal kind; known keys are typed, everything else is shown read-only. */
export type TPHProposalContent = {
  patch?: Record<string, unknown>;
  statements?: TPHProposalStatement[];
  note?: string;
  task?: string;
  result?: { text?: string; status?: string; [key: string]: unknown };
  // diagram interpretation
  interpretation?: string;
  affected_areas?: string[];
  possible_impacts?: string[];
  uncertainty?: { level: "low" | "medium" | "high"; reasons: string[] };
  questions?: { edge_id: string; text: string }[];
  suggested_criteria?: { edge_id: string; text: string; status: string }[];
  diagram_id?: string;
  diagram_version?: number;
  [key: string]: unknown;
};

export type TPHProposal = {
  id: string;
  kind: TPHProposalKind;
  status: "pending" | "accepted" | "rejected" | "stale";
  issue_id: string | null;
  project_id?: string | null;
  content: TPHProposalContent;
  selection?: unknown;
  sources?: TPHSourceRef[];
  base_version: string;
  requested_by?: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at?: string;
};

// -- diagrams (S08) -------------------------------------------------------------

export type TPHDiagramNode = { id: string; type: string; label: string; properties: Record<string, unknown> };
export type TPHDiagramEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  /** `direction` of `both|bidirectional|unknown|ambiguous|?` makes the edge a question, not a requirement. */
  properties: Record<string, unknown>;
};
export type TPHDiagramSemantic = { nodes: TPHDiagramNode[]; edges: TPHDiagramEdge[] };
export type TPHDiagramLayout = Record<string, { x?: number; y?: number; w?: number; h?: number }>;

export type TPHDiagramDocument = {
  id: string;
  project_id: string;
  workspace_id: string;
  issue_id: string | null;
  page_id: string | null;
  name: string;
  diagram_type: string;
  semantic: TPHDiagramSemantic;
  layout: TPHDiagramLayout;
  version: number;
  updated_at: string | null;
};

export type TPHDiagramVersion = {
  id: string;
  version: number;
  layout_only: boolean;
  semantic_diff: TPHDiagramSemanticDiff | Record<string, never>;
  proposal_id: string | null;
  created_at: string | null;
};

type TElementDiff<T> = {
  added: T[];
  removed: T[];
  changed: {
    id: string;
    fields: Record<string, { before: unknown; after: unknown }>;
    properties: Record<string, { before: unknown; after: unknown }>;
  }[];
};

export type TPHDiagramSemanticDiff = { nodes: TElementDiff<TPHDiagramNode>; edges: TElementDiff<TPHDiagramEdge> };

/** `GET P/diagrams/{id}/` */
export type TPHDiagramDetail = TPHDiagramDocument & { versions: TPHDiagramVersion[]; proposals: TPHProposal[] };

export type TPHDiagramCreate = {
  name: string;
  diagram_type?: string;
  issue_id?: string;
  semantic: TPHDiagramSemantic;
  layout: TPHDiagramLayout;
};

/** `PUT P/diagrams/{id}/` → layout-only vs semantic change (+ pending interpretation proposal). */
export type TPHDiagramUpdateResult = {
  changed: boolean;
  layout_only: boolean;
  semantic_diff: TPHDiagramSemanticDiff;
  layout_diff: { changed: Record<string, { before: unknown; after: unknown }> };
  proposal_id: string | null;
  proposal?: TPHProposal | null;
  version?: TPHDiagramVersion;
  diagram: TPHDiagramDocument;
};

/** Accepting appends criteria/scope notes to the working draft only (no revision, no approval). */
export type TPHDiagramProposalAccepted = {
  proposal: TPHProposal;
  criteria_added?: unknown[];
  profile_version?: number;
  revision_created?: false;
  execution_approved?: false;
};

// -- uploads (FR-C05, FR-E04) ---------------------------------------------------

export type TPHUploadScanStatus = "pending" | "clean" | "quarantined" | "failed";
export type TPHUploadFormatSupport = "native_edit" | "comment" | "preview" | "download";

export type TPHUploadRecord = {
  id: string;
  asset_id: string;
  name: string;
  project_id: string | null;
  issue_id: string | null;
  owner_id: string | null;
  declared_mime: string;
  detected_mime: string;
  scan_status: TPHUploadScanStatus;
  scan_detail: string;
  format_support: TPHUploadFormatSupport;
  has_extracted_text: boolean;
  updated_at: string | null;
};

/** `GET P/uploads/candidates` — native FileAssets of the project not yet registered. */
export type TPHUploadCandidate = {
  asset_id: string;
  name: string;
  declared_mime: string;
  size: number;
  entity_type: string;
  issue_id: string | null;
  is_uploaded: boolean;
  created_at: string;
};

export type TPHUploadRegister = { declared_mime?: string; filename?: string; issue_id?: string };

// -- search, activity, overview, notifications, retention ------------------------

export type TPHSearchResultType = "package" | "issue" | "decision" | "page" | "message" | "event" | "upload";

/** `GET W/search/` → `{results}`; no total counts (FR-P06). */
export type TPHSearchResult = {
  type: TPHSearchResultType | string;
  id: string;
  title: string;
  snippet: string;
  project_id: string | null;
  issue_id?: string | null;
  conversation_id?: string | null;
  identifier?: string;
  source: "package_flow" | "plane" | string;
  updated_at: string | null;
  rank?: number;
};

export type TPHActivityEntry =
  | {
      kind: "event";
      id: string;
      source: "package_flow";
      event_type: string;
      summary: string;
      reason: string;
      actor_kind: "human" | "agent" | "system";
      actor_id: string;
      occurred_at: string;
      is_fixture: boolean;
      status?: string;
    }
  | {
      kind: "native";
      id: string;
      source: "plane";
      event_type: string;
      field: string | null;
      summary: string;
      old_value: string | null;
      new_value: string | null;
      actor_id: string | null;
      occurred_at: string;
    }
  | {
      /** Compacted technical events (FR-P03); `raw_ids` can be expanded via `?ids=`. */
      kind: "summary";
      event_type: string;
      count: number;
      summary: string;
      raw_ids: string[];
      first_at: string;
      occurred_at: string;
    };

export type TPHActivityDecision = {
  id: string;
  title: string;
  kind: string;
  status: string;
  issue_id: string | null;
  confirmed_at: string | null;
  created_at: string;
};

/** `GET P/activity/?since=&until=&issue_id=` */
export type TPHActivityFeed = {
  since: string;
  until: string;
  raw: boolean;
  groups: {
    issue_id: string | null;
    issue_name: string | null;
    identifier: string | null;
    last_at: string;
    days: { date: string; entries: TPHActivityEntry[] }[];
  }[];
  decisions_confirmed: TPHActivityDecision[];
  open_decisions: TPHActivityDecision[];
};

/** UI projection of one package on one day (built from the feed by `adaptActivityFeed`). */
export type TPHActivityGroup = {
  issue_id: string | null;
  package_name?: string | null;
  identifier?: string | null;
  day: string;
  summary: string;
  reasons: string[];
  decision_needed?: boolean;
  responsible_kind?: "human" | "agent" | "system";
  event_count: number;
  first_at: string;
  last_at: string;
  entries: TPHActivityEntry[];
};

export type TPHOverviewItem = {
  issue_id: string;
  identifier: string;
  name: string;
  status: string;
  priority: string | null;
};

export type TPHNextWork = TPHOverviewItem & {
  approved: boolean;
  blocked: boolean;
  blockers: { type: string; id?: string; name?: string }[];
  immediately_executable: boolean;
  reasons: string[];
};

/** `GET P/overview` */
export type TPHOverview = {
  project_id: string;
  packages: Record<"active" | "ready" | "review" | "shipped" | "draft", TPHOverviewItem[]>;
  open_decisions: TPHActivityDecision[];
  next_work: TPHNextWork[];
  priority_source: string;
};

export type TPHNotificationItem = {
  id: string;
  project_id: string | null;
  category: "mention" | "decision_needed" | "blocked" | "review_request" | "technical" | string;
  delivery: "immediate" | "digest";
  count: number;
  title: string;
  target: { type?: string; id?: string; issue_id?: string; conversation_id?: string; url?: string };
  read_at: string | null;
  created_at: string;
  updated_at: string;
};

/** `GET W/notifications/` */
export type TPHNotifications = { targeted: TPHNotificationItem[]; bundled: TPHNotificationItem[] };

export type TPHRetentionCategory = "messages" | "audit" | "run_logs" | "raw_events" | "ai_outputs" | "exports";

export type TPHRetentionPolicy = { category: TPHRetentionCategory | string; retain_days: number | null };
