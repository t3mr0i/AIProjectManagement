/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHDecision, TPHSearchResult } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextField } from "../common/field";
import { HubPage } from "../common/page";
import { HubCard, HubSection } from "../common/section";
import { HubSearchResults } from "../common/search-results";
import { HubEmpty, HubPartialBanner, HubResourceBoundary } from "../common/states";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { DiagramsPanel } from "../diagrams/diagrams-panel";
import { ProjectUploadsSection } from "./uploads-section";

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
  const { formatDate } = useHubFormatters();
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
    <HubPage title={t("project_hub.knowledge.title")}>
      {failed.length === 1 && <HubPartialBanner sections={failed} />}
      <form
        role="search"
        className="max-w-xl"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim());
        }}
      >
        <HubTextField
          label={t("project_hub.common.search")}
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
          empty={<HubEmpty title={t("project_hub.knowledge.search_empty")} />}
        >
          {(data) => <HubSearchResults workspaceSlug={workspaceSlug} results={data} />}
        </HubResourceBoundary>
      )}

      <HubSection title={t("project_hub.knowledge.decisions")} as="h2">
        <HubResourceBoundary
          resource={decisions}
          loadingRows={2}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.knowledge.decisions_empty")} />}
        >
          {(data) => (
            <ul className="flex flex-col gap-2">
              {data.map((d) => (
                <li key={d.id}>
                  <HubCard className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body-xs-medium text-primary">{d.title}</span>
                      {d.source_changed_since_decision && (
                        <ToneBadge tone="warning" size="xs" label={t("project_hub.history.source_changed")} />
                      )}
                    </div>
                    <p className="text-caption-sm-regular whitespace-pre-wrap text-secondary">{d.text}</p>
                    <p className="text-caption-sm-regular text-tertiary">
                      {formatDate(d.confirmed_at ?? d.created_at)}
                    </p>
                  </HubCard>
                </li>
              ))}
            </ul>
          )}
        </HubResourceBoundary>
      </HubSection>

      <ProjectUploadsSection workspaceSlug={workspaceSlug} projectId={projectId} />
      <div className="@container">
        <DiagramsPanel workspaceSlug={workspaceSlug} projectId={projectId} headingLevel="h2" />
      </div>
    </HubPage>
  );
});
