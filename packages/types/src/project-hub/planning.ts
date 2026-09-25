/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Planning (API §6). Shapes follow the Django serializers. */

export type TPHDateConfidence = "confirmed" | "estimated" | "unknown";

export type TPHMilestone = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  target_at: string | null;
  timezone: string;
  target_local: string | null;
  owner_id: string | null;
  status: "planned" | "at_risk" | "done" | "cancelled";
  issues: string[];
  date_confidence: TPHDateConfidence;
  reliable_date: boolean;
  /** "no reliable date" label when not reliable */
  date_label: string | null;
};

export type TPHMilestoneCreate = {
  name: string;
  target_at: string | null;
  timezone: string;
  owner_id?: string | null;
  issues?: string[];
  date_confidence: TPHDateConfidence;
  description?: string;
};

export type TPHNodeType = "issue" | "milestone" | "project";

export type TPHNodeRef = { type: TPHNodeType; id: string; project_id: string | null; label?: string };

/** Graph node; `external_blocker` is the redacted "External prerequisite open" node (AC25). */
export type TPHGraphNode =
  | {
      key: string;
      type: TPHNodeType;
      id: string;
      project_id: string | null;
      label: string;
      start?: string | null;
      target?: string | null;
    }
  | { key: string; type: "external_blocker"; label: string };

export type TPHDependencyStyle = "hard" | "soft" | "suggested" | "external";

/** Visible dependency edge (also `serialize_dependency`). Redacted edges only carry keys + style `external`. */
export type TPHDependency = {
  id: string;
  source_key?: string;
  target_key?: string;
  predecessor?: TPHNodeRef;
  successor?: TPHNodeRef;
  strength: "hard" | "soft";
  confirmation: "suggested" | "confirmed" | "rejected";
  source?: "human" | "ai" | "native_relation" | "import" | string;
  /** Only confirmed hard dependencies block. */
  blocking: boolean;
  style: TPHDependencyStyle;
  allow_anonymous_blocker?: boolean;
  note?: string;
  confirmed_by?: string | null;
};

/** `GET W/dependencies/` → redacted graph. */
export type TPHDependencyGraph = { nodes: TPHGraphNode[]; edges: TPHDependency[] };

export type TPHDependencyCreate = {
  predecessor_type: TPHNodeType;
  predecessor_id: string;
  successor_type: TPHNodeType;
  successor_id: string;
  strength?: "hard" | "soft";
  note?: string;
};

export type TPHRoadmapPackage = {
  id: string;
  work_item_id: string;
  project_id: string;
  label: string;
  name: string;
  state_group: string | null;
  start_date: string | null;
  target_date: string | null;
  start_label: "unknown" | null;
  target_label: "unknown" | null;
  reliable_date: boolean;
};

export type TPHRoadmapCycle = {
  id: string;
  project_id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  read_only: true;
};

export type TPHRoadmapModule = {
  id: string;
  project_id: string;
  name: string;
  status: string;
  start_date: string | null;
  target_date: string | null;
  read_only: true;
};

/** `GET W/roadmap/?project_ids=&team_id=&from=&to=&tz=` */
export type TPHRoadmap = {
  projects: { id: string; name: string; identifier: string; team_ids: string[] }[];
  milestones: TPHMilestone[];
  packages: TPHRoadmapPackage[];
  cycles: TPHRoadmapCycle[];
  modules: TPHRoadmapModule[];
  dependencies: TPHDependency[];
  nodes: TPHGraphNode[];
  filters: { project_ids: string[]; team_id: string | null; from: string | null; to: string | null };
};

export type TPHScenarioChange = {
  type: "milestone";
  id: string;
  target_at: string | null;
  project_id?: string;
  date_confidence?: TPHDateConfidence;
};

export type TPHScenario = {
  id: string;
  name: string;
  changes: TPHScenarioChange[];
  status: "draft" | "applied" | "discarded";
  applied_by: string | null;
  created_by: string | null;
};

export type TPHScenarioAffected = {
  key: string;
  type: TPHNodeType;
  id: string;
  project_id: string | null;
  label: string;
  current_target: string | null;
  current_start: string | null;
  depth: number;
  direct: boolean;
  via: string[];
  dependency_strength: "hard" | "soft";
  would_be_affected: true;
  would_be_late: boolean;
  projected_target: string | null;
  shift_hours: number;
  projected_target_label?: string;
};

/** `GET W/scenarios/{id}/impact` — read only, never modifies the plan. */
export type TPHScenarioImpact = {
  scenario: TPHScenario;
  changes: (TPHScenarioChange & {
    label: string | null;
    current_target_at: string | null;
    new_target_at: string | null;
  })[];
  affected: TPHScenarioAffected[];
  modifies_plan: false;
};

export type TPHScenarioApplied = { scenario: TPHScenario; applied: unknown; successors_changed: unknown[] };

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
