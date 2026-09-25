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
import type { TChangeRecord, TChangeRecordKind } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField, HubTextField } from "../../common/field";
import { WpSection } from "../panel";
import { HubSelect } from "../../common/select";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import type { TWorkPackageScope } from "../types";

/** Small changes recorded on the package instead of new tickets (PRD §2 "Kleine Änderungen"). */
export const ChangeRecordsPanel = observer(function ChangeRecordsPanel({
  scope,
  canEdit,
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { workspaceSlug, projectId, issueId } = scope;
  const records = useHubResource<TChangeRecord[]>(PH_KEYS.changeRecords(issueId), () =>
    store.packageService.listChangeRecords(workspaceSlug, projectId, issueId)
  );
  const [isOpen, setIsOpen] = useState(false);
  const [kind, setKind] = useState<TChangeRecordKind>("change");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!title.trim()) return;
    setBusy("create");
    try {
      await store.packageService.createChangeRecord(workspaceSlug, projectId, issueId, {
        kind,
        title: title.trim(),
        description,
      });
      setIsOpen(false);
      setTitle("");
      setDescription("");
      store.invalidate(PH_KEYS.changeRecords(issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  const toggleStatus = async (record: TChangeRecord) => {
    setBusy(record.id);
    try {
      await store.packageService.updateChangeRecord(workspaceSlug, projectId, issueId, record.id, {
        status: record.status === "done" ? "open" : "done",
      });
      store.invalidate(PH_KEYS.changeRecords(issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <WpSection
      title={t("project_hub.changes.records")}
      actions={
        canEdit && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t("project_hub.changes.add_record")}
            onClick={() => setIsOpen(true)}
          />
        )
      }
    >
      <HubResourceBoundary
        resource={records}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty size="sm" title={t("project_hub.changes.records_empty")} />}
      >
        {(data) => (
          <ul className="flex flex-col divide-y divide-subtle">
            {data.map((record) => (
              <li key={record.id} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-body-xs-medium text-primary">{record.title}</span>
                    <ToneBadge tone="neutral" size="xs" label={t(`project_hub.changes.kinds.${record.kind}`)} />
                    <ToneBadge
                      tone={record.status === "done" ? "success" : record.status === "dropped" ? "neutral" : "info"}
                      size="xs"
                      label={t(`project_hub.changes.status.${record.status}`)}
                    />
                  </div>
                  {record.description && (
                    <p className="text-caption-sm-regular whitespace-pre-wrap text-secondary">{record.description}</p>
                  )}
                </div>
                {canEdit && record.status !== "dropped" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    stretch="auto"
                    loading={busy === record.id}
                    label={
                      record.status === "done" ? t("project_hub.changes.reopen") : t("project_hub.changes.mark_done")
                    }
                    onClick={() => void toggleStatus(record)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </HubResourceBoundary>
      <HubDialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        isBusy={busy === "create"}
        title={t("project_hub.changes.add_record")}
        onSubmit={() => void handleCreate()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setIsOpen(false)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              disabled={!title.trim()}
              loading={busy === "create"}
              label={t("project_hub.common.create")}
            />
          </>
        }
      >
        <HubSelect
          label={t("project_hub.changes.record_kind")}
          value={kind}
          onChange={(v) => setKind(v as TChangeRecordKind)}
          options={(["change", "technical_task", "openspec_change"] as TChangeRecordKind[]).map((k) => ({
            value: k,
            label: t(`project_hub.changes.kinds.${k}`),
          }))}
        />
        <HubTextField label={t("project_hub.changes.record_title")} value={title} required onChange={setTitle} />
        <HubTextAreaField
          label={t("project_hub.changes.record_description")}
          value={description}
          onChange={setDescription}
        />
      </HubDialog>
    </WpSection>
  );
});
