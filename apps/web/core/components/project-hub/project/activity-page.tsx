/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { ActivityOutline, CalendarOutline, WarningTriangleOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHActivityFeed } from "@plane/types";
import { adaptActivityFeed, groupActivityByDay } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubProjectAIReportCard } from "../ai/report-card";
import { ActivityGroupItem } from "../common/activity-group";
import { HubTextField } from "../common/field";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;
type TRange = "last_visit" | "today" | "7d" | "custom";
const RANGES: TRange[] = ["last_visit", "today", "7d", "custom"];

/**
 * S02 Project activity (J08): "Since my last visit" by default, grouped by day (sticky group bars)
 * and package with reasons and open decisions; expanding shows raw events and sources.
 */
export const ProjectActivityPage = observer(function ProjectActivityPage({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDate, formatDateTime } = useHubFormatters();
  const listRef = useRef<HTMLDivElement>(null);
  const onKeyDown = useHubListNavigation(listRef);
  const [range, setRange] = useState<TRange>("last_visit");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const visitMarked = useRef(false);

  const { since, until } = useMemo(() => {
    switch (range) {
      case "today":
        return { since: "today", until: "" };
      case "7d":
        return { since: new Date(Date.now() - 7 * 86_400_000).toISOString(), until: "" };
      case "custom":
        return {
          since: from ? new Date(from).toISOString() : "last_visit",
          until: to ? new Date(`${to}T23:59:59`).toISOString() : "",
        };
      default:
        return { since: "last_visit", until: "" };
    }
  }, [range, from, to]);

  const activity = useHubResource<TPHActivityFeed>(PH_KEYS.activity(workspaceSlug, projectId, since, until), () =>
    store.knowledgeService.getActivity(workspaceSlug, projectId, { since, ...(until ? { until } : {}) })
  );

  const markVisit = async (silent: boolean) => {
    try {
      await store.knowledgeService.setVisitMarker(workspaceSlug, projectId);
      if (!silent) showHubSuccessToast(t("project_hub.activity.marked_visit"));
    } catch (error) {
      if (!silent) showHubErrorToast(t, error);
    }
  };

  // The visit marker is a personal view marker only; set once after the "since last visit" view loaded.
  useEffect(() => {
    if (range === "last_visit" && activity.data && !visitMarked.current) {
      visitMarked.current = true;
      void markVisit(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, activity.data]);

  const rangeLabel: Record<TRange, string> = {
    last_visit: t("project_hub.activity.since_last_visit"),
    today: t("project_hub.activity.today"),
    "7d": t("project_hub.activity.last_7_days"),
    custom: t("project_hub.activity.range"),
  };

  return (
    <HubPage
      title={t("project_hub.activity.title")}
      flush
      tabs={{
        "aria-label": t("project_hub.activity.filter_label"),
        activeKey: range,
        onTabChange: (key) => setRange(key as TRange),
        tabs: RANGES.map((key) => ({
          key,
          label: rangeLabel[key],
          icon: key === "custom" ? (CalendarOutline as TGlyph) : undefined,
        })),
      }}
      actions={
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          label={t("project_hub.activity.mark_visit")}
          onClick={() => void markVisit(false)}
        />
      }
    >
      <div className="border-b border-subtle px-4 py-4 md:px-6">
        <HubProjectAIReportCard workspaceSlug={workspaceSlug} projectId={projectId} className="max-w-3xl" />
      </div>
      {range === "custom" && (
        <div className="flex flex-wrap items-end gap-2 border-b border-subtle px-4 py-2 md:px-6">
          <HubTextField type="date" label={t("project_hub.activity.from")} value={from} onChange={setFrom} />
          <HubTextField type="date" label={t("project_hub.activity.to")} value={to} onChange={setTo} />
        </div>
      )}

      <HubResourceBoundary resource={activity} loadingRows={6}>
        {(data) => {
          const days = groupActivityByDay(adaptActivityFeed(data));
          return (
            // oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- list navigation (j/k/Enter) on the container
            <div ref={listRef} onKeyDown={onKeyDown} className="flex min-w-0 flex-col pb-6">
              <p className="flex h-8 items-center px-4 text-caption-md-regular text-tertiary md:px-6">
                {t("project_hub.activity.period", { from: formatDateTime(data.since), to: formatDateTime(data.until) })}
              </p>
              {data.open_decisions.length > 0 && (
                <HubListGroup
                  icon={WarningTriangleOutline as TGlyph}
                  title={t("project_hub.activity.open_decisions")}
                  count={data.open_decisions.length}
                >
                  <HubList aria-label={t("project_hub.activity.open_decisions")}>
                    {data.open_decisions.map((d) => (
                      <HubListRow
                        key={d.id}
                        href={d.issue_id ? `/${workspaceSlug}/projects/${projectId}/issues/${d.issue_id}` : undefined}
                        navId={d.id}
                        icon={WarningTriangleOutline as TGlyph}
                        title={d.title}
                        meta={
                          <span className="text-caption-md-regular text-warning-primary">
                            {t("project_hub.activity.decision_needed")}
                          </span>
                        }
                      />
                    ))}
                  </HubList>
                </HubListGroup>
              )}
              {days.length === 0 ? (
                <HubEmptyState icon={ActivityOutline as TGlyph} title={t("project_hub.activity.empty")} />
              ) : (
                days.map((section) => (
                  <HubListGroup
                    key={section.day}
                    icon={CalendarOutline as TGlyph}
                    title={formatDate(section.day)}
                    count={section.groups.reduce((n, g) => n + g.event_count, 0)}
                  >
                    {section.groups.map((group) => (
                      <ActivityGroupItem
                        key={`${group.issue_id}-${group.day}-${group.first_at}`}
                        group={group}
                        workspaceSlug={workspaceSlug}
                        projectId={projectId}
                        className="border-b border-subtle last:border-b-0"
                      />
                    ))}
                  </HubListGroup>
                ))
              )}
            </div>
          );
        }}
      </HubResourceBoundary>
    </HubPage>
  );
});
