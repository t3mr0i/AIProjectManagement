/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import type { TPHActivityResponse } from "@plane/types";
import { cn, groupActivityByDay } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { ActivityGroupItem } from "../common/activity-group";
import { HubTextField } from "../common/field";
import { HubPage } from "../common/page";
import { HubCard, HubSection } from "../common/section";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TRange = "last_visit" | "today" | "7d" | "custom";

const startOfToday = () => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
};

/**
 * S02 Project activity (J08): "Since my last visit" by default, grouped by package and day with
 * reasons and open decisions; expanding shows raw events and sources.
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
  const { formatDate, formatAge } = useHubFormatters();
  const [range, setRange] = useState<TRange>("last_visit");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const visitMarked = useRef(false);

  const { since, until } = useMemo(() => {
    switch (range) {
      case "today":
        return { since: startOfToday(), until: "" };
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

  const activity = useHubResource<TPHActivityResponse>(PH_KEYS.activity(workspaceSlug, projectId, since, until), () =>
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

  const ranges: { key: TRange; label: string }[] = [
    { key: "last_visit", label: t("project_hub.activity.since_last_visit") },
    { key: "today", label: t("project_hub.activity.today") },
    { key: "7d", label: t("project_hub.activity.last_7_days") },
    { key: "custom", label: t("project_hub.activity.range") },
  ];

  return (
    <HubPage
      title={t("project_hub.activity.title")}
      actions={
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("project_hub.activity.mark_visit")}
          onClick={() => void markVisit(false)}
        />
      }
    >
      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label={t("project_hub.activity.filter_label")} className="flex flex-wrap gap-1">
          {ranges.map((r) => (
            <button
              key={r.key}
              type="button"
              aria-pressed={range === r.key}
              onClick={() => setRange(r.key)}
              className={cn(
                "focus-visible:outline-accent-primary rounded-md border px-2.5 py-1 text-body-xs-medium focus-visible:outline-2 focus-visible:outline-offset-2",
                range === r.key
                  ? "border-accent-strong bg-accent-subtle text-accent-primary"
                  : "border-subtle text-secondary hover:bg-layer-1"
              )}
            >
              {range === r.key ? "✓ " : ""}
              {r.label}
            </button>
          ))}
        </div>
        {range === "custom" && (
          <div className="flex flex-wrap gap-2">
            <HubTextField type="date" label={t("project_hub.activity.from")} value={from} onChange={setFrom} />
            <HubTextField type="date" label={t("project_hub.activity.to")} value={to} onChange={setTo} />
          </div>
        )}
      </div>

      <HubResourceBoundary resource={activity} loadingRows={5}>
        {(data) => (
          <div className="flex flex-col gap-5">
            {(data.source_health ?? []).length > 0 && (
              <ul className="flex flex-wrap gap-2" aria-label={t("project_hub.settings.health")}>
                {(data.source_health ?? []).map((source) => (
                  <li key={source.source}>
                    <ToneBadge
                      tone={source.status && source.status !== "active" ? "warning" : "neutral"}
                      size="xs"
                      label={t("project_hub.activity.source_health", {
                        source: source.source,
                        time: formatAge(source.last_synced_at),
                      })}
                    />
                  </li>
                ))}
              </ul>
            )}
            {(data.open_decisions ?? []).length > 0 && (
              <HubSection title={t("project_hub.activity.open_decisions")} as="h2">
                <HubCard>
                  <ul className="flex flex-col gap-1">
                    {(data.open_decisions ?? []).map((d) => (
                      <li key={d.id} className="flex items-center gap-2 text-body-xs-regular text-primary">
                        <ToneBadge tone="warning" size="xs" label={t("project_hub.activity.decision_needed")} />
                        {d.issue_id ? (
                          <Link
                            href={`/${workspaceSlug}/projects/${projectId}/issues/${d.issue_id}`}
                            className="focus-visible:outline-accent-primary underline-offset-2 hover:underline focus-visible:outline-2"
                          >
                            {d.title}
                          </Link>
                        ) : (
                          <span>{d.title}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </HubCard>
              </HubSection>
            )}
            {data.groups.length === 0 ? (
              <HubEmpty title={t("project_hub.activity.empty")} />
            ) : (
              groupActivityByDay(data.groups).map((section) => (
                <section key={section.day} className="flex flex-col gap-2" aria-label={formatDate(section.day)}>
                  <h2 className="text-caption-md-medium text-tertiary">{formatDate(section.day)}</h2>
                  {section.groups.map((group) => (
                    <ActivityGroupItem
                      key={`${group.issue_id}-${group.day}-${group.first_at}`}
                      group={group}
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                    />
                  ))}
                </section>
              ))
            )}
          </div>
        )}
      </HubResourceBoundary>
    </HubPage>
  );
});
