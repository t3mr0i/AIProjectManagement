/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHNotificationItem, TPHOverview } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { useProjectHubCapabilities } from "../common/gate";
import { HubPage } from "../common/page";
import { HubCard, HubSection } from "../common/section";
import { HubEmpty, HubErrorState, HubLoading, HubResourceBoundary } from "../common/states";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";

const ProjectOverviewCard = observer(function ProjectOverviewCard({
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
  return (
    <li>
      <HubCard className="flex h-full flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Link
            href={`/${workspaceSlug}/projects/${projectId}/hub/activity`}
            className="focus-visible:outline-accent-primary text-body-sm-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2"
          >
            {project?.name ?? projectId}
          </Link>
          {isLoaded && !isEnabled && (
            <ToneBadge tone="neutral" size="xs" label={t("project_hub.overview.not_enabled")} />
          )}
        </div>
        {!isLoaded || (isEnabled && overview.isLoading) ? (
          <HubLoading rows={1} />
        ) : isEnabled && overview.error && !overview.data ? (
          <HubErrorState error={overview.error} onRetry={() => void overview.refresh()} />
        ) : isEnabled && overview.data ? (
          <>
            <p className="text-caption-sm-regular text-secondary">
              {t("project_hub.overview.counts", {
                active: overview.data.active.length,
                review: overview.data.review.length,
                ready: overview.data.ready.length,
              })}
            </p>
            {overview.data.next_work.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-caption-md-medium text-tertiary">{t("project_hub.overview.next_work")}</p>
                <ul className="flex flex-col gap-1 text-caption-sm-regular text-secondary">
                  {overview.data.next_work.slice(0, 3).map((n) => (
                    <li key={n.issue_id}>
                      <Link
                        href={`/${workspaceSlug}/projects/${projectId}/issues/${n.issue_id}`}
                        className="focus-visible:outline-accent-primary text-primary underline-offset-2 hover:underline focus-visible:outline-2"
                      >
                        {n.name}
                      </Link>
                      {n.reasons.length > 0 && ` — ${n.reasons.join(" · ")}`}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {overview.data.open_decisions.length > 0 && (
              <ToneBadge
                tone="warning"
                size="xs"
                label={`${t("project_hub.activity.open_decisions")}: ${overview.data.open_decisions.length}`}
              />
            )}
          </>
        ) : null}
      </HubCard>
    </li>
  );
});

/** S01 Workspace overview: project state, decisions needing me, current work. */
export const WorkspaceOverviewPage = observer(function WorkspaceOverviewPage({
  workspaceSlug,
}: {
  workspaceSlug: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { joinedProjectIds } = useProject();
  const notifications = useHubResource<TPHNotificationItem[]>(PH_KEYS.notifications(workspaceSlug), () =>
    store.collaborationService.listNotifications(workspaceSlug)
  );

  return (
    <HubPage title={t("project_hub.overview.title")}>
      <HubSection title={t("project_hub.overview.my_decisions")} as="h2">
        <HubResourceBoundary
          resource={notifications}
          loadingRows={2}
          isEmpty={(d) => d.filter((n) => !n.read_at && n.delivery === "immediate").length === 0}
          empty={<HubEmpty title={t("project_hub.overview.empty")} />}
        >
          {(data) => (
            <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
              {data
                .filter((n) => !n.read_at && n.delivery === "immediate")
                .map((n) => (
                  <li key={n.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-body-xs-regular">
                    <ToneBadge
                      tone={n.category === "decision_needed" || n.category === "blocked" ? "warning" : "info"}
                      size="xs"
                      label={n.category}
                    />
                    {n.target.url ? (
                      <Link
                        href={n.target.url}
                        className="focus-visible:outline-accent-primary text-primary underline-offset-2 hover:underline focus-visible:outline-2"
                      >
                        {n.title}
                      </Link>
                    ) : (
                      <span className="text-primary">{n.title}</span>
                    )}
                    {n.count > 1 && <span className="text-tertiary">×{n.count}</span>}
                  </li>
                ))}
            </ul>
          )}
        </HubResourceBoundary>
      </HubSection>

      <HubSection title={t("project_hub.overview.projects")} as="h2">
        {joinedProjectIds.length === 0 ? (
          <HubEmpty />
        ) : (
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {joinedProjectIds.map((projectId) => (
              <ProjectOverviewCard key={projectId} workspaceSlug={workspaceSlug} projectId={projectId} />
            ))}
          </ul>
        )}
      </HubSection>
    </HubPage>
  );
});
