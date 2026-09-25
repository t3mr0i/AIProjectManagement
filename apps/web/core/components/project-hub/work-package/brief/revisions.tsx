/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import type { TPackageRevision, TPackageRevisionCompare } from "@plane/types";
import { shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../../common/chip";
import { HubList, HubListRow } from "../../common/list";
import { HubSelect } from "../../common/select";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { useHubResource } from "../../common/use-hub-resource";
import type { THubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import { WpSection } from "../panel";
import type { TWorkPackageScope } from "../types";
import { sortRevisions, useCreateRevision } from "../use-work-package";

const renderValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value
      .map((v) => (typeof v === "object" && v && "text" in v ? String((v as { text: unknown }).text) : String(v)))
      .join("\n");
  return JSON.stringify(value, null, 2);
};

const RevisionCompare = observer(function RevisionCompare({
  scope,
  from,
  to,
}: {
  scope: TWorkPackageScope;
  from: TPackageRevision;
  to: TPackageRevision;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const compare = useHubResource<TPackageRevisionCompare>(PH_KEYS.compare(scope.issueId, from.id, to.id), () =>
    store.packageService.compareRevisions(scope.workspaceSlug, scope.projectId, scope.issueId, from.id, to.id)
  );
  return (
    <HubResourceBoundary
      resource={compare}
      loadingRows={2}
      size="sm"
      isEmpty={(d) => d.changes.length === 0}
      empty={<HubEmpty size="sm" title={t("project_hub.revisions.no_changes")} />}
    >
      {(data) => (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-caption-md-regular">
            <caption className="sr-only">
              {t("project_hub.revisions.compare_title", { from: from.number, to: to.number })}
            </caption>
            <thead>
              <tr className="border-b border-subtle text-tertiary">
                <th scope="col" className="py-1 pr-3 font-medium">
                  {t("project_hub.revisions.field")}
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  {t("project_hub.revisions.before")}
                </th>
                <th scope="col" className="py-1 font-medium">
                  {t("project_hub.revisions.after")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.changes.map((change) => (
                <tr key={change.field} className="border-b border-subtle align-top last:border-b-0">
                  <th scope="row" className="py-1 pr-3 font-medium text-primary">
                    {change.field}
                  </th>
                  <td className="py-1 pr-3 whitespace-pre-wrap text-secondary">
                    <del className="decoration-danger-primary no-underline">{renderValue(change.from)}</del>
                  </td>
                  <td className="py-1 whitespace-pre-wrap text-primary">
                    <ins className="no-underline">{renderValue(change.to)}</ins>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </HubResourceBoundary>
  );
});

type Props = {
  scope: TWorkPackageScope;
  revisions: THubResource<TPackageRevision[]>;
  workingRevisionId: string | null;
  canEdit: boolean;
};

/** Revisions as compact list rows: `#n  title …… chips  hash  created`. */
export const RevisionsPanel = observer(function RevisionsPanel({
  scope,
  revisions,
  workingRevisionId,
  canEdit,
}: Props) {
  const { t } = useTranslation();
  const { formatDateTime, formatAge } = useHubFormatters();
  const { create, isCreating } = useCreateRevision(scope);
  const [compareFrom, setCompareFrom] = useState<string | null>(null);
  const [compareTo, setCompareTo] = useState<string | null>(null);
  const [showCompare, setShowCompare] = useState(false);

  const sorted = sortRevisions(revisions.data);
  const fromRev = sorted.find((r) => r.id === (compareFrom ?? sorted[1]?.id));
  const toRev = sorted.find((r) => r.id === (compareTo ?? sorted[0]?.id));
  const options = sorted.map((r) => ({ value: r.id, label: t("project_hub.revisions.number", { number: r.number }) }));

  return (
    <WpSection
      title={t("project_hub.revisions.title")}
      actions={
        <>
          {sorted.length > 1 && (
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              aria-expanded={showCompare}
              label={t("project_hub.revisions.compare")}
              onClick={() => setShowCompare((v) => !v)}
            />
          )}
          {canEdit && (
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              loading={isCreating}
              label={isCreating ? t("project_hub.revisions.creating") : t("project_hub.revisions.create")}
              onClick={() => void create()}
            />
          )}
        </>
      }
    >
      <HubResourceBoundary
        resource={revisions}
        loadingRows={2}
        size="sm"
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty size="sm" title={t("project_hub.revisions.empty")} />}
      >
        {() => (
          <div className="flex min-w-0 flex-col gap-3">
            <HubList aria-label={t("project_hub.revisions.title")}>
              {sorted.map((revision) => (
                <HubListRow
                  key={revision.id}
                  identifier={`#${revision.number}`}
                  title={revision.title || t("project_hub.revisions.number", { number: revision.number })}
                  meta={
                    <>
                      {revision.is_approved && <HubChip tone="success" label={t("project_hub.revisions.approved")} />}
                      {revision.is_stale && <HubChip tone="warning" label={t("project_hub.revisions.stale")} />}
                      {workingRevisionId === revision.id && (
                        <HubChip tone="neutral" label={t("project_hub.lifecycle.draft")} />
                      )}
                      <code
                        className="font-mono text-caption-md-regular text-tertiary"
                        title={t("project_hub.revisions.hash", { hash: revision.content_hash })}
                      >
                        {shortHash(revision.content_hash)}
                      </code>
                    </>
                  }
                  trailing={
                    <span
                      className="text-caption-md-regular text-tertiary tabular-nums"
                      title={t("project_hub.revisions.created_at", { time: formatDateTime(revision.created_at) })}
                    >
                      {formatAge(revision.created_at)}
                    </span>
                  }
                />
              ))}
            </HubList>
            {showCompare && fromRev && toRev && (
              <div className="flex flex-col gap-2 border-t border-subtle pt-3">
                <div className="flex flex-wrap gap-3">
                  <HubSelect
                    label={t("project_hub.revisions.compare_from")}
                    value={fromRev.id}
                    options={options}
                    onChange={setCompareFrom}
                  />
                  <HubSelect
                    label={t("project_hub.revisions.compare_to")}
                    value={toRev.id}
                    options={options}
                    onChange={setCompareTo}
                  />
                </div>
                {fromRev.id !== toRev.id ? (
                  <RevisionCompare scope={scope} from={fromRev} to={toRev} />
                ) : (
                  <HubEmpty size="sm" title={t("project_hub.revisions.no_changes")} />
                )}
              </div>
            )}
          </div>
        )}
      </HubResourceBoundary>
    </WpSection>
  );
});
