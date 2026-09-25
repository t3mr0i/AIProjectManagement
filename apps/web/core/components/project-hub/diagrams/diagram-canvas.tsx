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
import { cn } from "@plane/utils";
// local imports
import type { TDiagramSelection, TDiagramViewBox } from "./diagram-utils";
import { CANVAS_H, CANVAS_W, NODE_H, NODE_W, borderPoint, isAmbiguousEdge, nodeBox } from "./diagram-utils";

type Props = {
  semantic: TPHDiagramSemantic;
  layout: TPHDiagramLayout;
  selection: TDiagramSelection | null;
  readOnly: boolean;
  viewBox: TDiagramViewBox;
  onSelect: (selection: TDiagramSelection | null) => void;
  /** Moves change the layout only — never the semantic model. */
  onMove: (id: string, x: number, y: number) => void;
  className?: string;
};

const STEP = 10;
const GRID = 20;

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

/**
 * SVG canvas for a structured diagram: nodes are rounded cards, edges thin lines with arrowheads,
 * the selection has an accent outline. Nodes are focusable buttons: drag with the pointer or move
 * with the arrow keys (Shift = larger steps). Ambiguous edges (no type/label or unclear direction)
 * are dashed and marked "?" — never only by colour.
 */
export function DiagramCanvas({ semantic, layout, selection, readOnly, viewBox, onSelect, onMove, className }: Props) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);

  /** Pointer position in user (viewBox) units, exact under `meet` scaling. */
  const toSvg = (e: PointerEvent) => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return { x: 0, y: 0 };
    const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return { x: point.x, y: point.y };
  };

  const onNodePointerDown = (e: PointerEvent<SVGGElement>, id: string) => {
    e.stopPropagation();
    onSelect({ kind: "node", id });
    if (readOnly) return;
    const p = toSvg(e);
    const box = nodeBox(layout, semantic, id);
    setDrag({ id, dx: p.x - box.x, dy: p.y - box.y, moved: false });
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const p = toSvg(e);
    if (!drag.moved) setDrag({ ...drag, moved: true });
    onMove(
      drag.id,
      Math.round(clamp(p.x - drag.dx, 0, CANVAS_W - NODE_W)),
      Math.round(clamp(p.y - drag.dy, 0, CANVAS_H - NODE_H))
    );
  };

  const onKeyDown = (e: KeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect({ kind: "node", id });
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
    onMove(id, clamp(box.x + d[0], 0, CANVAS_W - NODE_W), clamp(box.y + d[1], 0, CANVAS_H - NODE_H));
  };

  const nodeLabel = (id: string) => semantic.nodes.find((n) => n.id === id)?.label || id;

  return (
    <svg
      ref={svgRef}
      viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
      className={cn("h-auto w-full touch-none rounded-md border border-subtle bg-layer-1 select-none", className)}
      role="group"
      aria-label={t("project_hub.diagram.canvas_label")}
      onPointerDown={(e) => {
        if (e.target === e.currentTarget || (e.target as Element).getAttribute("data-canvas-bg") !== null)
          onSelect(null);
      }}
      onPointerMove={onPointerMove}
      onPointerUp={() => setDrag(null)}
      onPointerLeave={() => setDrag(null)}
    >
      <defs>
        <pattern id="ph-grid" width={GRID} height={GRID} patternUnits="userSpaceOnUse">
          <circle cx={1} cy={1} r={0.75} className="fill-current text-placeholder" fillOpacity={0.3} />
        </pattern>
        <marker id="ph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M1,1 L9,5 L1,9 z" className="fill-current" />
        </marker>
      </defs>
      <rect
        data-canvas-bg=""
        x={viewBox.x - CANVAS_W}
        y={viewBox.y - CANVAS_H}
        width={viewBox.w + CANVAS_W * 2}
        height={viewBox.h + CANVAS_H * 2}
        fill="url(#ph-grid)"
      />
      {semantic.edges.map((edge) => {
        const a = nodeBox(layout, semantic, edge.source);
        const b = nodeBox(layout, semantic, edge.target);
        // Arrows end at the node border, not hidden under the target box.
        const { x: x1, y: y1 } = borderPoint(a, b);
        const { x: x2, y: y2 } = borderPoint(b, a);
        const ambiguous = isAmbiguousEdge(edge);
        const selected = selection?.kind === "edge" && selection.id === edge.id;
        const label = edge.type || edge.label;
        const text = ambiguous ? `? ${label}`.trim() : label;
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        return (
          // oxlint-disable-next-line jsx_a11y/no-static-element-interactions -- SVG group acts as a focusable button
          <g
            key={edge.id}
            // oxlint-disable-next-line jsx_a11y/prefer-tag-over-role -- SVG has no <button> element
            role="button"
            tabIndex={0}
            aria-pressed={selected}
            aria-label={t("project_hub.diagram.select_edge", {
              label: label || t("project_hub.diagram.ambiguous_short"),
              source: nodeLabel(edge.source),
              target: nodeLabel(edge.target),
            })}
            className={cn(
              "cursor-pointer outline-none",
              selected ? "text-accent-primary" : "text-placeholder hover:text-tertiary"
            )}
            onPointerDown={(e) => {
              e.stopPropagation();
              onSelect({ kind: "edge", id: edge.id });
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect({ kind: "edge", id: edge.id });
              }
            }}
          >
            {/* wide transparent hit area */}
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={14} />
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="currentColor"
              strokeWidth={selected ? 1.75 : 1.25}
              strokeDasharray={ambiguous ? "5 4" : undefined}
              markerEnd="url(#ph-arrow)"
            />
            {text && (
              <text
                x={mx}
                y={my - 5}
                textAnchor="middle"
                className={cn("text-[11px]", selected ? "fill-accent-primary" : "fill-tertiary")}
                style={{ paintOrder: "stroke", stroke: "var(--bg-layer-1)", strokeWidth: 4, strokeLinejoin: "round" }}
              >
                {text}
              </text>
            )}
          </g>
        );
      })}
      {semantic.nodes.map((node) => {
        const box = nodeBox(layout, semantic, node.id);
        const selected = selection?.kind === "node" && selection.id === node.id;
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
            className={cn(
              "group/node outline-none",
              readOnly ? "cursor-pointer" : drag?.id === node.id ? "cursor-grabbing" : "cursor-grab"
            )}
            onPointerDown={(e) => onNodePointerDown(e, node.id)}
            onKeyDown={(e) => onKeyDown(e, node.id)}
          >
            {selected && (
              <rect
                x={-3}
                y={-3}
                width={NODE_W + 6}
                height={NODE_H + 6}
                rx={9}
                fill="none"
                stroke="var(--border-accent-strong)"
                strokeOpacity={0.35}
                strokeWidth={1.5}
              />
            )}
            <rect
              width={NODE_W}
              height={NODE_H}
              rx={6}
              fill="var(--bg-layer-2)"
              stroke={selected ? "var(--border-accent-strong)" : "var(--border-subtle)"}
              strokeWidth={1}
              className="group-focus-visible/node:stroke-[var(--border-accent-strong)]"
            />
            <text x={12} y={21} className="fill-primary text-[12px] font-medium">
              {(node.label || node.id).slice(0, 20)}
            </text>
            <text x={12} y={36} className="fill-tertiary text-[10px]">
              {node.type}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
