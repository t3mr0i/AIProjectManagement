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
import type { TPHActivityGroup } from "@plane/types";
import { generateWorkItemLink } from "@plane/utils";
// local imports
import { PackagePhaseIndicator } from "./phase-indicator";
import { ToneBadge } from "./tone-badge";
import { useHubFormatters } from "./use-relative-time";

type Props = {
  group: TPHActivityGroup;
  workspaceSlug: string;
  projectId: string;
  /** Hide the package title (inside the package itself). */
  hidePackage?: boolean;
};

/**
 * Compacted activity group (DESIGN_BRIEF ActivityGroup): package, understandable change, reasons,
 * outcome, responsible actor, count + covered period; raw events and sources are expandable.
 */
export const ActivityGroupItem = observer(function ActivityGroupItem({
  group,
  workspaceSlug,
  projectId,
  hidePackage,
}: Props) {
  const { t } = useTranslation();
  const { formatDateTime } = useHubFormatters();
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const packageLabel =
    group.project_identifier && group.sequence_id
      ? `${group.project_identifier}-${group.sequence_id}`
      : (group.package_name ?? "");
  const actorKey =
    group.responsible_kind === "agent"
      ? "project_hub.activity.actor_agent"
      : group.responsible_kind === "system"
        ? "project_hub.activity.actor_system"
        : "project_hub.activity.actor_human";

  return (
    <article className="flex flex-col gap-1.5 rounded-md border border-subtle bg-layer-1 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {!hidePackage &&
          (group.issue_id ? (
            <Link
              href={generateWorkItemLink({
                workspaceSlug,
                projectId,
                issueId: group.issue_id,
                projectIdentifier: group.project_identifier ?? null,
                sequenceId: group.sequence_id ?? null,
              })}
              className="focus-visible:outline-accent-primary text-body-xs-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2"
            >
              {packageLabel ? `${packageLabel} · ` : ""}
              {group.package_name}
            </Link>
          ) : (
            <span className="text-body-xs-medium text-secondary">{t("project_hub.activity.no_package")}</span>
          ))}
        {group.phase && (
          <PackagePhaseIndicator status={{ phase: group.phase, flags: [], delivery: "unknown" }} variant="compact" />
        )}
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
      {group.outcome && <p className="text-caption-sm-regular text-secondary">{group.outcome}</p>}
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
          onClick={() => setExpanded((v) => !v)}
          className="focus-visible:outline-accent-primary rounded-sm text-accent-primary underline-offset-2 hover:underline focus-visible:outline-2"
        >
          {t("project_hub.history.raw_events", { count: group.events.length })}
        </button>
      </div>
      {expanded && (
        <ol id={detailsId} className="flex flex-col gap-1 border-l-2 border-subtle pl-3">
          {group.events.map((event) => (
            <li key={event.id} className="flex flex-col text-caption-sm-regular">
              <span className="text-secondary">
                <code className="font-mono text-tertiary">{event.event_type}</code> — {event.summary}
              </span>
              <span className="text-tertiary">
                {formatDateTime(event.occurred_at)} ·{" "}
                {t("project_hub.activity.source", {
                  source: `${event.source_kind}${event.source_id ? `:${event.source_id}` : ""}`,
                })}
                {event.is_imported && ` · ${t("project_hub.activity.imported")}`}
                {event.is_fixture && ` · ${t("project_hub.activity.fixture")}`}
              </span>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
});
