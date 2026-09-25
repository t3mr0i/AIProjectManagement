/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useId, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { AgentOutline, ChevronRightOutline, CubeOutline, SettingsOutline, UserOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHActivityEntry, TPHActivityGroup } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { HubGroupBar } from "./list";
import { showHubErrorToast } from "./toast";
import { ToneBadge } from "./tone-badge";
import { useHubFormatters } from "./use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const ACTOR_ICON: Record<"human" | "agent" | "system", TGlyph> = {
  human: UserOutline as TGlyph,
  agent: AgentOutline as TGlyph,
  system: SettingsOutline as TGlyph,
};

export type THubTimelineRowProps = {
  /** 16px avatar or glyph. Defaults to a person glyph. */
  icon?: ReactNode;
  /** Actor name in normal weight, before the text. */
  actor?: ReactNode;
  children: ReactNode;
  /** Muted relative time on the right (already formatted). */
  time?: ReactNode;
  /** `title` for the exact timestamp. */
  timeTitle?: string;
  /** Inline quiet detail toggle rendered after the text. */
  trailing?: ReactNode;
  className?: string;
};

/** One compact timeline line: 16px icon, one line of text (actor + change), muted relative time. */
export function HubTimelineRow({ icon, actor, children, time, timeTitle, trailing, className }: THubTimelineRowProps) {
  return (
    <div className={cn("flex min-h-7 min-w-0 items-center gap-2 px-3 text-13", className)}>
      <span
        className="flex size-4 shrink-0 items-center justify-center text-tertiary [&>svg]:size-4"
        aria-hidden="true"
      >
        {icon ?? <UserOutline className="size-4" />}
      </span>
      <span className="min-w-0 flex-1 truncate text-secondary">
        {actor && <span className="text-primary">{actor} </span>}
        {children}
      </span>
      {trailing && <span className="flex shrink-0 items-center">{trailing}</span>}
      {time && (
        <span className="shrink-0 text-caption-md-regular text-tertiary tabular-nums" title={timeTitle}>
          {time}
        </span>
      )}
    </div>
  );
}

const EntryLine = observer(function EntryLine({ entry }: { entry: TPHActivityEntry }) {
  const { t } = useTranslation();
  const { formatDateTime, formatAge } = useHubFormatters();
  const source = entry.kind === "summary" ? "package_flow" : entry.source;
  const actorKind = entry.kind === "event" ? entry.actor_kind : entry.kind === "native" ? "human" : "system";
  const Glyph = ACTOR_ICON[actorKind];
  const details = [
    t("project_hub.activity.source", { source }),
    entry.kind === "event" && entry.reason ? entry.reason : null,
    entry.kind === "event" && entry.is_fixture ? t("project_hub.activity.fixture") : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="flex min-h-7 min-w-0 items-center gap-2 text-caption-md-regular">
      <Glyph className="size-3.5 shrink-0 text-placeholder" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-secondary" title={details}>
        <code className="font-mono text-tertiary">{entry.event_type}</code> {entry.summary}
        <span className="text-placeholder"> · {details}</span>
      </span>
      <span
        className="shrink-0 text-tertiary tabular-nums"
        title={
          entry.kind === "summary"
            ? t("project_hub.activity.period", {
                from: formatDateTime(entry.first_at),
                to: formatDateTime(entry.occurred_at),
              })
            : formatDateTime(entry.occurred_at)
        }
      >
        {formatAge(entry.occurred_at)}
      </span>
    </li>
  );
});

type Props = {
  group: TPHActivityGroup;
  workspaceSlug: string;
  projectId: string;
  /** Hide the package title (inside the package itself). */
  hidePackage?: boolean;
  /** Extra classes on the wrapper. */
  className?: string;
};

/**
 * Compacted activity group (DESIGN_BRIEF ActivityGroup) as a Linear-style timeline block: a group
 * bar (package · count · period) followed by one-line rows — the understandable change, reasons and
 * the responsible actor — and a quiet inline "Technical details" toggle that lists the entries and,
 * for compacted summaries, loads the underlying raw events (`?ids=`) with their sources.
 */
export const ActivityGroupItem = observer(function ActivityGroupItem({
  group,
  workspaceSlug,
  projectId,
  hidePackage,
  className,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime, formatAge } = useHubFormatters();
  const [expanded, setExpanded] = useState(false);
  const [raw, setRaw] = useState<TPHActivityEntry[] | null>(null);
  const detailsId = useId();
  const actorKind = group.responsible_kind ?? "human";
  const actorKey =
    actorKind === "agent"
      ? "project_hub.activity.actor_agent"
      : actorKind === "system"
        ? "project_hub.activity.actor_system"
        : "project_hub.activity.actor_human";
  const ActorGlyph = ACTOR_ICON[actorKind];
  const rawIds = group.entries.flatMap((e) => (e.kind === "summary" ? e.raw_ids : []));
  const period = t("project_hub.activity.period", {
    from: formatDateTime(group.first_at),
    to: formatDateTime(group.last_at),
  });

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

  const packageTitle = group.issue_id ? (
    <Link
      href={`/${workspaceSlug}/projects/${projectId}/issues/${group.issue_id}`}
      className="truncate hover:underline focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
    >
      {group.identifier && <span className="text-tertiary">{group.identifier} </span>}
      {group.package_name}
    </Link>
  ) : (
    t("project_hub.activity.no_package")
  );

  return (
    <article className={cn("flex min-w-0 flex-col", className)}>
      {!hidePackage && (
        <HubGroupBar
          sticky={false}
          icon={CubeOutline as TGlyph}
          title={packageTitle}
          count={group.event_count}
          hint={period}
          trailing={
            group.decision_needed ? (
              <ToneBadge tone="warning" size="xs" label={t("project_hub.activity.decision_needed")} />
            ) : undefined
          }
        />
      )}
      <div className="flex min-w-0 flex-col py-1">
        <HubTimelineRow
          icon={<ActorGlyph />}
          actor={t(actorKey)}
          time={formatAge(group.last_at)}
          timeTitle={period}
          trailing={
            <>
              {hidePackage && group.decision_needed && (
                <ToneBadge tone="warning" size="xs" label={t("project_hub.activity.decision_needed")} />
              )}
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={detailsId}
                onClick={() => void toggle()}
                className="flex h-6 items-center gap-0.5 rounded-sm px-1 text-caption-md-regular text-tertiary transition-colors duration-100 hover:bg-layer-transparent-hover hover:text-secondary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
              >
                <ChevronRightOutline
                  className={cn("size-3 transition-transform duration-100", expanded && "rotate-90")}
                  aria-hidden="true"
                />
                {t("project_hub.history.raw_events", { count: group.event_count })}
              </button>
            </>
          }
        >
          <span className="text-primary">{group.summary}</span>
        </HubTimelineRow>
        {group.reasons.length > 0 && (
          <p className="truncate pr-3 pl-9 text-caption-md-regular text-tertiary" title={group.reasons.join(" · ")}>
            <span className="text-placeholder">{t("project_hub.activity.reasons")}: </span>
            {group.reasons.join(" · ")}
          </p>
        )}
        {expanded && (
          <ol id={detailsId} className="mt-1 ml-5 flex flex-col border-l border-subtle pr-3 pl-3">
            {group.entries.map((entry, i) => (
              // oxlint-disable-next-line react/no-array-index-key -- summaries have no id
              <EntryLine key={entry.kind === "summary" ? `s-${entry.event_type}-${i}` : entry.id} entry={entry} />
            ))}
            {raw?.map((entry) =>
              entry.kind === "summary" ? null : <EntryLine key={`raw-${entry.id}`} entry={entry} />
            )}
          </ol>
        )}
      </div>
    </article>
  );
});
