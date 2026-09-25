/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPHDiagramEdge, TPHDiagramLayout, TPHDiagramSemantic, TPHDiagramSemanticDiff } from "@plane/types";

export const NODE_W = 140;
export const NODE_H = 48;

/** Same rule as the server (`_is_ambiguous_edge`): no type/label or unclear direction → question. */
const AMBIGUOUS_DIRECTIONS = new Set(["both", "bidirectional", "unknown", "ambiguous", "?"]);

export const isAmbiguousEdge = (edge: TPHDiagramEdge): boolean => {
  if (!edge.type && !edge.label) return true;
  const direction = String((edge.properties ?? {}).direction ?? "").toLowerCase();
  return AMBIGUOUS_DIRECTIONS.has(direction);
};

/** Layout box with a deterministic grid fallback for nodes without stored layout. */
export const nodeBox = (layout: TPHDiagramLayout, semantic: TPHDiagramSemantic, id: string) => {
  const stored = layout[id];
  if (stored && typeof stored.x === "number" && typeof stored.y === "number") return { x: stored.x, y: stored.y };
  const index = Math.max(
    0,
    semantic.nodes.findIndex((n) => n.id === id)
  );
  return { x: 30 + (index % 4) * 210, y: 30 + Math.floor(index / 4) * 110 };
};

type TPoint = { x: number; y: number };

/** Where the line from the centre of box `from` towards the centre of box `to` leaves `from`. */
export const borderPoint = (from: TPoint, to: TPoint): TPoint => {
  const cx = from.x + NODE_W / 2;
  const cy = from.y + NODE_H / 2;
  const dx = to.x + NODE_W / 2 - cx;
  const dy = to.y + NODE_H / 2 - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };
  const scale = 1 / Math.max(Math.abs(dx) / (NODE_W / 2), Math.abs(dy) / (NODE_H / 2));
  return { x: cx + dx * scale, y: cy + dy * scale };
};

export const newId = (prefix: string) =>
  `${prefix}-${typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID().slice(0, 8) : Date.now().toString(36)}`;

export const diffCounts = (diff: TPHDiagramSemanticDiff | Record<string, never> | undefined) => {
  if (!diff || !("nodes" in diff)) return null;
  return {
    nodes: { added: diff.nodes.added.length, removed: diff.nodes.removed.length, changed: diff.nodes.changed.length },
    edges: { added: diff.edges.added.length, removed: diff.edges.removed.length, changed: diff.edges.changed.length },
  };
};
