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
  hasReliableDate,
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

type TNode = { key: string; type: "issue" | "milestone" | "project"; id: string; label: string; projectId?: string };

const nodeKey = (type: string, id: string) => `${type}:${id}`;

type Props = {
  workspaceSlug: string;
  /** Fixed project scope (project roadmap). Without it the user can filter projects. */
  fixedProjectId?: string;
};

/**
 * Multi-project roadmap (S10, J09): timeline + accessible table view, milestones, package dates,
 * dependencies (confirmed solid vs suggested dashed + label), redacted external prerequisites,
 * scenarios with impact before apply, cycle errors with path and "no reliable date" handling.
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

  const nodes = useMemo(() => {
    const data = roadmap.data;
    const map = new Map<string, TNode>();
    if (!data) return map;
    for (const p of data.projects)
      map.set(nodeKey("project", p.id), { key: nodeKey("project", p.id), type: "project", id: p.id, label: p.name });
    for (const m of data.milestones)
      map.set(nodeKey("milestone", m.id), {
        key: nodeKey("milestone", m.id),
        type: "milestone",
        id: m.id,
        label: m.name,
        projectId: m.project_id,
      });
    for (const pkg of data.packages) {
      const ident = pkg.project_identifier && pkg.sequence_id ? `${pkg.project_identifier}-${pkg.sequence_id} ` : "";
      map.set(nodeKey("issue", pkg.issue_id), {
        key: nodeKey("issue", pkg.issue_id),
        type: "issue",
        id: pkg.issue_id,
        label: `${ident}${pkg.name}`,
        projectId: pkg.project_id,
      });
    }
    return map;
  }, [roadmap.data]);

  const nodeLabel = (type: string, id: string, redacted?: boolean) =>
    redacted
      ? t("project_hub.roadmap.external_prerequisite")
      : (nodes.get(nodeKey(type, id))?.label ?? t("project_hub.roadmap.external_prerequisite"));

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
        target_at: msDate ? new Date(msDate).toISOString() : null,
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
    const a = depFrom ? nodes.get(depFrom) : undefined;
    const b = depTo ? nodes.get(depTo) : undefined;
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
      // 422 DEPENDENCY_CYCLE → show the cycle path in the dialog
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
        changes: [{ type: "milestone", id: scMilestone, target_at: scDate ? new Date(scDate).toISOString() : null }],
      });
      setScenario(created);
      setImpact(created.impact ?? (await store.planningService.getScenarioImpact(workspaceSlug, created.id)));
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
  const nodeOptions = [...nodes.values()]
    .filter((n) => n.type !== "project")
    .map((n) => ({ value: n.key, label: n.label }));
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
              label={t("project_hub.roadmap.dependencies")}
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
          const unplannedMilestones = data.milestones.filter((m) => !hasReliableDate(m.target_at, m.date_confidence));
          const unplannedPackages = data.packages.filter((p) => !hasReliableDate(p.target_date));
          return (
            <div className="flex flex-col gap-5">
              {view === "timeline" ? (
                <div className="flex flex-col gap-1 overflow-x-auto" aria-hidden={false}>
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
                    const ms = data.milestones.filter(
                      (m) => m.project_id === project.id && hasReliableDate(m.target_at, m.date_confidence)
                    );
                    const pkgs = data.packages.filter(
                      (p) => p.project_id === project.id && hasReliableDate(p.target_date)
                    );
                    return (
                      <div key={project.id} className="flex min-w-[640px] items-stretch border-b border-subtle py-2">
                        <div className="w-40 shrink-0 pr-2 text-body-xs-medium text-primary">{project.name}</div>
                        <div className="relative min-h-8 flex-1">
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
                                key={p.issue_id}
                                className="absolute truncate rounded-sm border border-subtle bg-layer-2 px-1 text-caption-sm-regular text-secondary"
                                style={{
                                  left: `${start}%`,
                                  width: `${Math.max(end - start, 2)}%`,
                                  top: `${(i % 3) * 18}px`,
                                }}
                                title={`${nodeLabel("issue", p.issue_id)} · ${formatDate(p.start_date)} – ${formatDate(p.target_date)}`}
                              >
                                {nodeLabel("issue", p.issue_id)}
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
                            {hasReliableDate(m.target_at, m.date_confidence)
                              ? formatDate(m.target_at)
                              : t("project_hub.roadmap.no_reliable_date")}
                          </td>
                          <td className="py-1.5 text-secondary">
                            {t(`project_hub.roadmap.confidence.${m.date_confidence}`)}
                          </td>
                        </tr>
                      ))}
                      {data.packages.map((p) => (
                        <tr key={p.issue_id} className="border-b border-subtle">
                          <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                            {nodeLabel("issue", p.issue_id)}
                          </th>
                          <td className="py-1.5 pr-3 text-secondary">
                            {data.projects.find((pr) => pr.id === p.project_id)?.name ?? "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-secondary">
                            {hasReliableDate(p.target_date)
                              ? `${formatDate(p.start_date)} – ${formatDate(p.target_date)}`
                              : t("project_hub.roadmap.no_reliable_date")}
                          </td>
                          <td className="py-1.5 text-secondary">{p.phase ? t(`project_hub.phase.${p.phase}`) : "—"}</td>
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
                      <li key={p.issue_id}>
                        <ToneBadge
                          tone="neutral"
                          size="xs"
                          label={`${nodeLabel("issue", p.issue_id)} · ${t("project_hub.roadmap.no_reliable_date")}`}
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
                      return (
                        <li
                          key={dep.id}
                          className={cn(
                            "flex flex-wrap items-center gap-2 rounded-md border-2 px-3 py-2 text-body-xs-regular",
                            confirmed ? "border-solid border-subtle" : "border-dashed border-subtle"
                          )}
                        >
                          <span className="inline-flex items-center gap-1 text-primary">
                            {dep.is_redacted && <Icon icon={LockOutline} tint="tertiary" />}
                            {nodeLabel(dep.predecessor_type, dep.predecessor_id, dep.is_redacted)}
                          </span>
                          <span aria-hidden="true" className="text-tertiary">
                            {confirmed ? "━━▶" : "┅┅▷"}
                          </span>
                          <span className="sr-only">
                            {t("project_hub.roadmap.predecessor")} → {t("project_hub.roadmap.successor")}
                          </span>
                          <span className="text-primary">{nodeLabel(dep.successor_type, dep.successor_id)}</span>
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
                            {dep.strength === "hard" ? t("project_hub.roadmap.hard") : t("project_hub.roadmap.soft")} ·{" "}
                            {dep.source}
                          </span>
                          {!confirmed && canPlan && dep.confirmation === "suggested" && (
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
                {(data.redacted_nodes ?? []).length > 0 && (
                  <ul className="flex flex-wrap gap-2">
                    {(data.redacted_nodes ?? []).map((n) => (
                      <li key={`${n.type}-${n.id}`}>
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
        title={t("project_hub.roadmap.dependencies")}
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
            {cyclePath.length > 0 && (
              <p>
                {t("project_hub.roadmap.cycle_error", {
                  path: cyclePath.map((id) => [...nodes.values()].find((n) => n.id === id)?.label ?? id).join(" → "),
                })}
              </p>
            )}
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
            {impact.affected.length === 0 ? (
              <p className="text-body-xs-regular text-secondary">{t("project_hub.roadmap.impact_empty")}</p>
            ) : (
              <ul className="flex flex-col gap-1 text-body-xs-regular text-secondary">
                {impact.affected.map((a) => (
                  <li key={`${a.type}-${a.id}`}>
                    {a.name ?? nodeLabel(a.type, a.id)}
                    {a.shift_days !== null && a.shift_days !== undefined
                      ? ` · ${t("project_hub.roadmap.shift", { days: a.shift_days })}`
                      : ` · ${t("project_hub.roadmap.no_reliable_date")}`}
                    {a.reason && ` — ${a.reason}`}
                  </li>
                ))}
              </ul>
            )}
            {impact.basis && (
              <p className="text-caption-sm-regular text-tertiary">
                {t("project_hub.roadmap.impact_basis", { basis: impact.basis })}
              </p>
            )}
            {(impact.uncertain ?? []).length > 0 && (
              <p className="text-caption-sm-regular text-tertiary">
                {t("project_hub.roadmap.uncertain")}: {(impact.uncertain ?? []).join(", ")}
              </p>
            )}
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
