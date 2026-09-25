/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { LockOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type {
  TPHDateConfidence,
  TPHDependency,
  TPHGraphNode,
  TPHRoadmap,
  TPHScenario,
  TPHScenarioImpact,
  TProjectHubApiError,
} from "@plane/types";
import {
  cn,
  computeTimelineWindow,
  getDependencyCyclePath,
  getProjectHubErrorMessageKey,
  getTimelinePosition,
  toProjectHubApiError,
} from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubCard, HubSection } from "../common/section";
import { HubSelect } from "../common/select";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TSelectableNode = { key: string; type: "issue" | "milestone"; id: string; label: string };

type Props = {
  workspaceSlug: string;
  /** Fixed project scope (project roadmap). Without it the user can filter projects. */
  fixedProjectId?: string;
};

const isExternal = (node: TPHGraphNode | undefined) => !node || node.type === "external_blocker";

/**
 * Multi-project roadmap (S10, J09): timeline + accessible table view, milestones, package dates,
 * dependencies (confirmed solid vs suggested dashed + label), redacted external prerequisites,
 * scenarios with read-only impact before apply, cycle errors with path and "no reliable date".
 */
export const RoadmapView = observer(function RoadmapView({ workspaceSlug, fixedProjectId }: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { joinedProjectIds, getPartialProjectById } = useProject();
  const { formatDate } = useHubFormatters();
  const { has } = useProjectHubCapabilities(workspaceSlug, fixedProjectId);
  const canPlan = has("project.plan");

  const [view, setView] = useState<"timeline" | "table">("timeline");
  const [projectFilter, setProjectFilter] = useState<string[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const projectIds = useMemo(
    () => (fixedProjectId ? [fixedProjectId] : projectFilter),
    [fixedProjectId, projectFilter]
  );
  const params = useMemo(
    () => ({
      ...(projectIds.length ? { project_ids: projectIds.join(",") } : {}),
      ...(from ? { from } : {}),
      ...(to ? { to } : {}),
    }),
    [projectIds, from, to]
  );
  const roadmap = useHubResource<TPHRoadmap>(PH_KEYS.roadmap(workspaceSlug, JSON.stringify(params)), () =>
    store.planningService.getRoadmap(workspaceSlug, params)
  );

  // dialogs
  const [dialog, setDialog] = useState<"milestone" | "dependency" | "scenario" | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<TProjectHubApiError | null>(null);
  const [msName, setMsName] = useState("");
  const [msDate, setMsDate] = useState("");
  const [msConfidence, setMsConfidence] = useState<TPHDateConfidence>("estimated");
  const [depFrom, setDepFrom] = useState<string | null>(null);
  const [depTo, setDepTo] = useState<string | null>(null);
  const [scName, setScName] = useState("");
  const [scMilestone, setScMilestone] = useState<string | null>(null);
  const [scDate, setScDate] = useState("");
  const [scenario, setScenario] = useState<TPHScenario | null>(null);
  const [impact, setImpact] = useState<TPHScenarioImpact | null>(null);

  const refreshRoadmap = () => store.invalidate(`ph:roadmap:${workspaceSlug}:`);

  /** All nodes that may be connected by a dependency: milestones and packages of visible projects. */
  const selectable = useMemo(() => {
    const data = roadmap.data;
    const out: TSelectableNode[] = [];
    if (!data) return out;
    for (const m of data.milestones)
      out.push({ key: `milestone:${m.id}`, type: "milestone", id: m.id, label: `◆ ${m.name}` });
    for (const p of data.packages)
      out.push({ key: `issue:${p.id}`, type: "issue", id: p.id, label: p.label || p.name });
    return out;
  }, [roadmap.data]);

  const graphNodes = useMemo(() => new Map((roadmap.data?.nodes ?? []).map((n) => [n.key, n])), [roadmap.data]);

  const nodeLabel = (key: string | undefined) => {
    const node = key ? graphNodes.get(key) : undefined;
    if (isExternal(node)) return t("project_hub.roadmap.external_prerequisite");
    return (
      node?.label ?? selectable.find((n) => n.key === key)?.label ?? t("project_hub.roadmap.external_prerequisite")
    );
  };

  const closeDialog = () => {
    setDialog(null);
    setDialogError(null);
    setScenario(null);
    setImpact(null);
  };

  const createMilestone = async () => {
    if (!fixedProjectId || !msName.trim()) return;
    setBusy(true);
    try {
      await store.planningService.createMilestone(workspaceSlug, fixedProjectId, {
        name: msName.trim(),
        target_at: msDate ? `${msDate}T12:00:00` : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        date_confidence: msDate ? msConfidence : "unknown",
      });
      showHubSuccessToast(t("project_hub.roadmap.created"));
      setMsName("");
      setMsDate("");
      closeDialog();
      refreshRoadmap();
    } catch (error) {
      setDialogError(toProjectHubApiError(error));
    } finally {
      setBusy(false);
    }
  };

  const createDependency = async () => {
    const a = selectable.find((n) => n.key === depFrom);
    const b = selectable.find((n) => n.key === depTo);
    if (!a || !b) return;
    setBusy(true);
    setDialogError(null);
    try {
      await store.planningService.createDependency(workspaceSlug, {
        predecessor_type: a.type,
        predecessor_id: a.id,
        successor_type: b.type,
        successor_id: b.id,
        strength: "hard",
      });
      closeDialog();
      refreshRoadmap();
    } catch (error) {
      // 422 DEPENDENCY_CYCLE → the cycle path (redacted labels) is shown in the dialog.
      setDialogError(toProjectHubApiError(error));
    } finally {
      setBusy(false);
    }
  };

  const confirmDependency = async (dep: TPHDependency) => {
    try {
      await store.planningService.confirmDependency(workspaceSlug, dep.id);
      refreshRoadmap();
    } catch (error) {
      showHubErrorToast(t, error);
    }
  };

  const createScenario = async () => {
    if (!scMilestone || !scName.trim()) return;
    setBusy(true);
    setDialogError(null);
    try {
      const created = await store.planningService.createScenario(workspaceSlug, {
        name: scName.trim(),
        changes: [{ type: "milestone", id: scMilestone, target_at: scDate ? `${scDate}T12:00:00` : null }],
      });
      setScenario(created);
      setImpact(await store.planningService.getScenarioImpact(workspaceSlug, created.id));
    } catch (error) {
      setDialogError(toProjectHubApiError(error));
    } finally {
      setBusy(false);
    }
  };

  const applyScenario = async () => {
    if (!scenario) return;
    setBusy(true);
    try {
      await store.planningService.applyScenario(workspaceSlug, scenario.id);
      showHubSuccessToast(t("project_hub.roadmap.scenario_applied"));
      closeDialog();
      refreshRoadmap();
    } catch (error) {
      setDialogError(toProjectHubApiError(error));
    } finally {
      setBusy(false);
    }
  };

  const milestoneOptions = (roadmap.data?.milestones ?? []).map((m) => ({ value: m.id, label: m.name }));
  const nodeOptions = selectable.map((n) => ({ value: n.key, label: n.label }));
  const cyclePath = getDependencyCyclePath(dialogError);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label={t("project_hub.roadmap.title")} className="flex gap-1">
          {(["timeline", "table"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={cn(
                "focus-visible:outline-accent-primary rounded-md border px-2.5 py-1 text-body-xs-medium focus-visible:outline-2 focus-visible:outline-offset-2",
                view === v
                  ? "border-accent-strong bg-accent-subtle text-accent-primary"
                  : "border-subtle text-secondary hover:bg-layer-1"
              )}
            >
              {view === v ? "✓ " : ""}
              {v === "timeline" ? t("project_hub.roadmap.timeline_view") : t("project_hub.roadmap.table_view")}
            </button>
          ))}
        </div>
        <HubTextField type="date" label={t("project_hub.activity.from")} value={from} onChange={setFrom} />
        <HubTextField type="date" label={t("project_hub.activity.to")} value={to} onChange={setTo} />
        {canPlan && (
          <div className="flex flex-wrap gap-2">
            {fixedProjectId && (
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label={t("project_hub.roadmap.milestone_create")}
                onClick={() => setDialog("milestone")}
              />
            )}
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label={t("project_hub.roadmap.dependency_create")}
              onClick={() => setDialog("dependency")}
            />
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label={t("project_hub.roadmap.scenario_create")}
              onClick={() => setDialog("scenario")}
            />
          </div>
        )}
      </div>
      {!fixedProjectId && (
        <fieldset className="flex flex-wrap gap-3">
          <legend className="sr-only">{t("project_hub.roadmap.project_filter")}</legend>
          {joinedProjectIds.map((pid) => (
            <label key={pid} className="flex items-center gap-1.5 text-body-xs-regular text-secondary">
              <Checkbox
                checked={projectFilter.includes(pid)}
                onCheckedChange={(c) =>
                  setProjectFilter((prev) => (c ? [...prev, pid] : prev.filter((p) => p !== pid)))
                }
              />
              {getPartialProjectById(pid)?.name ?? pid}
            </label>
          ))}
        </fieldset>
      )}

      <HubResourceBoundary
        resource={roadmap}
        loadingRows={5}
        isEmpty={(d) => d.milestones.length === 0 && d.packages.length === 0}
        empty={<HubEmpty title={t("project_hub.roadmap.milestones_empty")} />}
      >
        {(data) => {
          const dates = [
            ...data.milestones.map((m) => m.target_at),
            ...data.packages.flatMap((p) => [p.start_date, p.target_date]),
          ];
          const window = computeTimelineWindow(dates);
          const todayPos = getTimelinePosition(new Date().toISOString(), window);
          const unplannedMilestones = data.milestones.filter((m) => !m.reliable_date);
          const unplannedPackages = data.packages.filter((p) => !p.reliable_date);
          const redacted = data.nodes.filter((n) => n.type === "external_blocker");
          return (
            <div className="flex flex-col gap-5">
              {view === "timeline" ? (
                <div className="flex flex-col gap-1 overflow-x-auto">
                  <div className="relative ml-40 h-6 min-w-[480px] border-b border-subtle text-caption-sm-regular text-tertiary">
                    <span className="absolute left-0">{formatDate(new Date(window.start))}</span>
                    <span className="absolute right-0">{formatDate(new Date(window.end))}</span>
                    {todayPos !== null && (
                      <span
                        className="absolute -translate-x-1/2 font-medium text-primary"
                        style={{ left: `${todayPos}%` }}
                      >
                        ▼ {t("project_hub.roadmap.today")}
                      </span>
                    )}
                  </div>
                  {data.projects.map((project) => {
                    const ms = data.milestones.filter((m) => m.project_id === project.id && m.reliable_date);
                    const pkgs = data.packages.filter((p) => p.project_id === project.id && p.reliable_date);
                    return (
                      <div key={project.id} className="flex min-w-[640px] items-stretch border-b border-subtle py-2">
                        <div className="w-40 shrink-0 pr-2 text-body-xs-medium text-primary">{project.name}</div>
                        <div className="relative min-h-14 flex-1">
                          {todayPos !== null && (
                            <div
                              className="absolute inset-y-0 w-px bg-accent-primary"
                              style={{ left: `${todayPos}%` }}
                              aria-hidden="true"
                            />
                          )}
                          {pkgs.map((p, i) => {
                            const start = getTimelinePosition(p.start_date ?? p.target_date, window) ?? 0;
                            const end = getTimelinePosition(p.target_date, window) ?? start;
                            return (
                              <div
                                key={p.id}
                                className="absolute truncate rounded-sm border border-subtle bg-layer-2 px-1 text-caption-sm-regular text-secondary"
                                style={{
                                  left: `${start}%`,
                                  width: `${Math.max(end - start, 2)}%`,
                                  top: `${(i % 2) * 18}px`,
                                }}
                                title={`${p.label || p.name} · ${formatDate(p.start_date)} – ${formatDate(p.target_date)}`}
                              >
                                {p.label || p.name}
                              </div>
                            );
                          })}
                          {ms.map((m) => (
                            <div
                              key={m.id}
                              className="absolute -translate-x-1/2 text-caption-sm-medium whitespace-nowrap text-primary"
                              style={{ left: `${getTimelinePosition(m.target_at, window) ?? 0}%`, bottom: 0 }}
                              title={`${m.name} · ${formatDate(m.target_at)} · ${t(`project_hub.roadmap.confidence.${m.date_confidence}`)}`}
                            >
                              ◆ {m.name}
                              {m.date_confidence === "estimated" &&
                                ` (${t("project_hub.roadmap.confidence.estimated")})`}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-body-xs-regular">
                    <caption className="sr-only">{t("project_hub.roadmap.title")}</caption>
                    <thead>
                      <tr className="border-b border-subtle text-tertiary">
                        <th scope="col" className="py-1.5 pr-3 font-medium">
                          {t("project_hub.roadmap.milestone_name")}
                        </th>
                        <th scope="col" className="py-1.5 pr-3 font-medium">
                          {t("project_hub.common.project")}
                        </th>
                        <th scope="col" className="py-1.5 pr-3 font-medium">
                          {t("project_hub.roadmap.target_date")}
                        </th>
                        <th scope="col" className="py-1.5 font-medium">
                          {t("project_hub.roadmap.confidence_label")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.milestones.map((m) => (
                        <tr key={m.id} className="border-b border-subtle">
                          <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                            ◆ {m.name}
                          </th>
                          <td className="py-1.5 pr-3 text-secondary">
                            {data.projects.find((p) => p.id === m.project_id)?.name ?? "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-secondary">
                            {m.reliable_date ? formatDate(m.target_at) : t("project_hub.roadmap.no_reliable_date")}
                          </td>
                          <td className="py-1.5 text-secondary">
                            {t(`project_hub.roadmap.confidence.${m.date_confidence}`)}
                          </td>
                        </tr>
                      ))}
                      {data.packages.map((p) => (
                        <tr key={p.id} className="border-b border-subtle">
                          <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                            {p.label || p.name}
                          </th>
                          <td className="py-1.5 pr-3 text-secondary">
                            {data.projects.find((pr) => pr.id === p.project_id)?.name ?? "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-secondary">
                            {p.reliable_date
                              ? `${p.start_date ? formatDate(p.start_date) : t("project_hub.common.unknown")} – ${formatDate(p.target_date)}`
                              : t("project_hub.roadmap.no_reliable_date")}
                          </td>
                          <td className="py-1.5 text-secondary">{p.state_group ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(unplannedMilestones.length > 0 || unplannedPackages.length > 0) && (
                <HubSection title={t("project_hub.roadmap.unplanned")}>
                  <ul className="flex flex-wrap gap-2">
                    {unplannedMilestones.map((m) => (
                      <li key={m.id}>
                        <ToneBadge
                          tone="neutral"
                          size="xs"
                          label={`◆ ${m.name} · ${t("project_hub.roadmap.no_reliable_date")}`}
                        />
                      </li>
                    ))}
                    {unplannedPackages.map((p) => (
                      <li key={p.id}>
                        <ToneBadge
                          tone="neutral"
                          size="xs"
                          label={`${p.label || p.name} · ${t("project_hub.roadmap.no_reliable_date")}`}
                        />
                      </li>
                    ))}
                  </ul>
                </HubSection>
              )}

              <HubSection title={t("project_hub.roadmap.dependencies")}>
                {data.dependencies.length === 0 ? (
                  <HubEmpty title={t("project_hub.roadmap.dependencies_empty")} />
                ) : (
                  <ul className="flex flex-col gap-2">
                    {data.dependencies.map((dep) => {
                      const confirmed = dep.confirmation === "confirmed";
                      const external = dep.style === "external";
                      return (
                        <li
                          key={dep.id}
                          className={cn(
                            "flex flex-wrap items-center gap-2 rounded-md border-2 px-3 py-2 text-body-xs-regular",
                            confirmed ? "border-solid border-subtle" : "border-dashed border-subtle"
                          )}
                        >
                          <span className="inline-flex items-center gap-1 text-primary">
                            {external && <Icon icon={LockOutline} tint="tertiary" />}
                            {nodeLabel(dep.source_key)}
                          </span>
                          <span aria-hidden="true" className="text-tertiary">
                            {confirmed ? "━━▶" : "┅┅▷"}
                          </span>
                          <span className="sr-only">
                            {t("project_hub.roadmap.predecessor")} → {t("project_hub.roadmap.successor")}
                          </span>
                          <span className="text-primary">{nodeLabel(dep.target_key)}</span>
                          <ToneBadge
                            tone={confirmed ? "success" : "warning"}
                            size="xs"
                            label={
                              confirmed
                                ? t("project_hub.roadmap.dependency_confirmed")
                                : t("project_hub.roadmap.dependency_suggested")
                            }
                          />
                          <span className="text-caption-sm-regular text-tertiary">
                            {dep.blocking ? t("project_hub.roadmap.hard") : t("project_hub.roadmap.soft")}
                            {dep.source ? ` · ${dep.source}` : ""}
                          </span>
                          {!confirmed && !external && canPlan && dep.confirmation === "suggested" && (
                            <Button
                              variant="secondary"
                              size="sm"
                              stretch="auto"
                              label={t("project_hub.roadmap.confirm_dependency")}
                              onClick={() => void confirmDependency(dep)}
                            />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                {redacted.length > 0 && (
                  <ul className="flex flex-wrap gap-2">
                    {redacted.map((n) => (
                      <li key={n.key}>
                        <ToneBadge
                          tone="neutral"
                          size="xs"
                          icon={LockOutline}
                          label={t("project_hub.roadmap.external_prerequisite")}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </HubSection>
            </div>
          );
        }}
      </HubResourceBoundary>

      <HubDialog
        isOpen={dialog === "milestone"}
        onClose={closeDialog}
        isBusy={busy}
        title={t("project_hub.roadmap.milestone_create")}
        onSubmit={() => void createMilestone()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={closeDialog}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy}
              disabled={!msName.trim()}
              label={t("project_hub.common.create")}
            />
          </>
        }
      >
        <HubTextField label={t("project_hub.roadmap.milestone_name")} value={msName} required onChange={setMsName} />
        <HubTextField type="date" label={t("project_hub.roadmap.target_date")} value={msDate} onChange={setMsDate} />
        <HubSelect
          label={t("project_hub.roadmap.confidence_label")}
          value={msConfidence}
          onChange={(v) => setMsConfidence(v as TPHDateConfidence)}
          options={(["confirmed", "estimated", "unknown"] as const).map((v) => ({
            value: v,
            label: t(`project_hub.roadmap.confidence.${v}`),
          }))}
        />
        {dialogError && (
          <p role="alert" className="text-body-xs-regular text-danger-primary">
            {t(getProjectHubErrorMessageKey(dialogError))}
          </p>
        )}
      </HubDialog>

      <HubDialog
        isOpen={dialog === "dependency"}
        onClose={closeDialog}
        isBusy={busy}
        title={t("project_hub.roadmap.dependency_create")}
        onSubmit={() => void createDependency()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={closeDialog}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy}
              disabled={!depFrom || !depTo || depFrom === depTo}
              label={t("project_hub.common.create")}
            />
          </>
        }
      >
        <HubSelect
          label={t("project_hub.roadmap.predecessor")}
          value={depFrom}
          onChange={setDepFrom}
          options={nodeOptions}
        />
        <HubSelect label={t("project_hub.roadmap.successor")} value={depTo} onChange={setDepTo} options={nodeOptions} />
        {dialogError && (
          <div role="alert" className="flex flex-col gap-1 text-body-xs-regular text-danger-primary">
            <p>{t(getProjectHubErrorMessageKey(dialogError))}</p>
            {cyclePath.length > 0 && <p>{t("project_hub.roadmap.cycle_error", { path: cyclePath.join(" → ") })}</p>}
          </div>
        )}
      </HubDialog>

      <HubDialog
        isOpen={dialog === "scenario"}
        onClose={closeDialog}
        isBusy={busy}
        title={t("project_hub.roadmap.scenario_create")}
        onSubmit={() => void (scenario ? applyScenario() : createScenario())}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={closeDialog}
            />
            {scenario ? (
              <Button
                type="submit"
                variant="primary"
                size="md"
                stretch="auto"
                loading={busy}
                disabled={!canPlan}
                label={t("project_hub.roadmap.apply_scenario")}
              />
            ) : (
              <Button
                type="submit"
                variant="primary"
                size="md"
                stretch="auto"
                loading={busy}
                disabled={!scMilestone || !scName.trim()}
                label={t("project_hub.roadmap.impact")}
              />
            )}
          </>
        }
      >
        <p className="text-caption-sm-regular text-tertiary">{t("project_hub.roadmap.scenario_hint")}</p>
        {!scenario && (
          <>
            <HubTextField label={t("project_hub.roadmap.scenario_name")} value={scName} required onChange={setScName} />
            <HubSelect
              label={t("project_hub.roadmap.scenario_item")}
              value={scMilestone}
              onChange={setScMilestone}
              options={milestoneOptions}
            />
            <HubTextField
              type="date"
              label={t("project_hub.roadmap.scenario_new_date")}
              value={scDate}
              onChange={setScDate}
            />
          </>
        )}
        {impact && (
          <HubCard className="flex flex-col gap-2">
            <p className="text-caption-md-medium text-tertiary">{t("project_hub.roadmap.impact")}</p>
            <ul className="flex flex-col gap-1 text-body-xs-regular text-secondary">
              {impact.changes.map((c) => (
                <li key={c.id}>
                  ◆ {c.label ?? c.id}: {formatDate(c.current_target_at)} → {formatDate(c.new_target_at)}
                </li>
              ))}
            </ul>
            {impact.affected.length === 0 ? (
              <p className="text-body-xs-regular text-secondary">{t("project_hub.roadmap.impact_empty")}</p>
            ) : (
              <ul className="flex flex-col gap-1 text-body-xs-regular text-secondary">
                {impact.affected.map((a) => (
                  <li key={a.key}>
                    {a.label} ·{" "}
                    {a.current_target === null
                      ? t("project_hub.roadmap.no_reliable_date")
                      : a.would_be_late
                        ? t("project_hub.roadmap.late_by", {
                            hours: a.shift_hours,
                            date: formatDate(a.projected_target),
                          })
                        : t("project_hub.roadmap.not_late")}
                    <span className="text-tertiary">
                      {" "}
                      — {t("project_hub.roadmap.via", { path: a.via.join(" → ") })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-caption-sm-regular text-tertiary">{t("project_hub.roadmap.impact_basis_deps")}</p>
          </HubCard>
        )}
        {dialogError && (
          <p role="alert" className="text-body-xs-regular text-danger-primary">
            {t(getProjectHubErrorMessageKey(dialogError))}
          </p>
        )}
      </HubDialog>
    </div>
  );
});
