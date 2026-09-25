/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TPHSearchResult } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
// local imports
import { ToneBadge } from "./tone-badge";
import { useHubFormatters } from "./use-relative-time";

const KNOWN_TYPES = new Set(["package", "issue", "decision", "page", "message", "event", "upload"]);

const resultHref = (workspaceSlug: string, result: TPHSearchResult) => {
  if ((result.type === "package" || result.type === "issue") && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/issues/${result.issue_id ?? result.id}`;
  if (result.issue_id && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/issues/${result.issue_id}`;
  if (result.type === "page" && result.project_id)
    return `/${workspaceSlug}/projects/${result.project_id}/pages/${result.id}`;
  return undefined;
};

/**
 * Typed results with project, source and update time. The count is the number of results the
 * viewer can access — hidden results are never counted (FR-P06).
 */
export const HubSearchResults = observer(function HubSearchResults({
  workspaceSlug,
  results,
}: {
  workspaceSlug: string;
  results: TPHSearchResult[];
}) {
  const { t } = useTranslation();
  const { getPartialProjectById } = useProject();
  const { formatDateTime } = useHubFormatters();
  return (
    <div className="flex flex-col gap-2">
      <p className="text-caption-sm-regular text-tertiary" aria-live="polite">
        {t("project_hub.search.results_count", { count: results.length })}
      </p>
      <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
        {results.map((result) => {
          const href = resultHref(workspaceSlug, result);
          const typeLabel = KNOWN_TYPES.has(result.type) ? t(`project_hub.search.type.${result.type}`) : result.type;
          return (
            <li key={`${result.type}-${result.id}`} className="flex flex-col gap-1 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <ToneBadge tone="neutral" size="xs" label={typeLabel} />
                {href ? (
                  <Link
                    href={href}
                    className="focus-visible:outline-accent-primary text-body-xs-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2"
                  >
                    {result.title}
                  </Link>
                ) : (
                  <span className="text-body-xs-medium text-primary">{result.title}</span>
                )}
              </div>
              {result.snippet && <p className="text-caption-sm-regular text-secondary">{result.snippet}</p>}
              <p className="text-caption-sm-regular text-tertiary">
                {result.project_id ? `${getPartialProjectById(result.project_id)?.name ?? result.project_id} · ` : ""}
                {t("project_hub.search.source", { source: result.source })} ·{" "}
                {t("project_hub.search.updated", { time: formatDateTime(result.updated_at) })}
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
});
