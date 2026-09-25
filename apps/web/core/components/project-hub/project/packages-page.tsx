/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { FilterOutline, ListLayoutOutline, PlayCircleOutline } from "@makeplane/propel/icons";
import { PriorityIcon } from "@plane/blocks/icons";
import { useTranslation } from "@plane/i18n";
import type { TIssuePriorities, TPackagePhase, TPackageRow, TPHOverview } from "@plane/types";
import {
  PROJECT_HUB_PHASES,
  buildPackageIndicator,
  generateWorkItemLink,
  getPhaseDescriptionKey,
  getPhaseLabelKey,
  groupRowsByPhase,
} from "@plane/utils";
// components
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubPhaseIcon, PHASE_ICONS } from "../common/phase-indicator";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;
type TView = "all" | "active" | "drafts";

const ACTIVE_PHASES: ReadonlySet<TPackagePhase> = new Set(["ready", "build", "review", "ship"]);
const VIEW_PHASES: Record<TView, ReadonlySet<TPackagePhase>> = {
  all: new Set(PROJECT_HUB_PHASES),
  active: ACTIVE_PHASES,
  drafts: new Set(["drafts"]),
};

const PackageRowItem = observer(function PackageRowItem({
  row,
  workspaceSlug,
  projectId,
  nextReasons,
}: {
  row: TPackageRow;
  workspaceSlug: string;
  projectId: string;
  nextReasons?: string[];
}) {
  const { t } = useTranslation();
  const { formatAge, formatDateTime } = useHubFormatters();
  // Same native issue id and route as the native list (FR-B14 / PF14).
  const href = generateWorkItemLink({
    workspaceSlug,
    projectId,
    issueId: row.work_item_id,
    projectIdentifier: row.project_identifier,
    sequenceId: row.sequence_id,
  });
  const identifier = row.project_identifier && row.sequence_id ? `${row.project_identifier}-${row.sequence_id}` : "";
  const indicator = buildPackageIndicator(row);
  const [firstFlag, ...moreFlags] = indicator.flags;
  const reasons = nextReasons && nextReasons.length > 0 ? nextReasons.join(" · ") : undefined;

  return (
    <HubListRow
      href={href}
      navId={row.work_item_id}
      aria-label={`${t("project_hub.common.open_work_item", { id: identifier })} ${row.name}`}
      leading={<PriorityIcon priority={(row.priority as TIssuePriorities | null) ?? "none"} className="size-3.5" />}
      identifier={identifier || undefined}
      icon={<HubPhaseIcon phase={row.phase} />}
      title={row.name}
      meta={
        <>
          {reasons && (
            <HubChip
              icon={PlayCircleOutline as TGlyph}
              variant="soft"
              label={t("project_hub.packages.next")}
              title={`${t("project_hub.packages.next_reasons")}: ${reasons}`}
            />
          )}
          {firstFlag && (
            <HubChip
              tone={firstFlag.tone}
              label={t(firstFlag.labelKey)}
              trailing={moreFlags.length > 0 ? `+${moreFlags.length}` : undefined}
              title={indicator.flags.map((f) => t(f.labelKey)).join(", ")}
            />
          )}
          {row.open_questions > 0 && (
            <HubChip tone="warning" label={t("project_hub.packages.open_questions", { count: row.open_questions })} />
          )}
        </>
      }
      trailing={
        <>
          <span
            className="hidden text-caption-md-regular text-tertiary tabular-nums sm:inline"
            title={t("project_hub.packages.updated", { time: formatDateTime(row.updated_at) })}
          >
            {formatAge(row.updated_at)}
          </span>
          <span className="flex w-6 justify-end">
            {row.assignee_ids.length > 0 && <ButtonAvatars showTooltip userIds={row.assignee_ids} />}
          </span>
        </>
      }
    />
  );
});

/**
 * S03 Work packages: Linear-style grouped list — one sticky group bar per phase (Drafts / Ready /
 * Build / Review / Ship / Done), empty groups hidden, 36px rows, j/k/Enter navigation. Every row
 * opens the same native work item (no second issue model).
 */
export const ProjectPackagesPage = observer(function ProjectPackagesPage({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const listRef = useRef<HTMLDivElement>(null);
  const onKeyDown = useHubListNavigation(listRef);
  const [view, setView] = useState<TView>("all");
  const [hideDone, setHideDone] = useState(false);
  const [showEmpty, setShowEmpty] = useState(false);

  const rows = useHubResource<TPackageRow[]>(PH_KEYS.rows(workspaceSlug, projectId), () =>
    store.packageService.listPackages(workspaceSlug, projectId, "all")
  );
  // "Next" reasons (approval, blockers, native priority) come from the project overview.
  const overview = useHubResource<TPHOverview>(PH_KEYS.overview(workspaceSlug, projectId), () =>
    store.knowledgeService.getOverview(workspaceSlug, projectId)
  );
  const reasonsByIssue = useMemo(
    () => new Map((overview.data?.next_work ?? []).map((w) => [w.issue_id, w.reasons])),
    [overview.data]
  );

  const counts = useMemo(() => {
    const data = rows.data ?? [];
    return {
      all: data.length,
      active: data.filter((r) => ACTIVE_PHASES.has(r.phase)).length,
      drafts: data.filter((r) => r.phase === "drafts").length,
    };
  }, [rows.data]);
  const visiblePhases = PROJECT_HUB_PHASES.filter((p) => VIEW_PHASES[view].has(p) && !(hideDone && p === "done"));

  const doneLabel = hideDone ? t("project_hub.packages.show_done") : t("project_hub.packages.hide_done");
  const emptyLabel = showEmpty
    ? t("project_hub.packages.hide_empty_groups")
    : t("project_hub.packages.show_empty_groups");

  return (
    <HubPage
      title={t("project_hub.packages.title")}
      flush
      tabs={{
        "aria-label": t("project_hub.packages.sections_label"),
        activeKey: view,
        onTabChange: (key) => setView(key as TView),
        tabs: [
          { key: "all", label: t("project_hub.packages.view_all"), count: rows.data ? counts.all : undefined },
          { key: "active", label: t("project_hub.packages.view_active"), count: rows.data ? counts.active : undefined },
          { key: "drafts", label: t("project_hub.packages.view_drafts"), count: rows.data ? counts.drafts : undefined },
        ],
      }}
      controls={
        <>
          {view !== "drafts" && (
            <Tooltip label={doneLabel}>
              <IconButton
                variant={hideDone ? "secondary" : "ghost"}
                size="sm"
                icon={<Icon icon={FilterOutline} />}
                aria-label={doneLabel}
                aria-pressed={hideDone}
                onClick={() => setHideDone((v) => !v)}
              />
            </Tooltip>
          )}
          <Tooltip label={emptyLabel}>
            <IconButton
              variant={showEmpty ? "secondary" : "ghost"}
              size="sm"
              icon={<Icon icon={ListLayoutOutline} />}
              aria-label={emptyLabel}
              aria-pressed={showEmpty}
              onClick={() => setShowEmpty((v) => !v)}
            />
          </Tooltip>
        </>
      }
    >
      <HubResourceBoundary
        resource={rows}
        loadingRows={8}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmptyState icon={PHASE_ICONS.drafts} title={t("project_hub.packages.empty")} />}
      >
        {(all) => {
          const groups = groupRowsByPhase(all);
          const visibleCount = visiblePhases.reduce((n, p) => n + groups[p].length, 0);
          if (visibleCount === 0 && !showEmpty)
            return (
              <HubEmptyState
                icon={PHASE_ICONS[view === "drafts" ? "drafts" : "ready"]}
                title={t("project_hub.packages.filtered_empty")}
              />
            );
          return (
            // oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- list navigation (j/k/Enter) on the container
            <div ref={listRef} onKeyDown={onKeyDown} className="flex min-w-0 flex-col pb-6">
              {visiblePhases.map((phase) => (
                <HubListGroup
                  key={phase}
                  icon={<HubPhaseIcon phase={phase} />}
                  title={t(getPhaseLabelKey(phase))}
                  hint={t(getPhaseDescriptionKey(phase))}
                  count={groups[phase].length}
                  showEmpty={showEmpty}
                  emptyLabel={t("project_hub.packages.section_empty")}
                >
                  <HubList aria-label={t(getPhaseLabelKey(phase))}>
                    {groups[phase].map((row) => (
                      <PackageRowItem
                        key={row.work_item_id}
                        row={row}
                        workspaceSlug={workspaceSlug}
                        projectId={projectId}
                        nextReasons={phase === "ready" ? reasonsByIssue.get(row.work_item_id) : undefined}
                      />
                    ))}
                  </HubList>
                </HubListGroup>
              ))}
            </div>
          );
        }}
      </HubResourceBoundary>
    </HubPage>
  );
});
