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
import { HubSection } from "../../common/section";
import { HubSelect } from "../../common/select";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import type { THubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

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
      isEmpty={(d) => d.changes.length === 0}
      empty={<HubEmpty title={t("project_hub.revisions.no_changes")} />}
    >
      {(data) => (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-body-xs-regular">
            <caption className="sr-only">
              {t("project_hub.revisions.compare_title", { from: from.number, to: to.number })}
            </caption>
            <thead>
              <tr className="border-b border-subtle text-tertiary">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  {t("project_hub.revisions.field")}
                </th>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  {t("project_hub.revisions.before")}
                </th>
                <th scope="col" className="py-1.5 font-medium">
                  {t("project_hub.revisions.after")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.changes.map((change) => (
                <tr key={change.field} className="border-b border-subtle align-top">
                  <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                    {change.field}
                  </th>
                  <td className="py-1.5 pr-3 whitespace-pre-wrap text-secondary">
                    <del className="decoration-danger-primary no-underline">{renderValue(change.from)}</del>
                  </td>
                  <td className="py-1.5 whitespace-pre-wrap text-primary">
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

export const RevisionsPanel = observer(function RevisionsPanel({
  scope,
  revisions,
  workingRevisionId,
  canEdit,
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime } = useHubFormatters();
  const [isCreating, setIsCreating] = useState(false);
  const [compareFrom, setCompareFrom] = useState<string | null>(null);
  const [compareTo, setCompareTo] = useState<string | null>(null);
  const [showCompare, setShowCompare] = useState(false);

  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
  const sorted = [...(revisions.data ?? [])].sort((a, b) => b.number - a.number);

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const revision = await store.packageService.createRevision(scope.workspaceSlug, scope.projectId, scope.issueId);
      store.invalidateIssue(scope.issueId);
      showHubSuccessToast(t("project_hub.revisions.created", { number: revision.number }));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsCreating(false);
    }
  };

  const fromRev = sorted.find((r) => r.id === (compareFrom ?? sorted[1]?.id));
  const toRev = sorted.find((r) => r.id === (compareTo ?? sorted[0]?.id));
  const options = sorted.map((r) => ({ value: r.id, label: t("project_hub.revisions.number", { number: r.number }) }));

  return (
    <HubSection
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
              onClick={() => void handleCreate()}
            />
          )}
        </>
      }
    >
      <HubResourceBoundary
        resource={revisions}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.revisions.empty")} />}
      >
        {() => (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
              {sorted.map((revision) => (
                <li key={revision.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                  <span className="text-body-xs-medium text-primary">
                    {t("project_hub.revisions.number", { number: revision.number })}
                  </span>
                  <code className="font-mono text-caption-sm-regular text-tertiary" title={revision.content_hash}>
                    {t("project_hub.revisions.hash", { hash: shortHash(revision.content_hash) })}
                  </code>
                  <span className="text-caption-sm-regular text-tertiary">
                    {t("project_hub.revisions.created_at", { time: formatDateTime(revision.created_at) })}
                  </span>
                  {revision.is_approved && (
                    <ToneBadge tone="success" size="xs" label={t("project_hub.revisions.approved")} />
                  )}
                  {revision.is_stale && <ToneBadge tone="warning" size="xs" label={t("project_hub.revisions.stale")} />}
                  {workingRevisionId === revision.id && (
                    <ToneBadge tone="neutral" size="xs" label={t("project_hub.lifecycle.draft")} />
                  )}
                </li>
              ))}
            </ul>
            {showCompare && fromRev && toRev && (
              <div className="flex flex-col gap-2 rounded-md border border-subtle p-3">
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
                  <HubEmpty title={t("project_hub.revisions.no_changes")} />
                )}
              </div>
            )}
          </div>
        )}
      </HubResourceBoundary>
    </HubSection>
  );
});
