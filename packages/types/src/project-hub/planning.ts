/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPackagePhase } from "./package";

/** Planning, specs (API §6). */

export type TPHDateConfidence = "confirmed" | "estimated" | "unknown";

export type TPHMilestone = {
  id: string;
  project_id: string;
  name: string;
  description?: string;
  target_at: string | null;
  timezone: string;
  owner_id: string | null;
  status?: "planned" | "at_risk" | "done" | "cancelled";
  issues: string[];
  date_confidence: TPHDateConfidence;
};

export type TPHMilestoneCreate = {
  name: string;
  target_at: string | null;
  timezone: string;
  owner_id?: string | null;
  issues?: string[];
  date_confidence: TPHDateConfidence;
};

export type TPHNodeType = "issue" | "milestone" | "project";

export type TPHDependency = {
  id: string;
  predecessor_type: TPHNodeType;
  predecessor_id: string;
  predecessor_project_id?: string | null;
  successor_type: TPHNodeType;
  successor_id: string;
  successor_project_id?: string | null;
  strength: "hard" | "soft";
  confirmation: "suggested" | "confirmed" | "rejected";
  source: "human" | "ai" | "native_relation" | "import" | string;
  note?: string;
  /** When the viewer may not see the other side, the server redacts it (label "External prerequisite open"). */
  is_redacted?: boolean;
};

export type TPHDependencyCreate = {
  predecessor_type: TPHNodeType;
  predecessor_id: string;
  successor_type: TPHNodeType;
  successor_id: string;
  strength?: "hard" | "soft";
  note?: string;
};

export type TPHRoadmapPackage = {
  issue_id: string;
  project_id: string;
  name: string;
  sequence_id?: number | null;
  project_identifier?: string | null;
  start_date: string | null;
  target_date: string | null;
  phase?: TPackagePhase | null;
};

export type TPHRoadmapNode = {
  type: TPHNodeType;
  id: string;
  redacted?: boolean;
  label?: string;
};

export type TPHRoadmap = {
  projects: { id: string; name: string; identifier?: string }[];
  milestones: TPHMilestone[];
  packages: TPHRoadmapPackage[];
  dependencies: TPHDependency[];
  redacted_nodes?: TPHRoadmapNode[];
  from?: string | null;
  to?: string | null;
};

export type TPHScenarioChange = { type: "milestone" | "issue"; id: string; target_at: string | null };

export type TPHScenario = {
  id: string;
  name: string;
  changes: TPHScenarioChange[];
  status: "draft" | "applied" | "discarded";
  impact?: TPHScenarioImpact;
};

export type TPHScenarioImpact = {
  affected: { type: TPHNodeType; id: string; name?: string; shift_days?: number | null; reason?: string }[];
  basis?: string;
  uncertain?: string[];
};

export type TPHRisk = {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  origin: "human" | "automatic";
  cause?: { type?: string; id?: string };
  owner_id?: string | null;
};
