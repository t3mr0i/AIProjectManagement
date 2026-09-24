/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHDecision, TPHSearchResult, TPHUploadRecord, TPHUploadScanStatus } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextField } from "../common/field";
import { HubPage } from "../common/page";
import { HubCard, HubSection } from "../common/section";
import { normalizeSearch, HubSearchResults } from "../common/search-results";
import { HubEmpty, HubPartialBanner, HubResourceBoundary } from "../common/states";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

const SCAN_TONE: Record<TPHUploadScanStatus, TProjectHubTone> = {
  pending: "neutral",
  clean: "success",
  quarantined: "danger",
  failed: "warning",
};

/** Project knowledge (S11 scoped): uploads with scan/format state, decisions, search in project. */
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

  const uploads = useHubResource<TPHUploadRecord[]>(PH_KEYS.uploads(workspaceSlug, projectId), () =>
    store.knowledgeService.listUploads(workspaceSlug, projectId)
  );
  const decisions = useHubResource<TPHDecision[]>(PH_KEYS.decisions(workspaceSlug, projectId), () =>
    store.collaborationService.listDecisions(workspaceSlug, projectId)
  );
  const search = useHubResource<TPHSearchResult[]>(
    submitted ? PH_KEYS.search(workspaceSlug, submitted, `project:${projectId}`) : null,
    async () =>
      normalizeSearch(await store.knowledgeService.search(workspaceSlug, submitted)).filter(
        (r) => r.project_id === projectId
      )
  );

  const failed = [
    uploads.error && uploads.data === undefined ? t("project_hub.knowledge.uploads") : null,
    decisions.error && decisions.data === undefined ? t("project_hub.knowledge.decisions") : null,
  ].filter((v): v is string => !!v);

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

      <HubSection title={t("project_hub.knowledge.uploads")} as="h2">
        <HubResourceBoundary
          resource={uploads}
          loadingRows={2}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.knowledge.uploads_empty")} />}
        >
          {(data) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-body-xs-regular">
                <caption className="sr-only">{t("project_hub.knowledge.uploads")}</caption>
                <thead>
                  <tr className="border-b border-subtle text-tertiary">
                    <th scope="col" className="py-1.5 pr-3 font-medium">
                      {t("project_hub.settings.display_name")}
                    </th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">
                      {t("project_hub.knowledge.scan_label")}
                    </th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">
                      {t("project_hub.knowledge.format_label")}
                    </th>
                    <th scope="col" className="py-1.5 font-medium">
                      MIME
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((u) => (
                    <tr key={u.id} className="border-b border-subtle align-top">
                      <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                        {u.name ?? u.asset_id}
                      </th>
                      <td className="py-1.5 pr-3">
                        <ToneBadge
                          tone={SCAN_TONE[u.scan_status]}
                          size="xs"
                          label={t(`project_hub.knowledge.scan.${u.scan_status}`)}
                        />
                        {u.scan_detail && (
                          <p className="pt-0.5 text-caption-sm-regular text-tertiary">{u.scan_detail}</p>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-secondary">
                        {t(`project_hub.knowledge.format.${u.format_support}`)}
                      </td>
                      <td className="py-1.5 text-tertiary">{u.detected_mime || u.declared_mime || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </HubResourceBoundary>
      </HubSection>
    </HubPage>
  );
});
