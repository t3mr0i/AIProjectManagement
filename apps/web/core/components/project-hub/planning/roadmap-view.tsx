/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Popover, PopoverContent, PopoverTrigger } from "@makeplane/propel/components/popover";
import {
  AddOutline,
  CalendarOutline,
  CircleDashedOutline,
  CloseOutline,
  CubeOutline,
  DependencyOutline,
  DiamondOutline,
  FilterOutline,
  LockOutline,
  MilestoneOutline,
  ProjectsOutline,
  TableLayoutOutline,
  TickCircleOutline,
  TimelineLayoutOutline,
  WorkflowsOutline,
} from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import type {
  TLogoProps,
  TPHDateConfidence,
  TPHDependency,
  TPHGraphNode,
  TPHMilestone,
  TPHRoadmap,
  TPHRoadmapPackage,
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
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubSelect } from "../common/select";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

type TSelectableNode = { key: string; type: "issue" | "milestone"; id: string; label: string };

type Props = {
  workspaceSlug: string;
  /** Fixed project scope (project roadmap). Without it the user can filter projects. */
  fixedProjectId?: string;
  /** Document title (browser tab). */
  title: string;
};

const isExternal = (node: TPHGraphNode | undefined) => !node || node.type === "external_blocker";

const DAY_MS = 86_400_000;
const ROW_H = 36;
const LEFT_W = 260;
const MIN_CANVAS_W = 720;

/** One timeline row: a milestone (diamond) or a package (bar). */
type TTimelineRow =
  | { key: string; kind: "milestone"; item: TPHMilestone; start: number; end: number }
  | { key: string; kind: "package"; item: TPHRoadmapPackage; start: number; end: number };

/* -------------------------------------------------------------------------------------------------
 * Scale helpers (month labels, week ticks)
 * -----------------------------------------------------------------------------------------------*/

const monthSegments = (start: number, end: number) => {
  const out: { at: number; label: Date }[] = [];
  const cursor = new Date(start);
  cursor.setDate(1);
  cursor.setHours(0, 0, 0, 0);
  while (cursor.getTime() <= end) {
    out.push({ at: cursor.getTime(), label: new Date(cursor) });
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return out;
};

const weekTicks = (start: number, end: number) => {
  const out: number[] = [];
  const cursor = new Date(start);
  cursor.setHours(0, 0, 0, 0);
  // Move to the next Monday.
  cursor.setDate(cursor.getDate() + ((8 - cursor.getDay()) % 7 || 7));
  while (cursor.getTime() < end) {
    out.push(cursor.getTime());
    cursor.setDate(cursor.getDate() + 7);
  }
  return out;
};

const pct = (ms: number, window: { start: number; end: number }) =>
  Math.min(100, Math.max(0, ((ms - window.start) / (window.end - window.start)) * 100));

/** Bordered text/date field for popovers and the side panel (the bare propel Input has no frame). */
function PanelField({
  label,
  value,
  onChange,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "date";
  required?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-caption-md-medium text-tertiary">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-full rounded-md border border-subtle bg-layer-1 px-2.5 text-13 text-primary transition-colors duration-100 outline-none placeholder:text-placeholder focus:border-accent-strong"
      />
    </div>
  );
}

/** Project glyph: the project's emoji/icon, or a neutral outline when none is set. */
function ProjectGlyph({ logo, size = 16 }: { logo: TLogoProps | undefined; size?: number }) {
  if (logo?.in_use) return <Logo logo={logo} size={size} />;
  return (
    <ProjectsOutline className="shrink-0 text-tertiary" style={{ width: size, height: size }} aria-hidden="true" />
  );
}

/** Width of the timeline canvas in px (dependency lines are drawn in px on top of it). */
const useMeasuredWidth = () => {
  const [width, setWidth] = useState(0);
  const ref = useCallback((node: HTMLDivElement | null) => {
    if (!node) return;
    setWidth(node.getBoundingClientRect().width);
    const resizeObserver = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    resizeObserver.observe(node);
  }, []);
  return { ref, width };
};

/** Orthogonal connector from the end of one bar to the start of another (px). */
const connectorPath = (sx: number, sy: number, tx: number, ty: number) => {
  const gap = 10;
  if (tx >= sx + gap * 2) {
    const mid = sx + gap;
    return `M${sx},${sy} H${mid} V${ty} H${tx}`;
  }
  const midY = sy + (ty > sy ? ROW_H / 2 : -ROW_H / 2);
  return `M${sx},${sy} H${sx + gap} V${midY} H${tx - gap} V${ty} H${tx}`;
};

/* -------------------------------------------------------------------------------------------------
 * Compact side panel (scenario)
 * -----------------------------------------------------------------------------------------------*/

function SidePanel({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <aside
      aria-label={title}
      className="flex w-full shrink-0 flex-col border-subtle bg-layer-1 md:w-80 md:border-l lg:w-96"
    >
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-subtle pr-2 pl-4">
        <WorkflowsOutline className="size-4 shrink-0 text-tertiary" aria-hidden="true" />
        <h2 className="min-w-0 flex-1 truncate text-13 font-medium text-primary">{title}</h2>
        <IconButton
          variant="ghost"
          size="sm"
          aria-label={t("project_hub.common.close")}
          icon={<Icon icon={CloseOutline} />}
          onClick={onClose}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">{children}</div>
      <div className="flex shrink-0 items-center justify-end gap-1.5 border-t border-subtle px-3 py-2">{footer}</div>
    </aside>
  );
}

/** Date helpers bound to the locale (month labels for the scale + the shared date format). */
const useRoadmapFormatters = () => {
  const { currentLocale } = useTranslation();
  const { formatDate } = useHubFormatters();
  const currentLocaleFormat = (date: Date, options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(currentLocale, options).format(date);
  return { formatDate, currentLocaleFormat };
};

/* -------------------------------------------------------------------------------------------------
 * Roadmap
 * -----------------------------------------------------------------------------------------------*/

/**
 * Multi-project roadmap (S10, J09): Linear-style timeline (month/week scale, "Today" marker, left
 * project list, rounded bars) + accessible table view, milestones, package dates, dependencies
 * (confirmed solid vs suggested dashed + label), redacted external prerequisites, scenarios with
 * read-only impact in a side panel before apply, cycle errors with path and "no reliable date".
 */
export const RoadmapView = observer(function RoadmapView({ workspaceSlug, fixedProjectId, title }: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { joinedProjectIds, getPartialProjectById } = useProject();
  const { formatDate, currentLocaleFormat } = useRoadmapFormatters();
  const { has } = useProjectHubCapabilities(workspaceSlug, fixedProjectId);
  const canPlan = has("project.plan");
  const listRef = useRef<HTMLDivElement>(null);
  const onListKeyDown = useHubListNavigation(listRef);
  const canvas = useMeasuredWidth();

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

  // dialogs / panel
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
  const projectName = (id: string | null | undefined) =>
    (id && (roadmap.data?.projects.find((p) => p.id === id)?.name ?? getPartialProjectById(id)?.name)) || "—";
  const showProjectChip = !fixedProjectId;

  /* ---------------------------------- header controls ---------------------------------- */

  const rangeLabel =
    from || to
      ? `${from ? formatDate(from) : "…"} – ${to ? formatDate(to) : "…"}`
      : t("project_hub.roadmap.range_auto");

  const rangeControl = (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={t("project_hub.activity.range")}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md px-2 text-13 transition-colors duration-100 hover:bg-layer-transparent-hover focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
              from || to ? "text-primary" : "text-secondary"
            )}
          >
            <CalendarOutline className="size-3.5 shrink-0 text-tertiary" aria-hidden="true" />
            <span className="hidden sm:inline">{rangeLabel}</span>
          </button>
        }
      />
      <PopoverContent variant="rich" side="bottom" align="end">
        <div className="flex w-64 flex-col gap-3">
          <PanelField type="date" label={t("project_hub.activity.from")} value={from} onChange={setFrom} />
          <PanelField type="date" label={t("project_hub.activity.to")} value={to} onChange={setTo} />
          {(from || to) && (
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              label={t("project_hub.roadmap.range_clear")}
              onClick={() => {
                setFrom("");
                setTo("");
              }}
            />
          )}
        </div>
      </PopoverContent>
    </Popover>
  );

  const projectControl = !fixedProjectId && (
    <Popover>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={t("project_hub.roadmap.project_filter")}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded-md px-2 text-13 transition-colors duration-100 hover:bg-layer-transparent-hover focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
              projectFilter.length ? "text-primary" : "text-secondary"
            )}
          >
            <FilterOutline className="size-3.5 shrink-0 text-tertiary" aria-hidden="true" />
            <span className="hidden sm:inline">
              {projectFilter.length
                ? t("project_hub.roadmap.projects_selected", { count: projectFilter.length })
                : t("project_hub.roadmap.all_projects")}
            </span>
          </button>
        }
      />
      <PopoverContent variant="rich" side="bottom" align="end">
        <fieldset className="flex w-56 flex-col gap-1">
          <legend className="pb-1 text-caption-md-medium text-tertiary">
            {t("project_hub.roadmap.project_filter")}
          </legend>
          {joinedProjectIds.map((pid) => {
            const project = getPartialProjectById(pid);
            return (
              <label
                key={pid}
                className="flex h-7 items-center gap-2 rounded-sm px-1 text-13 text-primary hover:bg-layer-transparent-hover"
              >
                <Checkbox
                  checked={projectFilter.includes(pid)}
                  onCheckedChange={(c) =>
                    setProjectFilter((prev) => (c ? [...prev, pid] : prev.filter((p) => p !== pid)))
                  }
                />
                <ProjectGlyph logo={project?.logo_props} size={14} />
                <span className="truncate">{project?.name ?? pid}</span>
              </label>
            );
          })}
        </fieldset>
      </PopoverContent>
    </Popover>
  );

  const actions = canPlan ? (
    <>
      {fixedProjectId && (
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          icon={<Icon icon={MilestoneOutline} />}
          label={t("project_hub.roadmap.milestone")}
          onClick={() => setDialog("milestone")}
        />
      )}
      <Button
        variant="ghost"
        size="sm"
        stretch="auto"
        icon={<Icon icon={DependencyOutline} />}
        label={t("project_hub.roadmap.dependency")}
        onClick={() => setDialog("dependency")}
      />
      <Button
        variant="secondary"
        size="sm"
        stretch="auto"
        icon={<Icon icon={AddOutline} />}
        label={t("project_hub.roadmap.scenario")}
        onClick={() => setDialog("scenario")}
      />
    </>
  ) : undefined;

  /* ---------------------------------- render helpers ---------------------------------- */

  const renderItemRowLeft = (row: TTimelineRow) => {
    const identifier = row.kind === "package" ? row.item.label.split(" ")[0] : undefined;
    const name = row.kind === "package" ? row.item.name : row.item.name;
    const href =
      row.kind === "package"
        ? `/${workspaceSlug}/projects/${row.item.project_id}/issues/${row.item.work_item_id}`
        : undefined;
    const estimated = row.kind === "milestone" && row.item.date_confidence === "estimated";
    const content = (
      <>
        {row.kind === "milestone" ? (
          <DiamondOutline
            className={cn("size-4 shrink-0", estimated ? "text-tertiary" : "text-accent-primary")}
            role="img"
            aria-label={t("project_hub.roadmap.milestone")}
          />
        ) : (
          <CubeOutline
            className="size-4 shrink-0 text-tertiary"
            role="img"
            aria-label={t("project_hub.roadmap.package")}
          />
        )}
        {identifier && (
          <span className="w-16 shrink-0 truncate text-caption-md-regular text-tertiary tabular-nums">
            {identifier}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate text-13 font-medium text-primary">{name}</span>
        {estimated && (
          <span className="shrink-0 text-caption-md-regular text-tertiary">
            {t("project_hub.roadmap.confidence.estimated")}
          </span>
        )}
      </>
    );
    const classes =
      "flex h-9 w-full min-w-0 items-center gap-2 border-b border-subtle pr-3 pl-6 transition-colors duration-100";
    if (href)
      return (
        <Link
          href={href}
          data-hub-row=""
          className={cn(
            classes,
            "hover:bg-layer-transparent-hover focus-visible:bg-accent-primary/10 focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none focus-visible:ring-inset"
          )}
        >
          {content}
        </Link>
      );
    return (
      <div data-hub-row="" tabIndex={-1} className={classes}>
        {content}
      </div>
    );
  };

  const renderBar = (row: TTimelineRow) => {
    const estimated = row.kind === "milestone" && row.item.date_confidence === "estimated";
    const tooltip =
      row.kind === "milestone"
        ? `${row.item.name} · ${formatDate(row.item.target_at)} · ${t(`project_hub.roadmap.confidence.${row.item.date_confidence}`)}`
        : `${row.item.label || row.item.name} · ${formatDate(row.item.start_date)} – ${formatDate(row.item.target_date)}`;
    if (row.kind === "milestone") {
      return (
        <div
          className="absolute top-2 flex h-5 -translate-x-1/2 items-center gap-1 whitespace-nowrap"
          style={{ left: `${row.end}%` }}
          title={tooltip}
        >
          <span
            className={cn(
              "flex size-5 items-center justify-center rounded-full border bg-layer-1",
              estimated ? "border-dashed border-strong text-tertiary" : "border-accent-strong text-accent-primary"
            )}
          >
            <DiamondOutline className="size-3" aria-hidden="true" />
          </span>
          <span className="text-caption-md-regular text-secondary">{row.item.name}</span>
        </div>
      );
    }
    const width = Math.max(row.end - row.start, 1.5);
    const openStart = !row.item.start_date;
    return (
      <div
        className={cn(
          "absolute top-2 flex h-5 min-w-5 items-center overflow-hidden rounded-full border px-2 text-caption-md-regular whitespace-nowrap",
          openStart
            ? "border-dashed border-strong bg-layer-2 text-secondary"
            : "border-accent-subtle bg-accent-primary/15 text-primary"
        )}
        style={{ left: `${row.start}%`, width: `${width}%` }}
        title={tooltip}
      >
        <span className="truncate">{row.item.name}</span>
      </div>
    );
  };

  const confidenceChip = (dep: TPHDependency) => {
    const confirmed = dep.confirmation === "confirmed";
    return confirmed ? (
      <HubChip
        variant="soft"
        tone="success"
        icon={TickCircleOutline as TGlyph}
        label={t("project_hub.roadmap.dependency_confirmed")}
      />
    ) : (
      <HubChip
        variant="outline"
        icon={CircleDashedOutline as TGlyph}
        label={t("project_hub.roadmap.dependency_suggested")}
        className="border-dashed border-strong"
      />
    );
  };

  return (
    <HubPage
      title={title}
      width="full"
      flush
      className="min-h-0 flex-1"
      tabs={{
        tabs: [
          { key: "timeline", label: t("project_hub.roadmap.timeline_view"), icon: TimelineLayoutOutline as TGlyph },
          { key: "table", label: t("project_hub.roadmap.table_view"), icon: TableLayoutOutline as TGlyph },
        ],
        activeKey: view,
        onTabChange: (key) => setView(key as "timeline" | "table"),
        "aria-label": t("project_hub.roadmap.title"),
      }}
      controls={
        <>
          {projectControl}
          {rangeControl}
        </>
      }
      actions={actions}
    >
      <div className="flex min-h-0 flex-1">
        <div className={cn("flex min-w-0 flex-1 flex-col", dialog === "scenario" && "hidden md:flex")}>
          <HubResourceBoundary
            resource={roadmap}
            loadingRows={5}
            isEmpty={(d) => d.milestones.length === 0 && d.packages.length === 0}
            empty={
              <HubEmptyState
                icon={TimelineLayoutOutline as TGlyph}
                title={t("project_hub.roadmap.milestones_empty")}
                description={
                  canPlan && fixedProjectId
                    ? t("project_hub.roadmap.empty_hint")
                    : t("project_hub.roadmap.scenario_hint")
                }
                action={
                  canPlan && fixedProjectId ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={t("project_hub.roadmap.milestone_create")}
                      onClick={() => setDialog("milestone")}
                    />
                  ) : undefined
                }
              />
            }
          >
            {(data) => {
              const dates = [
                ...data.milestones.map((m) => m.target_at),
                ...data.packages.flatMap((p) => [p.start_date, p.target_date]),
              ];
              const window = computeTimelineWindow(dates);
              const todayPos = getTimelinePosition(new Date().toISOString(), window);
              const unplanned: TTimelineRow[] = [
                ...data.milestones
                  .filter((m) => !m.reliable_date)
                  .map(
                    (m): TTimelineRow => ({ key: `milestone:${m.id}`, kind: "milestone", item: m, start: 0, end: 0 })
                  ),
                ...data.packages
                  .filter((p) => !p.reliable_date)
                  .map((p): TTimelineRow => ({ key: `issue:${p.id}`, kind: "package", item: p, start: 0, end: 0 })),
              ];
              const redacted = data.nodes.filter((n) => n.type === "external_blocker");

              // Rows per project (dated items only), in date order.
              const projectRows = data.projects.map((project) => {
                const rows: TTimelineRow[] = [
                  ...data.milestones
                    .filter((m) => m.project_id === project.id && m.reliable_date)
                    .map((m): TTimelineRow => {
                      const at = getTimelinePosition(m.target_at, window) ?? 0;
                      return { key: `milestone:${m.id}`, kind: "milestone", item: m, start: at, end: at };
                    }),
                  ...data.packages
                    .filter((p) => p.project_id === project.id && p.reliable_date)
                    .map((p): TTimelineRow => {
                      const end = getTimelinePosition(p.target_date, window) ?? 0;
                      const start = p.start_date
                        ? (getTimelinePosition(p.start_date, window) ?? end)
                        : Math.max(0, end - 6);
                      return { key: `issue:${p.id}`, kind: "package", item: p, start, end };
                    }),
                ];
                rows.sort((a, b) => a.end - b.end);
                return { project, rows };
              });

              // Absolute y (px) of each row centre inside the canvas, for dependency lines.
              const rowY = new Map<string, number>();
              const rowX = new Map<string, { start: number; end: number; milestone: boolean }>();
              let y = 0;
              for (const { rows } of projectRows) {
                y += 32; // project bar
                for (const row of rows) {
                  rowY.set(row.key, y + ROW_H / 2);
                  rowX.set(row.key, { start: row.start, end: row.end, milestone: row.kind === "milestone" });
                  y += ROW_H;
                }
              }
              const canvasHeight = y;
              const drawableDeps = data.dependencies.filter(
                (dep) => dep.source_key && dep.target_key && rowY.has(dep.source_key) && rowY.has(dep.target_key)
              );
              const months = monthSegments(window.start, window.end);
              const weeks = weekTicks(window.start, window.end);
              const showWeeks = (window.end - window.start) / DAY_MS <= 200;

              return (
                <div
                  ref={listRef}
                  role="group"
                  aria-label={t("project_hub.roadmap.title")}
                  onKeyDown={onListKeyDown}
                  className="flex min-w-0 flex-col pb-8"
                >
                  {view === "timeline" ? (
                    <div className="overflow-x-auto">
                      <div className="flex min-w-0 flex-col" style={{ minWidth: LEFT_W + MIN_CANVAS_W }}>
                        {/* scale */}
                        <div className="sticky top-0 z-[3] flex h-10 border-b border-subtle bg-canvas">
                          <div
                            className="flex shrink-0 items-end border-r border-subtle px-3 pb-1.5 text-caption-md-regular text-tertiary"
                            style={{ width: LEFT_W }}
                          >
                            {t("project_hub.roadmap.projects")}
                          </div>
                          <div className="relative min-w-0 flex-1">
                            {months.map((m, i) => {
                              const left = pct(m.at, window);
                              const nextAt = months[i + 1]?.at ?? window.end;
                              const width = pct(nextAt, window) - left;
                              return (
                                <div
                                  key={m.at}
                                  className="absolute top-0 flex h-5 items-center overflow-hidden border-l border-subtle pl-1.5 text-caption-md-regular whitespace-nowrap text-secondary"
                                  style={{ left: `${left}%`, width: `${width}%` }}
                                >
                                  {width > 6 &&
                                    currentLocaleFormat(
                                      m.label,
                                      width > 12 ? { month: "long", year: "numeric" } : { month: "short" }
                                    )}
                                </div>
                              );
                            })}
                            {showWeeks &&
                              weeks.map((w) => (
                                <div
                                  key={w}
                                  className="absolute bottom-0 flex h-5 items-center border-l border-subtle pl-1 text-caption-sm-regular text-placeholder"
                                  style={{ left: `${pct(w, window)}%` }}
                                >
                                  {weeks.length < 30 && new Date(w).getDate()}
                                </div>
                              ))}
                            {todayPos !== null && (
                              <div
                                className="absolute bottom-0.5 z-[1] flex h-4 -translate-x-1/2 items-center rounded-full bg-accent-primary px-1.5 text-caption-sm-medium whitespace-nowrap text-on-color"
                                style={{ left: `${todayPos}%` }}
                              >
                                {t("project_hub.roadmap.today")}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* body */}
                        <div className="relative flex">
                          <div className="shrink-0 border-r border-subtle" style={{ width: LEFT_W }}>
                            {projectRows.map(({ project, rows }) => {
                              const partial = getPartialProjectById(project.id);
                              return (
                                <div key={project.id}>
                                  <div className="flex h-8 items-center gap-1.5 bg-layer-2 px-3">
                                    <ProjectGlyph logo={partial?.logo_props} />
                                    <Link
                                      href={`/${workspaceSlug}/projects/${project.id}/hub/roadmap`}
                                      className="min-w-0 truncate text-13 font-medium text-primary hover:underline focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
                                    >
                                      {project.name}
                                    </Link>
                                    <span className="shrink-0 text-13 text-tertiary">{rows.length}</span>
                                    <span className="ml-auto shrink-0 text-caption-md-regular text-placeholder">
                                      {project.identifier}
                                    </span>
                                  </div>
                                  {rows.map((row) => (
                                    <div key={row.key}>{renderItemRowLeft(row)}</div>
                                  ))}
                                </div>
                              );
                            })}
                          </div>
                          <div ref={canvas.ref} className="relative min-w-0 flex-1" style={{ height: canvasHeight }}>
                            {/* grid */}
                            {showWeeks &&
                              weeks.map((w) => (
                                <div
                                  key={w}
                                  className="absolute inset-y-0 w-0 border-l border-subtle opacity-60"
                                  style={{ left: `${pct(w, window)}%` }}
                                  aria-hidden="true"
                                />
                              ))}
                            {months.map((m) => (
                              <div
                                key={m.at}
                                className="absolute inset-y-0 w-0 border-l border-strong opacity-50"
                                style={{ left: `${pct(m.at, window)}%` }}
                                aria-hidden="true"
                              />
                            ))}
                            {todayPos !== null && (
                              <div
                                className="absolute inset-y-0 z-[1] w-px bg-accent-primary"
                                style={{ left: `${todayPos}%` }}
                                aria-hidden="true"
                              />
                            )}
                            {/* rows */}
                            {(() => {
                              let offset = 0;
                              return projectRows.map(({ project, rows }) => {
                                const top = offset;
                                offset += 32 + rows.length * ROW_H;
                                return (
                                  <div key={project.id} className="absolute inset-x-0" style={{ top }}>
                                    <div className="h-8 bg-layer-2/60" aria-hidden="true" />
                                    {rows.map((row) => (
                                      <div key={row.key} className="relative h-9 border-b border-subtle">
                                        {renderBar(row)}
                                      </div>
                                    ))}
                                  </div>
                                );
                              });
                            })()}
                            {/* dependency lines */}
                            {drawableDeps.length > 0 && (
                              <svg
                                className="pointer-events-none absolute inset-0 z-[2] size-full overflow-visible"
                                aria-hidden="true"
                              >
                                <defs>
                                  <marker
                                    id="ph-dep-arrow"
                                    viewBox="0 0 8 8"
                                    refX="7"
                                    refY="4"
                                    markerWidth="6"
                                    markerHeight="6"
                                    orient="auto-start-reverse"
                                  >
                                    <path d="M0,0 L8,4 L0,8 z" fill="currentColor" className="text-tertiary" />
                                  </marker>
                                </defs>
                                {canvas.width > 0 &&
                                  drawableDeps.map((dep) => {
                                    const source = rowX.get(dep.source_key!)!;
                                    const target = rowX.get(dep.target_key!)!;
                                    // Milestones are 20px markers centred on their date: leave/enter at the marker edge.
                                    const sx = (source.end / 100) * canvas.width + (source.milestone ? 10 : 0);
                                    const tx = (target.start / 100) * canvas.width - (target.milestone ? 10 : 0);
                                    const confirmed = dep.confirmation === "confirmed";
                                    return (
                                      <path
                                        key={dep.id}
                                        d={connectorPath(
                                          sx,
                                          rowY.get(dep.source_key!)!,
                                          tx,
                                          rowY.get(dep.target_key!)!
                                        )}
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth={confirmed ? 1.5 : 1}
                                        className="text-tertiary"
                                        strokeDasharray={confirmed ? undefined : "4 3"}
                                        markerEnd="url(#ph-dep-arrow)"
                                      />
                                    );
                                  })}
                              </svg>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] text-left text-13">
                        <caption className="sr-only">{t("project_hub.roadmap.title")}</caption>
                        <thead>
                          <tr className="h-8 border-b border-subtle bg-layer-2 text-caption-md-regular text-tertiary">
                            <th scope="col" className="font-normal pl-6">
                              {t("project_hub.roadmap.milestone_name")}
                            </th>
                            <th scope="col" className="font-normal px-3">
                              {t("project_hub.common.project")}
                            </th>
                            <th scope="col" className="font-normal px-3">
                              {t("project_hub.roadmap.target_date")}
                            </th>
                            <th scope="col" className="font-normal px-3 pr-6">
                              {t("project_hub.roadmap.confidence_label")}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.milestones.map((m) => (
                            <tr
                              key={m.id}
                              className="h-9 border-b border-subtle transition-colors duration-100 hover:bg-layer-transparent-hover"
                            >
                              <th scope="row" className="pl-6 font-medium text-primary">
                                <span className="flex min-w-0 items-center gap-2">
                                  <DiamondOutline className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
                                  <span className="truncate">{m.name}</span>
                                </span>
                              </th>
                              <td className="px-3 text-secondary">{projectName(m.project_id)}</td>
                              <td className="px-3 text-secondary tabular-nums">
                                {m.reliable_date ? formatDate(m.target_at) : t("project_hub.roadmap.no_reliable_date")}
                              </td>
                              <td className="px-3 pr-6 text-secondary">
                                {t(`project_hub.roadmap.confidence.${m.date_confidence}`)}
                              </td>
                            </tr>
                          ))}
                          {data.packages.map((p) => (
                            <tr
                              key={p.id}
                              className="h-9 border-b border-subtle transition-colors duration-100 hover:bg-layer-transparent-hover"
                            >
                              <th scope="row" className="pl-6 font-medium text-primary">
                                <Link
                                  href={`/${workspaceSlug}/projects/${p.project_id}/issues/${p.work_item_id}`}
                                  className="flex min-w-0 items-center gap-2 hover:underline focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
                                >
                                  <CubeOutline className="size-4 shrink-0 text-tertiary" aria-hidden="true" />
                                  <span className="font-normal w-16 shrink-0 truncate text-caption-md-regular text-tertiary">
                                    {p.label.split(" ")[0]}
                                  </span>
                                  <span className="truncate">{p.name}</span>
                                </Link>
                              </th>
                              <td className="px-3 text-secondary">{projectName(p.project_id)}</td>
                              <td className="px-3 text-secondary tabular-nums">
                                {p.reliable_date
                                  ? `${p.start_date ? formatDate(p.start_date) : t("project_hub.common.unknown")} – ${formatDate(p.target_date)}`
                                  : t("project_hub.roadmap.no_reliable_date")}
                              </td>
                              <td className="px-3 pr-6 text-secondary">{p.state_group ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <HubListGroup
                    icon={CircleDashedOutline as TGlyph}
                    title={t("project_hub.roadmap.unplanned")}
                    count={unplanned.length}
                    className="mt-4"
                  >
                    <HubList>
                      {unplanned.map((row) => (
                        <HubListRow
                          key={row.key}
                          href={
                            row.kind === "package"
                              ? `/${workspaceSlug}/projects/${row.item.project_id}/issues/${row.item.work_item_id}`
                              : undefined
                          }
                          navId={row.key}
                          identifier={row.kind === "package" ? row.item.label.split(" ")[0] : undefined}
                          icon={
                            row.kind === "milestone" ? (
                              <DiamondOutline className="size-4 text-tertiary" />
                            ) : (
                              <CubeOutline className="size-4 text-tertiary" />
                            )
                          }
                          title={row.item.name}
                          meta={
                            <>
                              {showProjectChip && (
                                <HubChip label={projectName(row.item.project_id)} className="hidden sm:inline-flex" />
                              )}
                              <HubChip
                                variant="soft"
                                icon={CalendarOutline as TGlyph}
                                label={t("project_hub.roadmap.no_reliable_date")}
                              />
                            </>
                          }
                        />
                      ))}
                    </HubList>
                  </HubListGroup>

                  <HubListGroup
                    icon={DependencyOutline as TGlyph}
                    title={t("project_hub.roadmap.dependencies")}
                    count={data.dependencies.length + redacted.length}
                    showEmpty
                    emptyLabel={t("project_hub.roadmap.dependencies_empty")}
                    className="mt-4"
                  >
                    <HubList>
                      {data.dependencies.map((dep) => {
                        const confirmed = dep.confirmation === "confirmed";
                        const external = dep.style === "external";
                        return (
                          <HubListRow
                            key={dep.id}
                            navId={dep.id}
                            icon={
                              external ? (
                                <LockOutline className="size-4 text-tertiary" />
                              ) : (
                                <DependencyOutline
                                  className={cn("size-4", confirmed ? "text-primary" : "text-tertiary")}
                                />
                              )
                            }
                            title={
                              <span className="flex min-w-0 items-center gap-1.5">
                                <span className="truncate">{nodeLabel(dep.source_key)}</span>
                                <span
                                  className={cn(
                                    "font-normal shrink-0 text-tertiary",
                                    !confirmed && "border-b border-dashed border-strong"
                                  )}
                                  aria-hidden="true"
                                >
                                  →
                                </span>
                                <span className="sr-only">
                                  {t("project_hub.roadmap.predecessor")} → {t("project_hub.roadmap.successor")}
                                </span>
                                <span className="truncate">{nodeLabel(dep.target_key)}</span>
                              </span>
                            }
                            meta={
                              <>
                                {confidenceChip(dep)}
                                <span className="hidden text-caption-md-regular text-tertiary md:inline">
                                  {dep.blocking ? t("project_hub.roadmap.hard") : t("project_hub.roadmap.soft")}
                                  {dep.source ? ` · ${dep.source}` : ""}
                                </span>
                              </>
                            }
                            trailing={
                              !confirmed && !external && canPlan && dep.confirmation === "suggested" ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  stretch="auto"
                                  label={t("project_hub.roadmap.confirm_dependency")}
                                  onClick={() => void confirmDependency(dep)}
                                />
                              ) : undefined
                            }
                          />
                        );
                      })}
                      {redacted.map((n) => (
                        <HubListRow
                          key={n.key}
                          navId={n.key}
                          icon={<LockOutline className="size-4 text-tertiary" />}
                          title={t("project_hub.roadmap.external_prerequisite")}
                          meta={<HubChip variant="soft" label={t("project_hub.roadmap.redacted")} />}
                        />
                      ))}
                    </HubList>
                  </HubListGroup>
                </div>
              );
            }}
          </HubResourceBoundary>
        </div>

        {dialog === "scenario" && (
          <SidePanel
            title={scenario ? scenario.name : t("project_hub.roadmap.scenario_create")}
            onClose={closeDialog}
            footer={
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  label={t("project_hub.common.cancel")}
                  onClick={closeDialog}
                />
                {scenario ? (
                  <Button
                    variant="primary"
                    size="sm"
                    stretch="auto"
                    loading={busy}
                    disabled={!canPlan}
                    label={t("project_hub.roadmap.apply_scenario")}
                    onClick={() => void applyScenario()}
                  />
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    stretch="auto"
                    loading={busy}
                    disabled={!scMilestone || !scName.trim()}
                    label={t("project_hub.roadmap.impact")}
                    onClick={() => void createScenario()}
                  />
                )}
              </>
            }
          >
            <p className="text-caption-md-regular text-tertiary">{t("project_hub.roadmap.scenario_hint")}</p>
            {!scenario && (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void createScenario();
                }}
              >
                <PanelField
                  label={t("project_hub.roadmap.scenario_name")}
                  value={scName}
                  required
                  onChange={setScName}
                />
                <HubSelect
                  label={t("project_hub.roadmap.scenario_item")}
                  value={scMilestone}
                  onChange={setScMilestone}
                  options={milestoneOptions}
                />
                <PanelField
                  type="date"
                  label={t("project_hub.roadmap.scenario_new_date")}
                  value={scDate}
                  onChange={setScDate}
                />
              </form>
            )}
            {impact && (
              <div className="flex flex-col overflow-hidden rounded-md border border-subtle">
                <div className="flex h-8 items-center gap-1.5 bg-layer-2 px-3 text-13 font-medium text-primary">
                  {t("project_hub.roadmap.impact")}
                  <span className="text-tertiary">{impact.affected.length}</span>
                </div>
                <ul className="flex flex-col">
                  {impact.changes.map((c) => (
                    <li key={c.id} className="flex min-h-8 items-center gap-2 border-b border-subtle px-3 text-13">
                      <DiamondOutline className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate text-primary">{c.label ?? c.id}</span>
                      <span className="shrink-0 text-caption-md-regular text-tertiary tabular-nums">
                        {formatDate(c.current_target_at)} → {formatDate(c.new_target_at)}
                      </span>
                    </li>
                  ))}
                  {impact.affected.length === 0 ? (
                    <li className="flex h-8 items-center px-3 text-caption-md-regular text-tertiary">
                      {t("project_hub.roadmap.impact_empty")}
                    </li>
                  ) : (
                    impact.affected.map((a) => (
                      <li
                        key={a.key}
                        className="flex min-w-0 flex-col gap-0.5 border-b border-subtle px-3 py-1.5 text-13 last:border-b-0"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="min-w-0 flex-1 truncate text-primary">{a.label}</span>
                          <HubChip
                            variant="soft"
                            tone={a.current_target === null ? "neutral" : a.would_be_late ? "warning" : "success"}
                            label={
                              a.current_target === null
                                ? t("project_hub.roadmap.no_reliable_date")
                                : a.would_be_late
                                  ? t("project_hub.roadmap.late_by", {
                                      hours: a.shift_hours,
                                      date: formatDate(a.projected_target),
                                    })
                                  : t("project_hub.roadmap.not_late")
                            }
                          />
                        </span>
                        <span className="truncate text-caption-md-regular text-tertiary" title={a.via.join(" → ")}>
                          {t("project_hub.roadmap.via", { path: a.via.join(" → ") })}
                        </span>
                      </li>
                    ))
                  )}
                </ul>
                <p className="px-3 py-2 text-caption-md-regular text-placeholder">
                  {t("project_hub.roadmap.impact_basis_deps")}
                </p>
              </div>
            )}
            {dialogError && (
              <p role="alert" className="text-caption-md-regular text-danger-primary">
                {t(getProjectHubErrorMessageKey(dialogError))}
              </p>
            )}
          </SidePanel>
        )}
      </div>

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
          <p role="alert" className="text-caption-md-regular text-danger-primary">
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
          <div role="alert" className="flex flex-col gap-1 text-caption-md-regular text-danger-primary">
            <p>{t(getProjectHubErrorMessageKey(dialogError))}</p>
            {cyclePath.length > 0 && <p>{t("project_hub.roadmap.cycle_error", { path: cyclePath.join(" → ") })}</p>}
          </div>
        )}
      </HubDialog>
    </HubPage>
  );
});
