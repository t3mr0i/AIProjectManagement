/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import {
  BookClosedOutline,
  ChatOutline,
  CheckDoneOutline,
  ClockOutline,
  CubeOutline,
  FolderOutline,
  ProjectsOutline,
  SearchOutline,
  WorkItemsOutline,
} from "@makeplane/propel/icons";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { useTranslation } from "@plane/i18n";
import type { TPHSearchResult } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const TYPES = ["package", "decision", "page", "message", "event", "upload"] as const;

const TYPE_ICON: Record<string, TGlyph> = {
  package: CubeOutline as TGlyph,
  issue: WorkItemsOutline as TGlyph,
  decision: CheckDoneOutline as TGlyph,
  page: BookClosedOutline as TGlyph,
  message: ChatOutline as TGlyph,
  event: ClockOutline as TGlyph,
  upload: FolderOutline as TGlyph,
};

/** Display order of result groups (unknown types go last). */
const TYPE_ORDER = ["package", "issue", "decision", "page", "message", "event", "upload"];

const resultHref = (workspaceSlug: string, result: TPHSearchResult) => {
  if ((result.type === "package" || result.type === "issue") && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/issues/${result.issue_id ?? result.id}`;
  if (result.issue_id && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/issues/${result.issue_id}`;
  if (result.type === "page" && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/pages/${result.id}`;
  if (result.type === "message" && result.conversation_id)
    return `/${workspaceSlug}/hub/messages?c=${result.conversation_id}`;
  return undefined;
};

const SOURCE_LABEL: Record<string, string> = { plane: "Plane", package_flow: "Project Hub" };

const ResultRow = observer(function ResultRow({
  workspaceSlug,
  result,
}: {
  workspaceSlug: string;
  result: TPHSearchResult;
}) {
  const { t } = useTranslation();
  const { getPartialProjectById } = useProject();
  const { formatAge, formatDateTime } = useHubFormatters();
  const Glyph = TYPE_ICON[result.type] ?? (SearchOutline as TGlyph);
  const project = result.project_id ? getPartialProjectById(result.project_id) : undefined;
  const typeLabel = result.type in TYPE_ICON ? t(`project_hub.search.type.${result.type}`) : result.type;
  return (
    <HubListRow
      href={resultHref(workspaceSlug, result)}
      navId={`${result.type}-${result.id}`}
      identifier={result.identifier}
      icon={<Glyph className="size-4 text-tertiary" role="img" aria-label={typeLabel} />}
      title={
        <>
          {result.title}
          {result.snippet && (
            <span className="font-normal ml-2 text-tertiary" title={result.snippet}>
              {result.snippet}
            </span>
          )}
        </>
      }
      meta={
        <>
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
            label={SOURCE_LABEL[result.source] ?? result.source}
            title={t("project_hub.search.source", { source: result.source })}
            className="hidden md:inline-flex"
          />
        </>
      }
      trailing={
        <span
          className="w-14 text-right text-caption-md-regular text-tertiary tabular-nums"
          title={t("project_hub.search.updated", { time: formatDateTime(result.updated_at) })}
        >
          {formatAge(result.updated_at)}
        </span>
      }
    />
  );
});

/** S11 Search: ACL-filtered typed results; counts only what the viewer can access. */
export const WorkspaceSearchPage = observer(function WorkspaceSearchPage({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const listRef = useRef<HTMLDivElement>(null);
  const onListKeyDown = useHubListNavigation(listRef);
  const [query, setQuery] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState<{ q: string; types: string[] } | null>(null);
  const results = useHubResource<TPHSearchResult[]>(
    submitted ? PH_KEYS.search(workspaceSlug, submitted.q, submitted.types.join(",")) : null,
    async () => await store.knowledgeService.search(workspaceSlug, submitted?.q ?? "", submitted?.types)
  );

  const submit = (nextTypes = types) => {
    const q = query.trim();
    if (q) setSubmitted({ q, types: nextTypes });
  };

  const toggleType = (type: string) => {
    const next = types.includes(type) ? types.filter((p) => p !== type) : [...types, type];
    setTypes(next);
    if (submitted) submit(next);
  };

  return (
    <HubPage title={t("project_hub.search.title")} width="full" flush>
      <form
        role="search"
        className="flex shrink-0 flex-col gap-2 border-b border-subtle px-4 py-3 md:px-6"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex h-9 w-full max-w-2xl items-center gap-2 rounded-md border border-subtle bg-layer-1 px-2.5 transition-colors duration-100 focus-within:border-accent-strong">
          <SearchOutline className="size-4 shrink-0 text-tertiary" aria-hidden="true" />
          <label htmlFor="project-hub-search" className="sr-only">
            {t("project_hub.common.search")}
          </label>
          <input
            id="project-hub-search"
            type="search"
            enterKeyHint="search"
            autoComplete="off"
            placeholder={t("project_hub.search.placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-full min-w-0 flex-1 bg-transparent text-13 text-primary outline-none placeholder:text-placeholder"
          />
          <kbd className="hidden shrink-0 rounded-sm border border-subtle px-1 text-caption-sm-regular text-placeholder sm:inline">
            ↵
          </kbd>
        </div>
        <div
          className="flex min-w-0 flex-wrap items-center gap-1"
          role="group"
          aria-label={t("project_hub.search.types")}
        >
          {TYPES.map((type) => {
            const Glyph = TYPE_ICON[type] ?? (SearchOutline as TGlyph);
            const active = types.includes(type);
            return (
              <button
                key={type}
                type="button"
                aria-pressed={active}
                onClick={() => toggleType(type)}
                className={cn(
                  "flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-caption-md-regular transition-colors duration-100 focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none",
                  active
                    ? "border-accent-strong bg-accent-primary/10 text-primary"
                    : "border-subtle bg-layer-1 text-secondary hover:bg-layer-transparent-hover hover:text-primary"
                )}
              >
                <Glyph className="size-3 shrink-0" aria-hidden="true" />
                {t(`project_hub.search.type.${type}`)}
              </button>
            );
          })}
          <span className="ml-auto hidden text-caption-md-regular text-placeholder md:inline">
            {t("project_hub.search.hint")}
          </span>
        </div>
      </form>

      <div
        ref={listRef}
        role="group"
        aria-label={t("project_hub.search.title")}
        onKeyDown={onListKeyDown}
        className="flex min-w-0 flex-col pb-8"
      >
        {submitted ? (
          <HubResourceBoundary
            resource={results}
            loadingRows={4}
            isEmpty={(d) => d.length === 0}
            empty={
              <HubEmptyState
                icon={SearchOutline as TGlyph}
                title={t("project_hub.search.empty")}
                description={t("project_hub.search.hint")}
              />
            }
          >
            {(data) => {
              const groups = new Map<string, TPHSearchResult[]>();
              for (const result of data) groups.set(result.type, [...(groups.get(result.type) ?? []), result]);
              const rank = (type: string) => (TYPE_ORDER.indexOf(type) === -1 ? 99 : TYPE_ORDER.indexOf(type));
              const ordered = TYPE_ORDER.concat([...groups.keys()].filter((k) => rank(k) === 99))
                .filter((type) => groups.has(type))
                .map((type) => [type, groups.get(type) ?? []] as const);
              return (
                <div className="flex min-w-0 flex-col">
                  <p
                    className="flex h-8 items-center px-4 text-caption-md-regular text-tertiary md:px-6"
                    aria-live="polite"
                  >
                    {t("project_hub.search.results_count", { count: data.length })}
                  </p>
                  {ordered.map(([type, items]) => (
                    <HubListGroup
                      key={type}
                      icon={TYPE_ICON[type] ?? (SearchOutline as TGlyph)}
                      title={type in TYPE_ICON ? t(`project_hub.search.type.${type}`) : type}
                      count={items.length}
                    >
                      <HubList>
                        {items.map((result) => (
                          <ResultRow
                            key={`${result.type}-${result.id}`}
                            workspaceSlug={workspaceSlug}
                            result={result}
                          />
                        ))}
                      </HubList>
                    </HubListGroup>
                  ))}
                </div>
              );
            }}
          </HubResourceBoundary>
        ) : (
          <HubEmptyState
            icon={SearchOutline as TGlyph}
            title={t("project_hub.search.start_title")}
            description={t("project_hub.search.hint")}
          />
        )}
      </div>
    </HubPage>
  );
});
