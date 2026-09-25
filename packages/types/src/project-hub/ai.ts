/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** AI core (status, Ask AI, assist, project report, usage). Shapes follow `package_flow.views.ai`. */

import type { TPHBlockedSource, TPHSourceRef, TPHVisibleSource } from "./collaboration";

export type TPHAIProvider = "openai" | "anthropic" | "gemini" | "ollama" | "openai_compatible";

export type TPHAIFeatures = {
  ask: boolean;
  proposals: boolean;
  report: boolean;
  assist: boolean;
  streaming: boolean;
  semantic_search: boolean;
};

/** `GET W/ai/status` — which AI is active; never contains secrets. */
export type TPHAIStatus = {
  provider: TPHAIProvider | string;
  provider_label: string;
  model: string;
  configured: boolean;
  embeddings: boolean;
  embedding_model: string;
  mode: "llm" | "rule_based";
  features: TPHAIFeatures;
};

export type TPHAIResultStatus = "ok" | "timeout" | "budget_exceeded" | "cancelled" | "error" | "unavailable";

export type TPHAIStatementStatus = "observed" | "confirmed" | "inferred" | "proposed";

export type TPHAIStatement = {
  text: string;
  status: TPHAIStatementStatus | string;
  sources: (TPHSourceRef & Record<string, unknown>)[];
};

/** Structured finding (unverified_claim, missing_evidence, contradiction, …). */
export type TPHAIFlag = { kind: string; [key: string]: unknown };

export type TPHAIUsageTokens = { input_tokens?: number; output_tokens?: number; [key: string]: unknown };

/** Provider-independent result of one AI call. */
export type TPHAIResult = {
  task: string;
  status: TPHAIResultStatus | string;
  statements: TPHAIStatement[];
  provider: string;
  model: string;
  error_code: string;
  error: string;
  usage: TPHAIUsageTokens;
  notes: string[];
  flags: TPHAIFlag[];
  needs_clarification: boolean;
  patch: Record<string, unknown>;
  allowed_actions: string[];
  text: string;
};

export type TPHAIAllowedSource = { ref: TPHSourceRef; title: string | null; confirmed?: boolean; stale?: boolean };

/** Context the AI was allowed to use for the audience (and what was blocked, with reasons). */
export type TPHAIContext = {
  allowed: TPHAIAllowedSource[];
  blocked: TPHBlockedSource[];
  visible: TPHVisibleSource[];
  audience_size: number;
};

export type TPHAIRetrievedRef = { type: string; id: string; retrieved: true };

export type TPHAskRequest = {
  question: string;
  project_ids?: string[];
  selection?: TPHSourceRef[];
};

/** `POST W/ai/ask` — private answer over everything the requester can read. */
export type TPHAskResponse = {
  question: string;
  result: TPHAIResult;
  context: TPHAIContext;
  retrieved: TPHAIRetrievedRef[];
};

export type TPHAssistRequest = { instruction: string; text?: string; project_id?: string };

/** `POST W/ai/assist` */
export type TPHAssistResponse = {
  text: string;
  status: TPHAIResultStatus | string;
  provider: string;
  model: string;
  error_code: string;
  error: string;
};

export type TPHAIUsageRow = { key: string; calls: number; input_tokens: number; output_tokens: number };

/** `GET W/ai/usage?days=` (workspace admins). */
export type TPHAIUsage = {
  days: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  errors: number;
  by_feature: TPHAIUsageRow[];
  by_task: TPHAIUsageRow[];
  by_model: TPHAIUsageRow[];
};

export type TPHAIProposalTask = "concretize" | "interpret" | "report" | "answer";

/** `POST P/proposals/` body. */
export type TPHProposalRequest = {
  task: TPHAIProposalTask;
  issue_id?: string;
  selection?: TPHSourceRef[];
  instruction?: string;
  retrieve?: boolean;
};

/** A criterion in a `concretize` patch (the full new list = existing + new). */
export type TPHAIPatchCriterion = { id?: string; text: string; verification?: string; required?: boolean };
