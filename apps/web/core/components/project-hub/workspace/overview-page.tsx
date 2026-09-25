/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useRef } from "react";
import { observer } from "mobx-react";
// plane imports
import {
  BlockingOutline,
  ChatOutline,
  InboxOutline,
  PlayCircleOutline,
  ProjectsOutline,
  SettingsOutline,
  ShowOutline,
  WarningCircleOutline,
} from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import type { TPackagePhase, TPHNextWork, TPHNotificationItem, TPHOverview, TPHOverviewItem } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubAskAIPanel } from "../ai/ask-panel";
import { HubChip } from "../common/chip";
import { useProjectHubCapabilities } from "../common/gate";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubPhaseIcon } from "../common/phase-indicator";
import { HubEmptyState, HubErrorState, HubLoading, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/* -------------------------------------------------------------------------------------------------
 * Phase progress (counts per overview bucket → package phase)
 * -----------------------------------------------------------------------------------------------*/

type TBucket = keyof TPHOverview["packages"];

/** Overview buckets in flow order with their phase (icon + text everywhere, colour is a helper). */
const BUCKETS: { key: TBucket; phase: TPackagePhase; bar: string }[] = [
  { key: "draft", phase: "drafts", bar: "bg-icon-placeholder" },
  { key: "ready", phase: "ready", bar: "bg-accent-primary/50" },
  { key: "active", phase: "build", bar: "bg-warning-primary" },
  { key: "review", phase: "review", bar: "bg-accent-primary" },
  { key: "shipped", phase: "ship", bar: "bg-success-primary" },
];

const countOf = (overview: TPHOverview, key: TBucket) => overview.packages[key]?.length ?? 0;

/** Small segmented progress bar (Linear project progress) + muted "n active · n review · n ready". */
function PhaseProgress({ overview }: { overview: TPHOverview }) {
  const { t } = useTranslation();
  const total = BUCKETS.reduce((sum, b) => sum + countOf(overview, b.key), 0);
  const summary = t("project_hub.overview.counts", {
    active: countOf(overview, "active"),
    review: countOf(overview, "review"),
    ready: countOf(overview, "ready"),
  });
  const detail = BUCKETS.map((b) => `${t(`project_hub.phase.${b.phase}`)}: ${countOf(overview, b.key)}`).join(" · ");
  return (
    <span className="flex items-center gap-2" title={detail}>
      <span className="hidden text-caption-md-regular text-tertiary tabular-nums md:inline">{summary}</span>
      <span
        role="img"
        aria-label={detail}
        className="flex h-1.5 w-16 shrink-0 gap-px overflow-hidden rounded-full bg-layer-3"
      >
        {total > 0 &&
          BUCKETS.map((b) => {
            const n = countOf(overview, b.key);
            return n > 0 ? (
              <span key={b.key} className={cn("h-full", b.bar)} style={{ flexGrow: n }} aria-hidden="true" />
            ) : null;
          })}
      </span>
      <span className="w-8 shrink-0 text-right text-caption-md-regular text-tertiary tabular-nums">{total}</span>
    </span>
  );
}

/* -------------------------------------------------------------------------------------------------
 * Rows
 * -----------------------------------------------------------------------------------------------*/

const CATEGORY_ICON: Record<string, TGlyph> = {
  decision_needed: WarningCircleOutline as TGlyph,
  blocked: BlockingOutline as TGlyph,
  mention: ChatOutline as TGlyph,
  review_request: ShowOutline as TGlyph,
  technical: SettingsOutline as TGlyph,
};

const CATEGORY_KEYS = new Set(Object.keys(CATEGORY_ICON));

const DecisionRow = observer(function DecisionRow({ item }: { item: TPHNotificationItem }) {
  const { t } = useTranslation();
  const { getPartialProjectById } = useProject();
  const { formatAge, formatDateTime } = useHubFormatters();
  const urgent = item.category === "decision_needed" || item.category === "blocked";
  const Glyph = CATEGORY_ICON[item.category] ?? (InboxOutline as TGlyph);
  const label = CATEGORY_KEYS.has(item.category) ? t(`project_hub.overview.category.${item.category}`) : item.category;
  const project = item.project_id ? getPartialProjectById(item.project_id) : undefined;
  return (
    <HubListRow
      href={item.target.url}
      navId={item.id}
      icon={<Glyph className={cn("size-4", urgent ? "text-warning-primary" : "text-tertiary")} />}
      title={item.title}
      meta={
        <>
          <HubChip variant="soft" tone={urgent ? "warning" : "info"} label={label} />
          {project && (
            <HubChip
              label={project.name}
              icon={
                project.logo_props?.in_use ? <Logo logo={project.logo_props} size={12} /> : (ProjectsOutline as TGlyph)
              }
              className="hidden sm:inline-flex"
            />
          )}
          {item.count > 1 && <span className="text-caption-md-regular text-tertiary tabular-nums">×{item.count}</span>}
        </>
      }
      trailing={
        <span
          className="w-14 text-right text-caption-md-regular text-tertiary tabular-nums"
          title={formatDateTime(item.updated_at)}
        >
          {formatAge(item.updated_at)}
        </span>
      }
    />
  );
});

function PackageRow({
  workspaceSlug,
  projectId,
  item,
  phase,
  projectChip,
  indent,
}: {
  workspaceSlug: string;
  projectId: string;
  item: TPHOverviewItem;
  phase: TPackagePhase;
  projectChip?: boolean;
  indent?: number;
}) {
  const { t } = useTranslation();
  const { getPartialProjectById } = useProject();
  const project = projectChip ? getPartialProjectById(projectId) : undefined;
  return (
    <HubListRow
      href={`/${workspaceSlug}/projects/${projectId}/issues/${item.issue_id}`}
      navId={`${projectId}:${item.issue_id}`}
      identifier={item.identifier}
      icon={<HubPhaseIcon phase={phase} />}
      title={item.name}
      indent={indent}
      meta={
        <>
          {item.priority && item.priority !== "none" && (
            <span className="hidden text-caption-md-regular text-tertiary capitalize md:inline">{item.priority}</span>
          )}
          {project && (
            <HubChip
              label={project.name}
              icon={
                project.logo_props?.in_use ? <Logo logo={project.logo_props} size={12} /> : (ProjectsOutline as TGlyph)
              }
              className="hidden sm:inline-flex"
            />
          )}
          <HubChip
            variant="soft"
            icon={PlayCircleOutline as TGlyph}
            label={t(`project_hub.phase.${phase}`)}
            className="hidden lg:inline-flex"
          />
        </>
      }
    />
  );
}

/** Next-work row: identifier, name and the quiet "why" reason line inline (single line, truncates). */
function NextWorkRow({
  workspaceSlug,
  projectId,
  item,
}: {
  workspaceSlug: string;
  projectId: string;
  item: TPHNextWork;
}) {
  const { t } = useTranslation();
  const reason = item.reasons.join(" · ");
  return (
    <HubListRow
      href={`/${workspaceSlug}/projects/${projectId}/issues/${item.issue_id}`}
      navId={`next:${projectId}:${item.issue_id}`}
      identifier={item.identifier}
      indent={20}
      icon={
        item.blocked ? (
          <BlockingOutline className="size-4 text-warning-primary" />
        ) : (
          <PlayCircleOutline
            className={cn("size-4", item.immediately_executable ? "text-success-primary" : "text-tertiary")}
          />
        )
      }
      title={
        <>
          {item.name}
          {reason && (
            <span className="font-normal ml-2 text-tertiary" title={reason}>
              {reason}
            </span>
          )}
        </>
      }
      meta={
        <HubChip
          variant="soft"
          tone={item.blocked ? "warning" : item.immediately_executable ? "success" : "neutral"}
          label={t("project_hub.overview.next_work")}
        />
      }
    />
  );
}

/* -------------------------------------------------------------------------------------------------
 * Project rows (each project loads its own overview into the store, same key as before)
 * -----------------------------------------------------------------------------------------------*/

const ProjectRows = observer(function ProjectRows({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { getPartialProjectById } = useProject();
  const { isLoaded, isEnabled } = useProjectHubCapabilities(workspaceSlug, projectId);
  const project = getPartialProjectById(projectId);
  const overview = useHubResource<TPHOverview>(isEnabled ? PH_KEYS.overview(workspaceSlug, projectId) : null, () =>
    store.knowledgeService.getOverview(workspaceSlug, projectId)
  );
  const data = overview.data;
  const openDecisions = data?.open_decisions.length ?? 0;
  return (
    <>
      <HubListRow
        href={`/${workspaceSlug}/projects/${projectId}/hub/activity`}
        navId={`project:${projectId}`}
        icon={
          project?.logo_props?.in_use ? (
            <Logo logo={project.logo_props} size={16} />
          ) : (
            <ProjectsOutline className="size-4 text-tertiary" />
          )
        }
        title={project?.name ?? projectId}
        meta={
          <>
            {isLoaded && !isEnabled && <HubChip variant="soft" label={t("project_hub.overview.not_enabled")} />}
            {openDecisions > 0 && (
              <HubChip
                variant="soft"
                tone="warning"
                icon={WarningCircleOutline as TGlyph}
                label={t("project_hub.overview.open_decisions_count", { count: openDecisions })}
              />
            )}
          </>
        }
        trailing={data ? <PhaseProgress overview={data} /> : undefined}
      />
      {(!isLoaded || (isEnabled && overview.isLoading)) && (
        <div className="px-3 py-1.5 pl-9">
          <HubLoading rows={1} />
        </div>
      )}
      {isEnabled && overview.error && !data && (
        <HubErrorState size="sm" error={overview.error} onRetry={() => void overview.refresh()} />
      )}
      {data?.next_work.slice(0, 3).map((n) => (
        <NextWorkRow key={n.issue_id} workspaceSlug={workspaceSlug} projectId={projectId} item={n} />
      ))}
    </>
  );
});

/* -------------------------------------------------------------------------------------------------
 * Page
 * -----------------------------------------------------------------------------------------------*/

const isDecision = (n: TPHNotificationItem) => !n.read_at && n.delivery === "immediate";

/** S01 Workspace overview: decisions needing me, current work and projects with next work (Linear-style groups). */
export const WorkspaceOverviewPage = observer(function WorkspaceOverviewPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { joinedProjectIds } = useProject();
  const listRef = useRef<HTMLDivElement>(null);
  const onKeyDown = useHubListNavigation(listRef);
  const notifications = useHubResource<TPHNotificationItem[]>(PH_KEYS.notifications(workspaceSlug), async () => {
    const n = await store.collaborationService.listNotifications(workspaceSlug);
    return [...n.targeted, ...n.bundled];
  });

  // Current work is composed from the per-project overviews the project rows load (same store keys).
  const currentWork = joinedProjectIds.flatMap((projectId) => {
    const overview = store.getResource<TPHOverview>(PH_KEYS.overview(workspaceSlug, projectId));
    if (!overview) return [];
    return [
      ...overview.packages.active.map((item) => ({ projectId, item, phase: "build" as const })),
      ...overview.packages.review.map((item) => ({ projectId, item, phase: "review" as const })),
    ];
  });
  const decisions = (notifications.data ?? []).filter(isDecision);
  const nothingToDo = notifications.data !== undefined && decisions.length === 0 && currentWork.length === 0;

  return (
    <HubPage title={t("project_hub.overview.title")} width="full" flush>
      {/* AI is the entry point: ask across every project the viewer can read. */}
      <div className="border-b border-subtle px-4 py-4 md:px-6">
        <HubAskAIPanel workspaceSlug={workspaceSlug} className="max-w-3xl" />
      </div>
      <div
        ref={listRef}
        role="group"
        aria-label={t("project_hub.overview.title")}
        onKeyDown={onKeyDown}
        className="flex min-w-0 flex-col pb-8"
      >
        <HubResourceBoundary resource={notifications} loadingRows={2}>
          {() => (
            <HubListGroup
              icon={WarningCircleOutline as TGlyph}
              title={t("project_hub.overview.my_decisions")}
              count={decisions.length}
            >
              <HubList aria-label={t("project_hub.overview.my_decisions")}>
                {decisions.map((n) => (
                  <DecisionRow key={n.id} item={n} />
                ))}
              </HubList>
            </HubListGroup>
          )}
        </HubResourceBoundary>

        <HubListGroup
          icon={PlayCircleOutline as TGlyph}
          title={t("project_hub.overview.current_work")}
          count={currentWork.length}
        >
          <HubList aria-label={t("project_hub.overview.current_work")}>
            {currentWork.map(({ projectId, item, phase }) => (
              <PackageRow
                key={`${projectId}:${item.issue_id}`}
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                item={item}
                phase={phase}
                projectChip={joinedProjectIds.length > 1}
              />
            ))}
          </HubList>
        </HubListGroup>

        {nothingToDo && (
          <HubEmptyState
            icon={InboxOutline as TGlyph}
            title={t("project_hub.overview.caught_up")}
            description={t("project_hub.overview.caught_up_hint")}
          />
        )}

        <HubListGroup
          icon={ProjectsOutline as TGlyph}
          title={t("project_hub.overview.projects")}
          count={joinedProjectIds.length}
          showEmpty
          emptyLabel={t("project_hub.overview.no_projects")}
        >
          <HubList aria-label={t("project_hub.overview.projects")}>
            {joinedProjectIds.map((projectId) => (
              <ProjectRows key={projectId} workspaceSlug={workspaceSlug} projectId={projectId} />
            ))}
          </HubList>
        </HubListGroup>
      </div>
    </HubPage>
  );
});
