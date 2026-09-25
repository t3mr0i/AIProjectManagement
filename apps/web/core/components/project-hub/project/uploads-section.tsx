/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AlertCircleOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHUploadCandidate, TPHUploadRecord, TPHUploadScanStatus } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubSection } from "../common/section";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";

const SCAN_TONE: Record<TPHUploadScanStatus, TProjectHubTone> = {
  pending: "neutral",
  clean: "success",
  quarantined: "danger",
  failed: "warning",
};

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** Scan badge + detail; quarantine is announced with icon, text and an explicit warning line. */
function ScanCell({ upload }: { upload: TPHUploadRecord }) {
  const { t } = useTranslation();
  const quarantined = upload.scan_status === "quarantined";
  return (
    <div className="flex flex-col gap-0.5">
      <ToneBadge
        tone={SCAN_TONE[upload.scan_status]}
        size="xs"
        label={t(`project_hub.knowledge.scan.${upload.scan_status}`)}
      />
      {quarantined && (
        <p className="flex items-center gap-1 text-caption-sm-medium text-danger-primary">
          <Icon icon={AlertCircleOutline} />
          {t("project_hub.knowledge.quarantined_warning")}
        </p>
      )}
      {upload.scan_detail && <p className="text-caption-sm-regular text-tertiary">{upload.scan_detail}</p>}
    </div>
  );
}

/**
 * Uploads in project knowledge (FR-K): registered files with scan status and format support, plus
 * registration of an existing native attachment / FileAsset (no new upload path).
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
  const { formatDate } = useHubFormatters();
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

  return (
    <HubSection
      title={t("project_hub.knowledge.uploads")}
      as="h2"
      actions={
        canRegister && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t("project_hub.knowledge.register")}
            onClick={() => setIsOpen(true)}
          />
        )
      }
    >
      {lastResult && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-md border border-subtle px-3 py-2">
          <span className="text-body-xs-medium text-primary">
            {t("project_hub.knowledge.registered", { name: lastResult.name })}
          </span>
          <ScanCell upload={lastResult} />
          <span className="text-caption-sm-regular text-secondary">
            {t(`project_hub.knowledge.format.${lastResult.format_support}`)}
          </span>
        </div>
      )}
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
                    {t("project_hub.knowledge.mime")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((u) => (
                  <tr
                    key={u.id}
                    className={`border-b border-subtle align-top ${u.scan_status === "quarantined" ? "bg-danger-subtle" : ""}`}
                  >
                    <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                      {u.name || u.asset_id}
                      {u.updated_at && (
                        <span className="block text-caption-sm-regular text-tertiary">{formatDate(u.updated_at)}</span>
                      )}
                    </th>
                    <td className="py-1.5 pr-3">
                      <ScanCell upload={u} />
                    </td>
                    <td className="py-1.5 pr-3 text-secondary">
                      {u.scan_status === "quarantined"
                        ? t("project_hub.knowledge.format_blocked")
                        : t(`project_hub.knowledge.format.${u.format_support}`)}
                    </td>
                    <td className="py-1.5 text-tertiary">{u.detected_mime || u.declared_mime || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </HubResourceBoundary>

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
        <HubResourceBoundary
          resource={candidates}
          loadingRows={3}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.knowledge.candidates_empty")} />}
        >
          {(data) => (
            <fieldset className="flex max-h-64 flex-col gap-1 overflow-y-auto">
              <legend className="sr-only">{t("project_hub.knowledge.candidates")}</legend>
              {data.map((c) => (
                <label
                  key={c.asset_id}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-subtle px-2 py-1.5"
                >
                  <input
                    type="radio"
                    name="ph-upload-candidate"
                    className="mt-0.5"
                    checked={selected?.asset_id === c.asset_id}
                    disabled={!c.is_uploaded}
                    onChange={() => pick(c)}
                  />
                  <span className="flex min-w-0 flex-col text-body-xs-medium break-all text-primary">
                    {c.name}
                    <span className="text-caption-sm-regular text-tertiary">
                      {[c.declared_mime || "—", formatSize(c.size), formatDate(c.created_at)].join(" · ")}
                      {!c.is_uploaded && ` · ${t("project_hub.knowledge.not_uploaded")}`}
                    </span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </HubResourceBoundary>
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
    </HubSection>
  );
});
