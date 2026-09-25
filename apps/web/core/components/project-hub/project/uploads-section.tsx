/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { AlertCircleOutline, AttachOutline, FileOutline, TickCircleOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHUploadCandidate, TPHUploadRecord, TPHUploadScanStatus } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubList, HubListGroup, HubListRow } from "../common/list";
import { HubEmptyState, HubErrorState, HubFreshnessBanner, HubLoading, HubNotice } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const SCAN_TONE: Record<TPHUploadScanStatus, TProjectHubTone> = {
  pending: "neutral",
  clean: "success",
  quarantined: "danger",
  failed: "warning",
};

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Scan chip + format chip + mime for one upload; quarantine carries the explicit warning as tooltip and text. */
function UploadMeta({ upload }: { upload: TPHUploadRecord }) {
  const { t } = useTranslation();
  const quarantined = upload.scan_status === "quarantined";
  const scanTitle = [quarantined ? t("project_hub.knowledge.quarantined_warning") : null, upload.scan_detail]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <HubChip
        tone={SCAN_TONE[upload.scan_status]}
        label={t(`project_hub.knowledge.scan.${upload.scan_status}`)}
        title={scanTitle || undefined}
      />
      <HubChip
        variant="soft"
        icon={quarantined ? (AlertCircleOutline as TGlyph) : undefined}
        tone="neutral"
        label={
          quarantined
            ? t("project_hub.knowledge.format_blocked")
            : t(`project_hub.knowledge.format.${upload.format_support}`)
        }
      />
      <span className="hidden text-caption-md-regular text-tertiary lg:inline">
        {upload.detected_mime || upload.declared_mime || "—"}
      </span>
    </>
  );
}

/**
 * Uploads in project knowledge (FR-K): registered files with scan status and format support as
 * list rows, plus registration of an existing native attachment / FileAsset (no new upload path).
 */
export const ProjectUploadsSection = observer(function ProjectUploadsSection({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const { formatDate, formatAge } = useHubFormatters();
  const canRegister = has("package.edit");
  const uploads = useHubResource<TPHUploadRecord[]>(PH_KEYS.uploads(workspaceSlug, projectId), () =>
    store.knowledgeService.listUploads(workspaceSlug, projectId)
  );
  const [isOpen, setIsOpen] = useState(false);
  const candidates = useHubResource<TPHUploadCandidate[]>(
    isOpen ? `${PH_KEYS.uploads(workspaceSlug, projectId)}:candidates` : null,
    () => store.knowledgeService.listUploadCandidates(workspaceSlug, projectId)
  );
  const [selected, setSelected] = useState<TPHUploadCandidate | null>(null);
  const [filename, setFilename] = useState("");
  const [mime, setMime] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<TPHUploadRecord | null>(null);

  const close = () => {
    setIsOpen(false);
    setSelected(null);
  };

  const pick = (c: TPHUploadCandidate) => {
    setSelected(c);
    setFilename(c.name);
    setMime(c.declared_mime);
  };

  const handleRegister = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const record = await store.knowledgeService.registerUpload(workspaceSlug, projectId, selected.asset_id, {
        filename: filename.trim() || undefined,
        declared_mime: mime.trim() || undefined,
        ...(selected.issue_id ? { issue_id: selected.issue_id } : {}),
      });
      setLastResult(record);
      close();
      store.invalidate(PH_KEYS.uploads(workspaceSlug, projectId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  const data = uploads.data;
  const quarantinedCount = data?.filter((u) => u.scan_status === "quarantined").length ?? 0;

  return (
    <>
      <HubListGroup
        icon={AttachOutline as TGlyph}
        title={t("project_hub.knowledge.uploads")}
        count={data?.length ?? 0}
        showEmpty
        emptyLabel={t("project_hub.knowledge.uploads_empty")}
        onAdd={canRegister ? () => setIsOpen(true) : undefined}
        addLabel={t("project_hub.knowledge.register")}
      >
        <div className="flex min-w-0 flex-col">
          {(lastResult || quarantinedCount > 0 || (data !== undefined && uploads.error)) && (
            <div className="flex flex-col gap-2 px-3 py-2 empty:hidden">
              <HubFreshnessBanner resource={uploads} />
              {lastResult && (
                <HubNotice
                  icon={TickCircleOutline as TGlyph}
                  title={t("project_hub.knowledge.registered", { name: lastResult.name })}
                  description={`${t(`project_hub.knowledge.scan.${lastResult.scan_status}`)} · ${t(`project_hub.knowledge.format.${lastResult.format_support}`)}`}
                  onDismiss={() => setLastResult(null)}
                />
              )}
              {quarantinedCount > 0 && (
                <HubNotice
                  role="alert"
                  tone="warning"
                  icon={AlertCircleOutline as TGlyph}
                  title={t("project_hub.knowledge.quarantined_count", { count: quarantinedCount })}
                  description={t("project_hub.knowledge.quarantined_warning")}
                />
              )}
            </div>
          )}
          {data === undefined ? (
            uploads.error ? (
              <HubErrorState error={uploads.error} size="sm" onRetry={() => void uploads.refresh()} />
            ) : (
              <HubLoading rows={2} />
            )
          ) : (
            <HubList aria-label={t("project_hub.knowledge.uploads")}>
              {data.map((u) => (
                <HubListRow
                  key={u.id}
                  navId={u.id}
                  icon={FileOutline as TGlyph}
                  title={u.name || u.asset_id}
                  aria-label={
                    u.scan_status === "quarantined"
                      ? `${u.name || u.asset_id} — ${t("project_hub.knowledge.quarantined_warning")}`
                      : undefined
                  }
                  className={u.scan_status === "quarantined" ? "bg-danger-subtle/40" : undefined}
                  meta={<UploadMeta upload={u} />}
                  trailing={
                    u.updated_at ? (
                      <span
                        className="text-caption-md-regular text-tertiary tabular-nums"
                        title={formatDate(u.updated_at)}
                      >
                        {formatAge(u.updated_at)}
                      </span>
                    ) : undefined
                  }
                />
              ))}
            </HubList>
          )}
        </div>
      </HubListGroup>

      <HubDialog
        isOpen={isOpen}
        onClose={close}
        isBusy={busy}
        title={t("project_hub.knowledge.register")}
        onSubmit={() => void handleRegister()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={close}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              disabled={!selected}
              loading={busy}
              label={t("project_hub.knowledge.register_submit")}
            />
          </>
        }
      >
        <p className="text-body-xs-regular text-tertiary">{t("project_hub.knowledge.register_hint")}</p>
        <div className="flex min-w-0 flex-col">
          {candidates.data === undefined ? (
            candidates.error ? (
              <HubErrorState error={candidates.error} size="sm" onRetry={() => void candidates.refresh()} />
            ) : (
              <HubLoading rows={3} />
            )
          ) : candidates.data.length === 0 ? (
            <HubEmptyState size="sm" title={t("project_hub.knowledge.candidates_empty")} />
          ) : (
            <fieldset className="flex max-h-64 flex-col overflow-y-auto rounded-md border border-subtle">
              <legend className="sr-only">{t("project_hub.knowledge.candidates")}</legend>
              {candidates.data.map((c) => (
                <label
                  key={c.asset_id}
                  className="flex h-9 cursor-pointer items-center gap-2 border-b border-subtle px-3 text-13 last:border-b-0 hover:bg-layer-transparent-hover has-[input:disabled]:cursor-not-allowed has-[input:disabled]:opacity-60"
                >
                  <input
                    type="radio"
                    name="ph-upload-candidate"
                    checked={selected?.asset_id === c.asset_id}
                    disabled={!c.is_uploaded}
                    onChange={() => pick(c)}
                  />
                  <span className="min-w-0 flex-1 truncate font-medium text-primary">{c.name}</span>
                  <span className="shrink-0 truncate text-caption-md-regular text-tertiary">
                    {[c.declared_mime || "—", formatSize(c.size), formatDate(c.created_at)].join(" · ")}
                    {!c.is_uploaded && ` · ${t("project_hub.knowledge.not_uploaded")}`}
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
        {selected && (
          <>
            <HubTextField label={t("project_hub.knowledge.filename")} value={filename} onChange={setFilename} />
            <HubTextField
              label={t("project_hub.knowledge.declared_mime")}
              value={mime}
              onChange={setMime}
              hint={t("project_hub.knowledge.declared_mime_hint")}
            />
          </>
        )}
      </HubDialog>
    </>
  );
});
