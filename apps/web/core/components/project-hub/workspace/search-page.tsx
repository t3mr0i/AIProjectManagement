/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { useTranslation } from "@plane/i18n";
import type { TPHSearchResult } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextField } from "../common/field";
import { HubPage } from "../common/page";
import { HubSearchResults } from "../common/search-results";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";

const TYPES = ["package", "decision", "page", "message", "event", "upload"] as const;

/** S11 Search: ACL-filtered typed results; counts only what the viewer can access. */
export const WorkspaceSearchPage = observer(function WorkspaceSearchPage({ workspaceSlug }: { workspaceSlug: string }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [query, setQuery] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState<{ q: string; types: string[] } | null>(null);
  const results = useHubResource<TPHSearchResult[]>(
    submitted ? PH_KEYS.search(workspaceSlug, submitted.q, submitted.types.join(",")) : null,
    async () => await store.knowledgeService.search(workspaceSlug, submitted?.q ?? "", submitted?.types)
  );

  return (
    <HubPage title={t("project_hub.search.title")} description={t("project_hub.search.hint")}>
      <form
        role="search"
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) setSubmitted({ q: query.trim(), types });
        }}
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <HubTextField
              label={t("project_hub.common.search")}
              placeholder={t("project_hub.search.placeholder")}
              value={query}
              onChange={setQuery}
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            size="md"
            stretch="auto"
            disabled={!query.trim()}
            label={t("project_hub.common.search")}
          />
        </div>
        <fieldset className="flex flex-wrap gap-3">
          <legend className="text-caption-md-medium text-tertiary">{t("project_hub.search.types")}</legend>
          {TYPES.map((type) => (
            <label key={type} className="flex items-center gap-1.5 text-body-xs-regular text-secondary">
              <Checkbox
                checked={types.includes(type)}
                onCheckedChange={(c) => setTypes((prev) => (c ? [...prev, type] : prev.filter((p) => p !== type)))}
              />
              {t(`project_hub.search.type.${type}`)}
            </label>
          ))}
        </fieldset>
      </form>
      {submitted && (
        <HubResourceBoundary
          resource={results}
          loadingRows={4}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.search.empty")} />}
        >
          {(data) => <HubSearchResults workspaceSlug={workspaceSlug} results={data} />}
        </HubResourceBoundary>
      )}
    </HubPage>
  );
});
