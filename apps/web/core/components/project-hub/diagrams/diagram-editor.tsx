/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useEffect, useId, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import {
  AddOutline,
  ArrowCollapseOutline,
  ArrowExpandOutline,
  CubeOutline,
  HelpOutline,
  InfoOutline,
  LinkOutline,
  LockOutline,
  SettingsOutline,
  TickCircleOutline,
  WorkflowsOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type {
  TPHDiagramDetail,
  TPHDiagramEdge,
  TPHDiagramLayout,
  TPHDiagramSemantic,
  TPHDiagramUpdateResult,
  TPHProposal,
  TProjectHubApiError,
} from "@plane/types";
import { cn, getProjectHubErrorKind, toProjectHubApiError } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { HubChip } from "../common/chip";
import { useProjectHubCapabilities } from "../common/gate";
import { HubSelect } from "../common/select";
import { HubSidebarCard } from "../common/sidebar-card";
import { HubConflictBanner, HubNotice, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { DiagramCanvas } from "./diagram-canvas";
import type { TDiagramSelection, TDiagramViewBox } from "./diagram-utils";
import { DEFAULT_VIEW_BOX, diffCounts, fitViewBox, isAmbiguousEdge, newId, nodeBox } from "./diagram-utils";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const DIRECTIONS = ["forward", "both", "unknown"] as const;

type TProps = { workspaceSlug: string; projectId: string; diagramId: string };

/* -------------------------------------------------------------------------------------------------
 * Pending interpretation
 * -----------------------------------------------------------------------------------------------*/

/** Compact card: interpretation, questions, suggested criteria (selectable), accept/reject. */
const DiagramProposalCard = observer(function DiagramProposalCard({
  workspaceSlug,
  projectId,
  diagramId,
  proposal,
  hasPackage,
  onDecided,
}: TProps & { proposal: TPHProposal; hasPackage: boolean; onDecided: () => void }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const content = proposal.content;
  const criteria = content.suggested_criteria ?? [];
  const questions = content.questions ?? [];
  const statements = content.statements ?? [];
  const impacts = content.possible_impacts ?? [];
  const [selected, setSelected] = useState<string[]>(criteria.map((c) => c.edge_id));
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);

  const decide = async (action: "accept" | "reject") => {
    setBusy(action);
    try {
      if (action === "accept") {
        await store.knowledgeService.acceptDiagramProposal(workspaceSlug, projectId, diagramId, proposal.id, selected);
        showHubSuccessToast(t("project_hub.diagram.accepted"));
      } else {
        await store.knowledgeService.rejectDiagramProposal(workspaceSlug, projectId, diagramId, proposal.id);
        showHubSuccessToast(t("project_hub.proposals.rejected"));
      }
      onDecided();
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const canDecide = has("package.edit") && proposal.status === "pending";

  return (
    <section
      aria-label={t("project_hub.diagram.pending_interpretation")}
      className="flex min-w-0 flex-col overflow-hidden rounded-md border border-subtle bg-layer-1"
    >
      <div className="flex h-8 min-w-0 items-center gap-1.5 bg-layer-2 pr-2 pl-3">
        <HelpOutline className="size-4 shrink-0 text-tertiary" aria-hidden="true" />
        <span className="truncate text-13 font-medium text-primary">
          {t("project_hub.diagram.pending_interpretation")}
        </span>
        <HubChip
          variant="soft"
          tone="info"
          label={t(`project_hub.proposals.status.${proposal.status}`)}
          className="ml-1"
        />
        {content.uncertainty && (
          <HubChip
            variant="soft"
            tone={content.uncertainty.level === "high" ? "warning" : "neutral"}
            label={t("project_hub.diagram.uncertainty", {
              level: t(`project_hub.brief.risk_levels.${content.uncertainty.level}`),
            })}
          />
        )}
        <span className="hidden min-w-0 flex-1 truncate text-caption-md-regular text-tertiary md:inline">
          {t("project_hub.diagram.not_a_requirement")}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        {content.interpretation && <p className="text-13 text-primary">{content.interpretation}</p>}
        {statements.length > 0 && (
          <ul className="flex flex-col gap-1 text-13 text-secondary">
            {statements.map((s, i) => (
              // oxlint-disable-next-line react/no-array-index-key -- statements have no id
              <li key={i} className="flex items-start gap-2">
                {s.kind && (
                  <HubChip variant="soft" label={t(`project_hub.proposals.statement.${s.kind}`)} className="mt-px" />
                )}
                <span className="min-w-0">{s.text}</span>
              </li>
            ))}
          </ul>
        )}
        {questions.length > 0 && (
          <div className="flex flex-col gap-1">
            <p className="text-caption-md-medium text-tertiary">{t("project_hub.diagram.questions")}</p>
            <ul className="flex flex-col">
              {questions.map((q) => (
                <li key={q.edge_id} className="flex min-h-7 items-center gap-2 text-13 text-primary">
                  <HelpOutline className="size-3.5 shrink-0 text-warning-primary" aria-hidden="true" />
                  <span className="min-w-0">{q.text}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {criteria.length > 0 && (
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-caption-md-medium text-tertiary">
              {t("project_hub.diagram.suggested_criteria")}
            </legend>
            {criteria.map((c) => (
              <label key={c.edge_id} className="flex min-h-7 items-center gap-2 text-13 text-secondary">
                <Checkbox
                  checked={selected.includes(c.edge_id)}
                  disabled={!canDecide}
                  onCheckedChange={(v) =>
                    setSelected((prev) => (v ? [...prev, c.edge_id] : prev.filter((x) => x !== c.edge_id)))
                  }
                />
                <span className="min-w-0">{c.text}</span>
              </label>
            ))}
          </fieldset>
        )}
        {impacts.length > 0 && (
          <details className="text-caption-md-regular text-secondary">
            <summary className="cursor-pointer text-tertiary hover:text-primary">
              {t("project_hub.diagram.impacts")} <span className="text-placeholder">{impacts.length}</span>
            </summary>
            <ul className="mt-1 list-inside list-disc">
              {impacts.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          </details>
        )}
        {!hasPackage && <HubNotice icon={InfoOutline as TGlyph} title={t("project_hub.diagram.needs_package")} />}
        {canDecide && (
          <div className="flex items-center justify-end gap-1.5 border-t border-subtle pt-3">
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              loading={busy === "reject"}
              disabled={!!busy}
              label={t("project_hub.common.reject")}
              onClick={() => void decide("reject")}
            />
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              loading={busy === "accept"}
              disabled={!hasPackage || !!busy}
              label={t("project_hub.diagram.accept")}
              onClick={() => void decide("accept")}
            />
          </div>
        )}
      </div>
    </section>
  );
});

/* -------------------------------------------------------------------------------------------------
 * Inspector rows
 * -----------------------------------------------------------------------------------------------*/

/** Labelled text field for the inspector (framed input, 12px muted label). */
function InspectorField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-caption-md-medium text-tertiary">
        {label}
      </label>
      <InputGroup size="md">
        <Input id={id} size="md" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      </InputGroup>
    </div>
  );
}

/** One selectable row in the Nodes / Edges sidebar cards (28px, quiet). */
function ItemRow({
  icon: Glyph,
  title,
  meta,
  selected,
  onClick,
  "aria-label": ariaLabel,
}: {
  icon: TGlyph;
  title: string;
  meta?: string;
  selected: boolean;
  onClick: () => void;
  "aria-label"?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={ariaLabel}
      onClick={onClick}
      className={cn(
        "flex h-7 w-full min-w-0 items-center gap-1.5 px-3 text-left text-13 transition-colors duration-100 hover:bg-layer-transparent-hover focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none focus-visible:ring-inset",
        selected ? "bg-layer-transparent-selected text-primary" : "text-secondary"
      )}
    >
      <Glyph
        className={cn("size-3.5 shrink-0", selected ? "text-accent-primary" : "text-tertiary")}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {meta && <span className="shrink-0 text-caption-md-regular text-tertiary">{meta}</span>}
    </button>
  );
}

/* -------------------------------------------------------------------------------------------------
 * Editor
 * -----------------------------------------------------------------------------------------------*/

/**
 * S08 structured diagram editor (FR-E02/E03): a calm canvas with a toolbar row, a right inspector
 * (properties of the selected node or edge, node and edge lists). Moving a node changes only the
 * layout. Saving shows whether the change was layout-only or semantic; a semantic change yields a
 * pending interpretation proposal that a human accepts or rejects (it never creates a revision or
 * approval).
 */
export const DiagramEditor = observer(function DiagramEditor({ workspaceSlug, projectId, diagramId }: TProps) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const key = `ph:diagram:${diagramId}`;
  const detail = useHubResource<TPHDiagramDetail>(key, () =>
    store.knowledgeService.getDiagram(workspaceSlug, projectId, diagramId)
  );
  const [semantic, setSemantic] = useState<TPHDiagramSemantic>({ nodes: [], edges: [] });
  const [layout, setLayout] = useState<TPHDiagramLayout>({});
  const [version, setVersion] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [selection, setSelection] = useState<TDiagramSelection | null>(null);
  const [viewBox, setViewBox] = useState<TDiagramViewBox>(DEFAULT_VIEW_BOX);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<TPHDiagramUpdateResult | null>(null);
  const [error, setError] = useState<TProjectHubApiError | null>(null);
  const readOnly = !has("package.edit");

  const loaded = detail.data;
  useEffect(() => {
    if (!loaded) return;
    setSemantic({ nodes: loaded.semantic.nodes ?? [], edges: loaded.semantic.edges ?? [] });
    setLayout(loaded.layout ?? {});
    setVersion(loaded.version);
    setDirty(false);
  }, [loaded]);

  const editSemantic = (fn: (s: TPHDiagramSemantic) => TPHDiagramSemantic) => {
    setSemantic(fn);
    setDirty(true);
  };
  const updateNode = (id: string, patch: Partial<TPHDiagramSemantic["nodes"][number]>) =>
    editSemantic((s) => ({ ...s, nodes: s.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) }));
  const updateEdge = (id: string, patch: Partial<TPHDiagramEdge>) =>
    editSemantic((s) => ({ ...s, edges: s.edges.map((e) => (e.id === id ? { ...e, ...patch } : e)) }));

  const addNode = () => {
    const id = newId("n");
    editSemantic((s) => ({
      ...s,
      nodes: [...s.nodes, { id, type: "component", label: t("project_hub.diagram.new_node"), properties: {} }],
    }));
    setSelection({ kind: "node", id });
  };
  const removeNode = (id: string) => {
    editSemantic((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
    }));
    setSelection(null);
  };
  const addEdge = () => {
    if (semantic.nodes.length < 2) return;
    // Start from the selected node when there is one, otherwise from the first two nodes.
    const from = selection?.kind === "node" ? selection.id : semantic.nodes[0]!.id;
    const to = semantic.nodes.find((n) => n.id !== from)!.id;
    const id = newId("e");
    editSemantic((s) => ({
      ...s,
      edges: [...s.edges, { id, source: from, target: to, type: "", label: "", properties: {} }],
    }));
    setSelection({ kind: "edge", id });
  };
  const removeEdge = (id: string) => {
    editSemantic((s) => ({ ...s, edges: s.edges.filter((e) => e.id !== id) }));
    setSelection(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      // Positions for all nodes so the server stores a complete layout.
      const fullLayout: TPHDiagramLayout = {};
      for (const n of semantic.nodes) fullLayout[n.id] = { ...nodeBox(layout, semantic, n.id), ...layout[n.id] };
      const res = await store.knowledgeService.updateDiagram(workspaceSlug, projectId, diagramId, {
        semantic,
        layout: fullLayout,
        expected_version: version,
      });
      setResult(res);
      setVersion(res.diagram.version);
      setDirty(false);
      store.invalidate(key);
      store.invalidate(`ph:diagrams:${workspaceSlug}:${projectId}`);
    } catch (err) {
      const e = toProjectHubApiError(err);
      setError(e);
      if (getProjectHubErrorKind(e) !== "conflict") showHubErrorToast(t, e);
    } finally {
      setSaving(false);
    }
  };

  const counts = diffCounts(result?.semantic_diff);
  const pending = (loaded?.proposals ?? []).filter((p) => p.status === "pending");
  const nodeOptions = semantic.nodes.map((n) => ({ value: n.id, label: n.label || n.id }));
  const nodeLabel = (id: string) => semantic.nodes.find((n) => n.id === id)?.label || id;
  const selectedNode = selection?.kind === "node" ? semantic.nodes.find((n) => n.id === selection.id) : undefined;
  const selectedEdge = selection?.kind === "edge" ? semantic.edges.find((e) => e.id === selection.id) : undefined;
  const isFitted = viewBox !== DEFAULT_VIEW_BOX;

  const resultNotice = result && (
    <HubNotice
      role="status"
      icon={(!result.changed ? InfoOutline : result.layout_only ? TickCircleOutline : WorkflowsOutline) as TGlyph}
      title={
        !result.changed
          ? t("project_hub.diagram.no_change")
          : result.layout_only
            ? t("project_hub.diagram.layout_only")
            : t("project_hub.diagram.semantic_change")
      }
      description={
        counts && result.changed && !result.layout_only
          ? t("project_hub.diagram.diff_summary", {
              nodesAdded: counts.nodes.added,
              nodesRemoved: counts.nodes.removed,
              nodesChanged: counts.nodes.changed,
              edgesAdded: counts.edges.added,
              edgesRemoved: counts.edges.removed,
              edgesChanged: counts.edges.changed,
            })
          : undefined
      }
      onDismiss={() => setResult(null)}
    />
  );

  return (
    <HubResourceBoundary resource={detail} loadingRows={4}>
      {(data) => (
        <div className="flex min-w-0 flex-col gap-3">
          {error && getProjectHubErrorKind(error) === "conflict" && (
            <HubConflictBanner
              onReload={() => {
                setError(null);
                setResult(null);
                store.invalidate(key);
              }}
            />
          )}
          {readOnly && <HubNotice icon={LockOutline as TGlyph} title={t("project_hub.diagram.read_only")} />}

          {/* Toolbar */}
          <div
            role="toolbar"
            aria-label={t("project_hub.diagram.toolbar_label")}
            className="flex h-9 min-w-0 items-center gap-1 rounded-md border border-subtle bg-layer-1 px-1.5"
          >
            {!readOnly && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  icon={<Icon icon={AddOutline} />}
                  label={t("project_hub.diagram.node")}
                  aria-label={t("project_hub.diagram.add_node")}
                  onClick={addNode}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  icon={<Icon icon={LinkOutline} />}
                  label={t("project_hub.diagram.edge")}
                  aria-label={t("project_hub.diagram.add_edge")}
                  disabled={semantic.nodes.length < 2}
                  onClick={addEdge}
                />
                <span className="mx-0.5 h-4 border-l border-subtle" aria-hidden="true" />
              </>
            )}
            <Tooltip label={isFitted ? t("project_hub.diagram.zoom_reset") : t("project_hub.diagram.zoom_fit")}>
              <IconButton
                variant="ghost"
                size="sm"
                aria-label={isFitted ? t("project_hub.diagram.zoom_reset") : t("project_hub.diagram.zoom_fit")}
                icon={<Icon icon={isFitted ? ArrowCollapseOutline : ArrowExpandOutline} />}
                disabled={semantic.nodes.length === 0}
                onClick={() => setViewBox(isFitted ? DEFAULT_VIEW_BOX : fitViewBox(layout, semantic))}
              />
            </Tooltip>
            <span className="flex-1" />
            <span className="hidden truncate text-caption-md-regular text-tertiary sm:inline">
              {t("project_hub.diagram.version", { version })}
              {" · "}
              {t("project_hub.diagram.counts", { nodes: semantic.nodes.length, edges: semantic.edges.length })}
            </span>
            {dirty && !readOnly && <HubChip variant="soft" tone="warning" label={t("project_hub.diagram.unsaved")} />}
            {!readOnly && (
              <Button
                variant="primary"
                size="sm"
                stretch="auto"
                loading={saving}
                disabled={!dirty}
                label={t("project_hub.common.save")}
                onClick={() => void save()}
              />
            )}
          </div>

          {resultNotice}

          {/* Canvas + inspector */}
          <div className="flex min-w-0 flex-col gap-3 @3xl:flex-row @3xl:items-start">
            <div className="relative min-w-0 flex-1">
              <DiagramCanvas
                semantic={semantic}
                layout={layout}
                selection={selection}
                readOnly={readOnly}
                viewBox={viewBox}
                onSelect={setSelection}
                onMove={(id, x, y) => {
                  setLayout((l) => ({ ...l, [id]: { ...l[id], x, y } }));
                  setDirty(true);
                }}
              />
              {semantic.nodes.length === 0 && (
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-center">
                  <WorkflowsOutline className="size-5 text-placeholder" aria-hidden="true" />
                  <p className="text-13 text-tertiary">{t("project_hub.diagram.canvas_empty")}</p>
                </div>
              )}
              <p className="mt-1.5 truncate px-0.5 text-caption-sm-regular text-tertiary">
                {t("project_hub.diagram.canvas_help")}
              </p>
            </div>

            <aside className="flex w-full shrink-0 flex-col gap-3 @3xl:w-72">
              <HubSidebarCard
                title={t("project_hub.diagram.properties")}
                icon={SettingsOutline as TGlyph}
                body="content"
              >
                {selectedNode ? (
                  <>
                    <div className="flex items-center gap-1.5">
                      <HubChip variant="soft" icon={CubeOutline as TGlyph} label={t("project_hub.diagram.node")} />
                      <span className="font-mono truncate text-caption-sm-regular text-placeholder">
                        {selectedNode.id}
                      </span>
                    </div>
                    <InspectorField
                      label={t("project_hub.diagram.label")}
                      value={selectedNode.label}
                      disabled={readOnly}
                      onChange={(v) => updateNode(selectedNode.id, { label: v })}
                    />
                    <InspectorField
                      label={t("project_hub.diagram.type")}
                      value={selectedNode.type}
                      disabled={readOnly}
                      onChange={(v) => updateNode(selectedNode.id, { type: v })}
                    />
                    {!readOnly && (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          stretch="auto"
                          label={t("project_hub.common.remove")}
                          aria-label={t("project_hub.diagram.remove_node", {
                            label: selectedNode.label || selectedNode.id,
                          })}
                          onClick={() => removeNode(selectedNode.id)}
                        />
                      </div>
                    )}
                  </>
                ) : selectedEdge ? (
                  <>
                    <div className="flex items-center gap-1.5">
                      <HubChip variant="soft" icon={LinkOutline as TGlyph} label={t("project_hub.diagram.edge")} />
                      {isAmbiguousEdge(selectedEdge) && (
                        <HubChip
                          variant="soft"
                          tone="warning"
                          icon={HelpOutline as TGlyph}
                          label={t("project_hub.diagram.ambiguous_short")}
                        />
                      )}
                    </div>
                    <HubSelect
                      label={t("project_hub.diagram.source")}
                      value={selectedEdge.source}
                      disabled={readOnly}
                      options={nodeOptions}
                      onChange={(v) => updateEdge(selectedEdge.id, { source: v })}
                    />
                    <HubSelect
                      label={t("project_hub.diagram.target")}
                      value={selectedEdge.target}
                      disabled={readOnly}
                      options={nodeOptions}
                      onChange={(v) => updateEdge(selectedEdge.id, { target: v })}
                    />
                    <InspectorField
                      label={t("project_hub.diagram.type")}
                      value={selectedEdge.type}
                      disabled={readOnly}
                      onChange={(v) => updateEdge(selectedEdge.id, { type: v })}
                    />
                    <InspectorField
                      label={t("project_hub.diagram.label")}
                      value={selectedEdge.label}
                      disabled={readOnly}
                      onChange={(v) => updateEdge(selectedEdge.id, { label: v })}
                    />
                    <HubSelect
                      label={t("project_hub.diagram.direction")}
                      value={String(selectedEdge.properties?.direction ?? "forward")}
                      disabled={readOnly}
                      options={DIRECTIONS.map((d) => ({ value: d, label: t(`project_hub.diagram.directions.${d}`) }))}
                      onChange={(v) =>
                        updateEdge(selectedEdge.id, {
                          properties: { ...selectedEdge.properties, direction: v === "forward" ? undefined : v },
                        })
                      }
                    />
                    {isAmbiguousEdge(selectedEdge) && (
                      <p className="flex items-start gap-1.5 text-caption-md-regular text-tertiary">
                        <HelpOutline className="mt-0.5 size-3.5 shrink-0 text-warning-primary" aria-hidden="true" />
                        {t("project_hub.diagram.ambiguous_edge")}
                      </p>
                    )}
                    {!readOnly && (
                      <div className="flex justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          stretch="auto"
                          label={t("project_hub.common.remove")}
                          aria-label={t("project_hub.diagram.remove_edge")}
                          onClick={() => removeEdge(selectedEdge.id)}
                        />
                      </div>
                    )}
                  </>
                ) : (
                  <p className="py-2 text-center text-caption-md-regular text-tertiary">
                    {t("project_hub.diagram.inspector_empty")}
                  </p>
                )}
              </HubSidebarCard>

              <HubSidebarCard
                title={t("project_hub.diagram.nodes")}
                icon={CubeOutline as TGlyph}
                trailing={
                  <>
                    <span className="text-caption-md-regular text-tertiary">{semantic.nodes.length}</span>
                    {!readOnly && (
                      <IconButton
                        variant="ghost"
                        size="xs"
                        aria-label={t("project_hub.diagram.add_node")}
                        icon={<Icon icon={AddOutline} />}
                        onClick={addNode}
                      />
                    )}
                  </>
                }
              >
                {semantic.nodes.length === 0 ? (
                  <p className="px-3 py-1 text-caption-md-regular text-tertiary">
                    {t("project_hub.diagram.canvas_empty")}
                  </p>
                ) : (
                  semantic.nodes.map((node) => (
                    <ItemRow
                      key={node.id}
                      icon={CubeOutline as TGlyph}
                      title={node.label || node.id}
                      meta={node.type}
                      selected={selection?.kind === "node" && selection.id === node.id}
                      onClick={() => setSelection({ kind: "node", id: node.id })}
                    />
                  ))
                )}
              </HubSidebarCard>

              <HubSidebarCard
                title={t("project_hub.diagram.edges")}
                icon={LinkOutline as TGlyph}
                trailing={
                  <>
                    <span className="text-caption-md-regular text-tertiary">{semantic.edges.length}</span>
                    {!readOnly && (
                      <IconButton
                        variant="ghost"
                        size="xs"
                        aria-label={t("project_hub.diagram.add_edge")}
                        icon={<Icon icon={AddOutline} />}
                        disabled={semantic.nodes.length < 2}
                        onClick={addEdge}
                      />
                    )}
                  </>
                }
              >
                {semantic.edges.length === 0 ? (
                  <p className="px-3 py-1 text-caption-md-regular text-tertiary">{t("project_hub.common.none")}</p>
                ) : (
                  semantic.edges.map((edge) => {
                    const ambiguous = isAmbiguousEdge(edge);
                    const label = edge.type || edge.label;
                    return (
                      <ItemRow
                        key={edge.id}
                        icon={(ambiguous ? HelpOutline : LinkOutline) as TGlyph}
                        title={t("project_hub.diagram.edge_label", {
                          source: nodeLabel(edge.source),
                          target: nodeLabel(edge.target),
                        })}
                        meta={label || (ambiguous ? t("project_hub.diagram.ambiguous_short") : undefined)}
                        selected={selection?.kind === "edge" && selection.id === edge.id}
                        aria-label={t("project_hub.diagram.select_edge", {
                          label: label || t("project_hub.diagram.ambiguous_short"),
                          source: nodeLabel(edge.source),
                          target: nodeLabel(edge.target),
                        })}
                        onClick={() => setSelection({ kind: "edge", id: edge.id })}
                      />
                    );
                  })
                )}
              </HubSidebarCard>
            </aside>
          </div>

          {pending.map((p) => (
            <DiagramProposalCard
              key={p.id}
              workspaceSlug={workspaceSlug}
              projectId={projectId}
              diagramId={diagramId}
              proposal={p}
              hasPackage={!!data.issue_id}
              onDecided={() => {
                setResult(null);
                store.invalidate(key);
                if (data.issue_id) store.invalidateIssue(data.issue_id);
              }}
            />
          ))}
        </div>
      )}
    </HubResourceBoundary>
  );
});
