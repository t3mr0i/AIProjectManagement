/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { KeyboardEvent, PointerEvent } from "react";
import { useRef, useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHDiagramLayout, TPHDiagramSemantic } from "@plane/types";
// local imports
import { NODE_H, NODE_W, borderPoint, isAmbiguousEdge, nodeBox } from "./diagram-utils";

type Props = {
  semantic: TPHDiagramSemantic;
  layout: TPHDiagramLayout;
  selectedId: string | null;
  readOnly: boolean;
  onSelect: (id: string | null) => void;
  /** Moves change the layout only — never the semantic model. */
  onMove: (id: string, x: number, y: number) => void;
};

const WIDTH = 880;
const HEIGHT = 480;
const STEP = 10;

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

/**
 * SVG canvas for a structured diagram. Nodes are focusable buttons: drag with the pointer or move
 * with the arrow keys (Shift = larger steps). Ambiguous edges (no type/label or unclear direction)
 * are dashed and marked "?" — never only by color.
 */
export function DiagramCanvas({ semantic, layout, selectedId, readOnly, onSelect, onMove }: Props) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number } | null>(null);

  const toSvg = (e: PointerEvent) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * WIDTH, y: ((e.clientY - rect.top) / rect.height) * HEIGHT };
  };

  const onPointerDown = (e: PointerEvent<SVGGElement>, id: string) => {
    onSelect(id);
    if (readOnly) return;
    const p = toSvg(e);
    const box = nodeBox(layout, semantic, id);
    setDrag({ id, dx: p.x - box.x, dy: p.y - box.y });
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const p = toSvg(e);
    onMove(
      drag.id,
      Math.round(clamp(p.x - drag.dx, 0, WIDTH - NODE_W)),
      Math.round(clamp(p.y - drag.dy, 0, HEIGHT - NODE_H))
    );
  };

  const onKeyDown = (e: KeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id);
      return;
    }
    if (readOnly) return;
    const step = e.shiftKey ? STEP * 5 : STEP;
    const box = nodeBox(layout, semantic, id);
    const delta: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const d = delta[e.key];
    if (!d) return;
    e.preventDefault();
    onMove(id, clamp(box.x + d[0], 0, WIDTH - NODE_W), clamp(box.y + d[1], 0, HEIGHT - NODE_H));
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-auto w-full touch-none rounded-md border border-subtle bg-layer-1"
      role="group"
      aria-label={t("project_hub.diagram.canvas_label")}
      onPointerMove={onPointerMove}
      onPointerUp={() => setDrag(null)}
      onPointerLeave={() => setDrag(null)}
    >
      <defs>
        <marker id="ph-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" className="fill-current text-tertiary" />
        </marker>
      </defs>
      {semantic.edges.map((edge) => {
        const a = nodeBox(layout, semantic, edge.source);
        const b = nodeBox(layout, semantic, edge.target);
        // Arrows end at the node border, not hidden under the target box.
        const { x: x1, y: y1 } = borderPoint(a, b);
        const { x: x2, y: y2 } = borderPoint(b, a);
        const ambiguous = isAmbiguousEdge(edge);
        const label = edge.type || edge.label;
        return (
          <g key={edge.id} className="text-tertiary">
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="currentColor"
              strokeWidth={2}
              strokeDasharray={ambiguous ? "6 4" : undefined}
              markerEnd="url(#ph-arrow)"
            />
            <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 6} textAnchor="middle" className="fill-current text-[11px]">
              {ambiguous ? `? ${label}` : label}
            </text>
          </g>
        );
      })}
      {semantic.nodes.map((node) => {
        const box = nodeBox(layout, semantic, node.id);
        const selected = selectedId === node.id;
        return (
          // oxlint-disable-next-line jsx_a11y/no-static-element-interactions -- SVG group acts as a focusable button
          <g
            key={node.id}
            // oxlint-disable-next-line jsx_a11y/prefer-tag-over-role -- SVG has no <button> element
            role="button"
            tabIndex={0}
            aria-pressed={selected}
            aria-label={t("project_hub.diagram.node_label", { label: node.label || node.id, type: node.type })}
            transform={`translate(${box.x} ${box.y})`}
            className={`cursor-move outline-none focus-visible:[&>rect]:stroke-[4] ${selected ? "text-accent-primary" : "text-secondary"}`}
            onPointerDown={(e) => onPointerDown(e, node.id)}
            onKeyDown={(e) => onKeyDown(e, node.id)}
          >
            <rect
              width={NODE_W}
              height={NODE_H}
              rx={6}
              fill="currentColor"
              fillOpacity={selected ? 0.14 : 0.06}
              stroke="currentColor"
              strokeWidth={selected ? 3 : 1.5}
            />
            <text x={NODE_W / 2} y={20} textAnchor="middle" className="fill-current text-[12px] font-medium">
              {(node.label || node.id).slice(0, 20)}
            </text>
            <text x={NODE_W / 2} y={36} textAnchor="middle" className="fill-current text-[10px] text-tertiary">
              {node.type}
              {selected ? " ✓" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
