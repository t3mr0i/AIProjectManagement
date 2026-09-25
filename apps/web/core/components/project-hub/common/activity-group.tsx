/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHActivityEntry, TPHActivityGroup } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { showHubErrorToast } from "./toast";
import { ToneBadge } from "./tone-badge";
import { useHubFormatters } from "./use-relative-time";

type Props = {
  group: TPHActivityGroup;
  workspaceSlug: string;
  projectId: string;
  /** Hide the package title (inside the package itself). */
  hidePackage?: boolean;
};

const EntryLine = observer(function EntryLine({ entry }: { entry: TPHActivityEntry }) {
  const { t } = useTranslation();
  const { formatDateTime } = useHubFormatters();
  const source = entry.kind === "summary" ? "package_flow" : entry.source;
  return (
    <li className="flex flex-col text-caption-sm-regular">
      <span className="text-secondary">
        <code className="font-mono text-tertiary">{entry.event_type}</code> — {entry.summary}
      </span>
      <span className="text-tertiary">
        {entry.kind === "summary"
          ? t("project_hub.activity.period", {
              from: formatDateTime(entry.first_at),
              to: formatDateTime(entry.occurred_at),
            })
          : formatDateTime(entry.occurred_at)}{" "}
        · {t("project_hub.activity.source", { source })}
        {entry.kind === "event" && entry.reason && ` · ${entry.reason}`}
        {entry.kind === "event" && entry.is_fixture && ` · ${t("project_hub.activity.fixture")}`}
      </span>
    </li>
  );
});

/**
 * Compacted activity group (DESIGN_BRIEF ActivityGroup): package, understandable change, reasons,
 * responsible actor, count + covered period. "Technical details" shows the entries and, for
 * compacted summaries, loads the underlying raw events (`?ids=`) with their sources.
 */
export const ActivityGroupItem = observer(function ActivityGroupItem({
  group,
  workspaceSlug,
  projectId,
  hidePackage,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime } = useHubFormatters();
  const [expanded, setExpanded] = useState(false);
  const [raw, setRaw] = useState<TPHActivityEntry[] | null>(null);
  const detailsId = useId();
  const actorKey =
    group.responsible_kind === "agent"
      ? "project_hub.activity.actor_agent"
      : group.responsible_kind === "system"
        ? "project_hub.activity.actor_system"
        : "project_hub.activity.actor_human";
  const rawIds = group.entries.flatMap((e) => (e.kind === "summary" ? e.raw_ids : []));

  const toggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && rawIds.length > 0 && raw === null) {
      try {
        setRaw(await store.knowledgeService.getRawEvents(workspaceSlug, projectId, rawIds));
      } catch (error) {
        showHubErrorToast(t, error);
      }
    }
  };

  return (
    <article className="flex flex-col gap-1.5 rounded-md border border-subtle bg-layer-1 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {!hidePackage &&
          (group.issue_id ? (
            <Link
              href={`/${workspaceSlug}/projects/${projectId}/issues/${group.issue_id}`}
              className="focus-visible:outline-accent-primary text-body-xs-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2"
            >
              {group.identifier ? `${group.identifier} · ` : ""}
              {group.package_name}
            </Link>
          ) : (
            <span className="text-body-xs-medium text-secondary">{t("project_hub.activity.no_package")}</span>
          ))}
        {group.decision_needed && (
          <ToneBadge tone="warning" size="xs" label={t("project_hub.activity.decision_needed")} />
        )}
      </div>
      <p className="text-body-xs-regular text-primary">{group.summary}</p>
      {group.reasons.length > 0 && (
        <p className="text-caption-sm-regular text-secondary">
          <span className="text-tertiary">{t("project_hub.activity.reasons")}: </span>
          {group.reasons.join(" · ")}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 text-caption-sm-regular text-tertiary">
        <span>{t(actorKey)}</span>
        <span aria-hidden="true">·</span>
        <span>{t("project_hub.activity.events", { count: group.event_count })}</span>
        <span aria-hidden="true">·</span>
        <span>
          {t("project_hub.activity.period", {
            from: formatDateTime(group.first_at),
            to: formatDateTime(group.last_at),
          })}
        </span>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={detailsId}
          onClick={() => void toggle()}
          className="focus-visible:outline-accent-primary rounded-sm text-accent-primary underline-offset-2 hover:underline focus-visible:outline-2"
        >
          {t("project_hub.history.raw_events", { count: group.event_count })}
        </button>
      </div>
      {expanded && (
        <ol id={detailsId} className="flex flex-col gap-1 border-l-2 border-subtle pl-3">
          {group.entries.map((entry, i) => (
            // oxlint-disable-next-line react/no-array-index-key -- summaries have no id
            <EntryLine key={entry.kind === "summary" ? `s-${entry.event_type}-${i}` : entry.id} entry={entry} />
          ))}
          {raw?.map((entry) => (entry.kind === "summary" ? null : <EntryLine key={`raw-${entry.id}`} entry={entry} />))}
        </ol>
      )}
    </article>
  );
});
