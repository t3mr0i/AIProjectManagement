/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useId, useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { CheckDoneOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHDecision, TPHSearchResult } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubTextField } from "../common/field";
import { HubList, HubListGroup, HubListRow, useHubListNavigation } from "../common/list";
import { HubPage } from "../common/page";
import { HubSearchResults } from "../common/search-results";
import { HubEmptyState, HubPartialBanner, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { DiagramsPanel } from "../diagrams/diagrams-panel";
import { ProjectUploadsSection } from "./uploads-section";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/** One decision as a list row; the text and rationale unfold inline below it. */
const DecisionRow = observer(function DecisionRow({ decision }: { decision: TPHDecision }) {
  const { t } = useTranslation();
  const { formatDate } = useHubFormatters();
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  return (
    <div className="flex min-w-0 flex-col border-b border-subtle last:border-b-0">
      <HubListRow
        onClick={() => setOpen((v) => !v)}
        navId={decision.id}
        icon={CheckDoneOutline as TGlyph}
        title={decision.title}
        aria-label={`${decision.title} (${open ? t("project_hub.common.collapse") : t("project_hub.common.expand")})`}
        className="border-b-0"
        meta={
          decision.source_changed_since_decision ? (
            <HubChip tone="warning" label={t("project_hub.history.source_changed")} />
          ) : undefined
        }
        trailing={
          <span className="text-caption-md-regular text-tertiary tabular-nums">
            {formatDate(decision.confirmed_at ?? decision.created_at)}
          </span>
        }
      />
      <div id={detailsId} role="region" className={cn("flex flex-col gap-1 py-2 pr-3 pl-11", !open && "hidden")}>
        <p className="text-13 whitespace-pre-wrap text-secondary">{decision.text}</p>
        {decision.rationale && <p className="text-caption-md-regular text-tertiary">{decision.rationale}</p>}
      </div>
    </div>
  );
});

/** Project knowledge (S11 scoped): search, decisions, uploads (scan/format, registration), diagrams (S08). */
export const ProjectKnowledgePage = observer(function ProjectKnowledgePage({
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
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const decisions = useHubResource<TPHDecision[]>(PH_KEYS.decisions(workspaceSlug, projectId), () =>
    store.collaborationService.listDecisions(workspaceSlug, projectId)
  );
  const search = useHubResource<TPHSearchResult[]>(
    submitted ? PH_KEYS.search(workspaceSlug, submitted, `project:${projectId}`) : null,
    async () =>
      (await store.knowledgeService.search(workspaceSlug, submitted)).filter((r) => r.project_id === projectId)
  );

  const failed = [decisions.error && decisions.data === undefined ? t("project_hub.knowledge.decisions") : null].filter(
    (v): v is string => !!v
  );

  return (
    <HubPage title={t("project_hub.knowledge.title")} flush>
      <div className="flex min-w-0 flex-col gap-3 px-4 pt-3 md:px-6">
        {failed.length === 1 && <HubPartialBanner sections={failed} />}
        <form
          role="search"
          className="max-w-md"
          onSubmit={(e) => {
            e.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <HubTextField
            label={t("project_hub.common.search")}
            hideLabel
            placeholder={t("project_hub.knowledge.search_placeholder")}
            value={query}
            onChange={setQuery}
          />
        </form>
        {submitted && (
          <HubResourceBoundary
            resource={search}
            loadingRows={3}
            isEmpty={(d) => d.length === 0}
            empty={<HubEmptyState title={t("project_hub.knowledge.search_empty")} />}
          >
            {(data) => <HubSearchResults workspaceSlug={workspaceSlug} results={data} />}
          </HubResourceBoundary>
        )}
      </div>

      {/* oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- list navigation (j/k/Enter) */}
      <div ref={listRef} onKeyDown={onKeyDown} className="flex min-w-0 flex-col gap-4 pt-3 pb-6">
        <HubResourceBoundary resource={decisions} loadingRows={2}>
          {(data) => (
            <HubListGroup
              icon={CheckDoneOutline as TGlyph}
              title={t("project_hub.knowledge.decisions")}
              count={data.length}
              showEmpty
              emptyLabel={t("project_hub.knowledge.decisions_empty")}
            >
              <HubList aria-label={t("project_hub.knowledge.decisions")}>
                {data.map((d) => (
                  <DecisionRow key={d.id} decision={d} />
                ))}
              </HubList>
            </HubListGroup>
          )}
        </HubResourceBoundary>

        <ProjectUploadsSection workspaceSlug={workspaceSlug} projectId={projectId} />
      </div>

      <div className="@container px-4 pb-6 md:px-6">
        <DiagramsPanel workspaceSlug={workspaceSlug} projectId={projectId} headingLevel="h2" />
      </div>
    </HubPage>
  );
});
