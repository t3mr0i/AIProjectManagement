/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { CloseOutline } from "@makeplane/propel/icons";
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
import { getProjectHubErrorKind, toProjectHubApiError } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { useProjectHubCapabilities } from "../common/gate";
import { HubTextField } from "../common/field";
import { HubCard, HubSection } from "../common/section";
import { HubSelect } from "../common/select";
import { HubConflictBanner, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { DiagramCanvas } from "./diagram-canvas";
import { diffCounts, isAmbiguousEdge, newId, nodeBox } from "./diagram-utils";

const DIRECTIONS = ["forward", "both", "unknown"] as const;

type TProps = { workspaceSlug: string; projectId: string; diagramId: string };

/** Pending interpretation proposal: interpretation, questions, suggested criteria (selectable), accept/reject. */
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
    <HubCard className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge tone="info" size="xs" label={t(`project_hub.proposals.status.${proposal.status}`)} />
        {content.uncertainty && (
          <ToneBadge
            tone={content.uncertainty.level === "high" ? "warning" : "neutral"}
            size="xs"
            label={t("project_hub.diagram.uncertainty", {
              level: t(`project_hub.brief.risk_levels.${content.uncertainty.level}`),
            })}
          />
        )}
        <span className="text-caption-sm-regular text-tertiary">{t("project_hub.diagram.not_a_requirement")}</span>
      </div>
      {content.interpretation && <p className="text-body-xs-regular text-primary">{content.interpretation}</p>}
      {(content.statements ?? []).length > 0 && (
        <ul className="flex flex-col gap-1 text-body-xs-regular text-secondary">
          {(content.statements ?? []).map((s, i) => (
            // oxlint-disable-next-line react/no-array-index-key -- statements have no id
            <li key={i} className="flex items-start gap-2">
              {s.kind && <ToneBadge tone="neutral" size="xs" label={t(`project_hub.proposals.statement.${s.kind}`)} />}
              <span>{s.text}</span>
            </li>
          ))}
        </ul>
      )}
      {(content.questions ?? []).length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-caption-md-medium text-tertiary">{t("project_hub.diagram.questions")}</p>
          <ul className="flex flex-col gap-1 text-body-xs-regular text-primary">
            {(content.questions ?? []).map((q) => (
              <li key={q.edge_id}>? {q.text}</li>
            ))}
          </ul>
        </div>
      )}
      {criteria.length > 0 && (
        <fieldset className="flex flex-col gap-1">
          <legend className="text-caption-md-medium text-tertiary">
            {t("project_hub.diagram.suggested_criteria")}
          </legend>
          {criteria.map((c) => (
            <label key={c.edge_id} className="flex items-start gap-2 text-body-xs-regular text-secondary">
              <Checkbox
                checked={selected.includes(c.edge_id)}
                disabled={!canDecide}
                onCheckedChange={(v) =>
                  setSelected((prev) => (v ? [...prev, c.edge_id] : prev.filter((x) => x !== c.edge_id)))
                }
              />
              <span>{c.text}</span>
            </label>
          ))}
        </fieldset>
      )}
      {(content.possible_impacts ?? []).length > 0 && (
        <details className="text-caption-sm-regular text-secondary">
          <summary className="cursor-pointer text-tertiary">{t("project_hub.diagram.impacts")}</summary>
          <ul className="list-inside list-disc">
            {(content.possible_impacts ?? []).map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </details>
      )}
      {!hasPackage && <p className="text-caption-sm-regular text-tertiary">{t("project_hub.diagram.needs_package")}</p>}
      {canDecide && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            loading={busy === "accept"}
            disabled={!hasPackage || !!busy}
            label={t("project_hub.diagram.accept")}
            onClick={() => void decide("accept")}
          />
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            loading={busy === "reject"}
            disabled={!!busy}
            label={t("project_hub.common.reject")}
            onClick={() => void decide("reject")}
          />
        </div>
      )}
    </HubCard>
  );
});

/**
 * S08 structured diagram editor (FR-E02/E03): nodes/edges edited as accessible lists and on an SVG
 * canvas. Moving a node changes only the layout. Saving shows whether the change was layout-only
 * or semantic; a semantic change yields a pending interpretation proposal that a human accepts or
 * rejects (it never creates a revision or approval).
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
  }, [loaded]);

  const updateNode = (id: string, patch: Partial<TPHDiagramSemantic["nodes"][number]>) =>
    setSemantic((s) => ({ ...s, nodes: s.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) }));
  const updateEdge = (id: string, patch: Partial<TPHDiagramEdge>) =>
    setSemantic((s) => ({ ...s, edges: s.edges.map((e) => (e.id === id ? { ...e, ...patch } : e)) }));

  const addNode = () => {
    const id = newId("n");
    setSemantic((s) => ({
      ...s,
      nodes: [...s.nodes, { id, type: "component", label: t("project_hub.diagram.new_node"), properties: {} }],
    }));
    setSelectedId(id);
  };
  const removeNode = (id: string) =>
    setSemantic((s) => ({
      nodes: s.nodes.filter((n) => n.id !== id),
      edges: s.edges.filter((e) => e.source !== id && e.target !== id),
    }));
  const addEdge = () => {
    if (semantic.nodes.length < 2) return;
    const [a, b] = semantic.nodes;
    setSemantic((s) => ({
      ...s,
      edges: [...s.edges, { id: newId("e"), source: a!.id, target: b!.id, type: "", label: "", properties: {} }],
    }));
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

  return (
    <HubResourceBoundary resource={detail} loadingRows={4}>
      {(data) => (
        <div className="flex flex-col gap-4">
          {error && getProjectHubErrorKind(error) === "conflict" && (
            <HubConflictBanner
              onReload={() => {
                setError(null);
                setResult(null);
                store.invalidate(key);
              }}
            />
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-caption-sm-regular text-tertiary">
              {t("project_hub.diagram.version", { version })} · {t("project_hub.diagram.canvas_help")}
            </p>
            {!readOnly && (
              <Button
                variant="primary"
                size="sm"
                stretch="auto"
                loading={saving}
                label={t("project_hub.common.save")}
                onClick={() => void save()}
              />
            )}
          </div>
          <DiagramCanvas
            semantic={semantic}
            layout={layout}
            selectedId={selectedId}
            readOnly={readOnly}
            onSelect={setSelectedId}
            onMove={(id, x, y) => setLayout((l) => ({ ...l, [id]: { ...l[id], x, y } }))}
          />

          {result && (
            <HubCard className="flex flex-col gap-1">
              <p role="status" className="text-body-xs-medium text-primary">
                {!result.changed
                  ? t("project_hub.diagram.no_change")
                  : result.layout_only
                    ? t("project_hub.diagram.layout_only")
                    : t("project_hub.diagram.semantic_change")}
              </p>
              {counts && result.changed && !result.layout_only && (
                <p className="text-caption-sm-regular text-secondary">
                  {t("project_hub.diagram.diff_summary", {
                    nodesAdded: counts.nodes.added,
                    nodesRemoved: counts.nodes.removed,
                    nodesChanged: counts.nodes.changed,
                    edgesAdded: counts.edges.added,
                    edgesRemoved: counts.edges.removed,
                    edgesChanged: counts.edges.changed,
                  })}
                </p>
              )}
            </HubCard>
          )}

          {pending.length > 0 && (
            <HubSection title={t("project_hub.diagram.pending_interpretation")}>
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
            </HubSection>
          )}

          <div className="grid gap-4 @4xl:grid-cols-2">
            <HubSection
              title={t("project_hub.diagram.nodes")}
              actions={
                !readOnly && (
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    label={t("project_hub.diagram.add_node")}
                    onClick={addNode}
                  />
                )
              }
            >
              <ul className="flex flex-col gap-2">
                {semantic.nodes.map((node) => (
                  <li
                    key={node.id}
                    className={`flex flex-wrap items-end gap-2 rounded-md border p-2 ${selectedId === node.id ? "border-accent-strong" : "border-subtle"}`}
                  >
                    <div className="min-w-32 flex-1">
                      <HubTextField
                        label={t("project_hub.diagram.label")}
                        value={node.label}
                        disabled={readOnly}
                        onChange={(v) => updateNode(node.id, { label: v })}
                      />
                    </div>
                    <div className="w-32">
                      <HubTextField
                        label={t("project_hub.diagram.type")}
                        value={node.type}
                        disabled={readOnly}
                        onChange={(v) => updateNode(node.id, { type: v })}
                      />
                    </div>
                    {!readOnly && (
                      <IconButton
                        variant="ghost"
                        size="md"
                        icon={<Icon icon={CloseOutline} />}
                        aria-label={t("project_hub.diagram.remove_node", { label: node.label || node.id })}
                        onClick={() => removeNode(node.id)}
                      />
                    )}
                  </li>
                ))}
              </ul>
            </HubSection>
            <HubSection
              title={t("project_hub.diagram.edges")}
              actions={
                !readOnly && (
                  <Button
                    variant="secondary"
                    size="sm"
                    stretch="auto"
                    disabled={semantic.nodes.length < 2}
                    label={t("project_hub.diagram.add_edge")}
                    onClick={addEdge}
                  />
                )
              }
            >
              <ul className="flex flex-col gap-2">
                {semantic.edges.map((edge) => (
                  <li key={edge.id} className="flex flex-col gap-2 rounded-md border border-subtle p-2">
                    <div className="flex flex-wrap items-end gap-2">
                      <HubSelect
                        label={t("project_hub.diagram.source")}
                        value={edge.source}
                        disabled={readOnly}
                        options={nodeOptions}
                        onChange={(v) => updateEdge(edge.id, { source: v })}
                      />
                      <span aria-hidden="true" className="pb-1 text-tertiary">
                        →
                      </span>
                      <HubSelect
                        label={t("project_hub.diagram.target")}
                        value={edge.target}
                        disabled={readOnly}
                        options={nodeOptions}
                        onChange={(v) => updateEdge(edge.id, { target: v })}
                      />
                      {!readOnly && (
                        <IconButton
                          variant="ghost"
                          size="md"
                          icon={<Icon icon={CloseOutline} />}
                          aria-label={t("project_hub.diagram.remove_edge")}
                          onClick={() => setSemantic((s) => ({ ...s, edges: s.edges.filter((e) => e.id !== edge.id) }))}
                        />
                      )}
                    </div>
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="w-32">
                        <HubTextField
                          label={t("project_hub.diagram.type")}
                          value={edge.type}
                          disabled={readOnly}
                          onChange={(v) => updateEdge(edge.id, { type: v })}
                        />
                      </div>
                      <div className="min-w-32 flex-1">
                        <HubTextField
                          label={t("project_hub.diagram.label")}
                          value={edge.label}
                          disabled={readOnly}
                          onChange={(v) => updateEdge(edge.id, { label: v })}
                        />
                      </div>
                      <HubSelect
                        label={t("project_hub.diagram.direction")}
                        value={String(edge.properties?.direction ?? "forward")}
                        disabled={readOnly}
                        options={DIRECTIONS.map((d) => ({ value: d, label: t(`project_hub.diagram.directions.${d}`) }))}
                        onChange={(v) =>
                          updateEdge(edge.id, {
                            properties: { ...edge.properties, direction: v === "forward" ? undefined : v },
                          })
                        }
                      />
                    </div>
                    {isAmbiguousEdge(edge) && (
                      <p className="text-caption-sm-regular text-tertiary">
                        ? {t("project_hub.diagram.ambiguous_edge")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </HubSection>
          </div>
        </div>
      )}
    </HubResourceBoundary>
  );
});
