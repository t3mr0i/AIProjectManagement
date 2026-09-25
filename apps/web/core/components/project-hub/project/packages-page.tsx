/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPackageRow, TPHOverview } from "@plane/types";
import {
  PROJECT_HUB_PHASES,
  generateWorkItemLink,
  getPhaseDescriptionKey,
  getPhaseLabelKey,
  groupRowsByPhase,
} from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useMemberDisplayName } from "../common/member-name";
import { HubPage } from "../common/page";
import { PHASE_ICONS, PackagePhaseIndicator } from "../common/phase-indicator";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

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
  const displayName = useMemberDisplayName();
  const { formatAge } = useHubFormatters();
  // Same native issue id and route as the native list (FR-B14 / PF14).
  const href = generateWorkItemLink({
    workspaceSlug,
    projectId,
    issueId: row.work_item_id,
    projectIdentifier: row.project_identifier,
    sequenceId: row.sequence_id,
  });
  const identifier = row.project_identifier && row.sequence_id ? `${row.project_identifier}-${row.sequence_id}` : "";
  return (
    <li className="flex min-h-10 flex-col gap-1 px-3 py-2 hover:bg-layer-1 sm:flex-row sm:items-center sm:gap-3">
      <Link
        href={href}
        className="focus-visible:outline-accent-primary flex min-w-0 flex-1 items-center gap-2 rounded-sm focus-visible:outline-2"
        aria-label={`${t("project_hub.common.open_work_item", { id: identifier })} ${row.name}`}
      >
        {identifier && <span className="shrink-0 text-caption-md-medium text-tertiary">{identifier}</span>}
        <span className="truncate text-body-xs-medium text-primary">{row.name}</span>
      </Link>
      <div className="flex flex-wrap items-center gap-2 text-caption-sm-regular text-tertiary">
        <PackagePhaseIndicator status={row} variant="compact" />
        {row.open_questions > 0 && (
          <span>{t("project_hub.packages.open_questions", { count: row.open_questions })}</span>
        )}
        {row.assignee_ids.length > 0 && <span>{row.assignee_ids.map(displayName).join(", ")}</span>}
        <span>{t("project_hub.packages.updated", { time: formatAge(row.updated_at) })}</span>
      </div>
      {nextReasons && nextReasons.length > 0 && (
        <p className="text-caption-sm-regular text-secondary sm:basis-full">
          <span className="text-tertiary">{t("project_hub.packages.next_reasons")}: </span>
          {nextReasons.join(" · ")}
        </p>
      )}
    </li>
  );
});

/**
 * S03 Work packages: compact list with sections Drafts / Ready-Next / Build / Review / Ship / Done.
 * Each row opens the same native work item (no second issue model).
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
  const rows = useHubResource<TPackageRow[]>(PH_KEYS.rows(workspaceSlug, projectId), () =>
    store.packageService.listPackages(workspaceSlug, projectId, "all")
  );
  // "Next" reasons (approval, blockers, native priority) come from the project overview.
  const overview = useHubResource<TPHOverview>(PH_KEYS.overview(workspaceSlug, projectId), () =>
    store.knowledgeService.getOverview(workspaceSlug, projectId)
  );
  const reasonsByIssue = new Map((overview.data?.next_work ?? []).map((w) => [w.issue_id, w.reasons]));

  return (
    <HubPage title={t("project_hub.packages.title")}>
      <HubResourceBoundary
        resource={rows}
        loadingRows={6}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.packages.empty")} />}
      >
        {(data) => {
          const groups = groupRowsByPhase(data);
          return (
            <div className="flex flex-col gap-5" aria-label={t("project_hub.packages.sections_label")}>
              {PROJECT_HUB_PHASES.map((phase) => {
                const Glyph = PHASE_ICONS[phase];
                return (
                  <section key={phase} aria-labelledby={`phase-${phase}`} className="flex flex-col gap-2">
                    <div className="flex items-baseline gap-2">
                      <Glyph className="size-4 self-center text-tertiary" aria-hidden="true" />
                      <h2 id={`phase-${phase}`} className="text-body-sm-semibold text-primary">
                        {t(getPhaseLabelKey(phase))}
                      </h2>
                      <span className="text-caption-sm-regular text-tertiary">({groups[phase].length})</span>
                      <span className="text-caption-sm-regular text-tertiary">{t(getPhaseDescriptionKey(phase))}</span>
                    </div>
                    {groups[phase].length === 0 ? (
                      <p className="px-3 text-caption-sm-regular text-tertiary">
                        {t("project_hub.packages.section_empty")}
                      </p>
                    ) : (
                      <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
                        {groups[phase].map((row) => (
                          <PackageRowItem
                            key={row.work_item_id}
                            row={row}
                            workspaceSlug={workspaceSlug}
                            projectId={projectId}
                            nextReasons={phase === "ready" ? reasonsByIssue.get(row.work_item_id) : undefined}
                          />
                        ))}
                      </ul>
                    )}
                  </section>
                );
              })}
            </div>
          );
        }}
      </HubResourceBoundary>
    </HubPage>
  );
});
