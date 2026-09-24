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
import type { TProjectHubTone } from "@plane/utils";
import type { TRepositoryBinding, TSpecState, TSpecSyncStateValue, TSyncConflict } from "@plane/types";
import { shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField, HubTextField } from "../../common/field";
import { HubCard, HubSection } from "../../common/section";
import { HubSelect } from "../../common/select";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

const SPEC_TONE: Record<TSpecSyncStateValue, TProjectHubTone> = {
  clean: "success",
  ahead: "info",
  behind: "warning",
  conflict: "danger",
};

const show = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "string" ? v : JSON.stringify(v));

/** OpenSpec roundtrip state (FR-W08): export/import and the 3-way conflict view. */
export const SpecSyncPanel = observer(function SpecSyncPanel({
  scope,
  canEdit,
}: {
  scope: TWorkPackageScope;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime } = useHubFormatters();
  const { workspaceSlug, projectId, issueId } = scope;
  const spec = useHubResource<TSpecState>(PH_KEYS.spec(issueId), () =>
    store.integrationService.getSpec(workspaceSlug, projectId, issueId)
  );
  const conflicts = useHubResource<TSyncConflict[]>(PH_KEYS.syncConflicts(issueId), () =>
    store.integrationService.listSyncConflicts(workspaceSlug, projectId, issueId)
  );
  const [dialog, setDialog] = useState<"export" | "import" | null>(null);
  const repositories = useHubResource<TRepositoryBinding[]>(
    dialog ? PH_KEYS.repositories(workspaceSlug, projectId) : null,
    () => store.integrationService.listRepositories(workspaceSlug, projectId)
  );
  const [repoId, setRepoId] = useState<string | null>(null);
  const [baseCommit, setBaseCommit] = useState("");
  const [content, setContent] = useState("");
  const [commit, setCommit] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const submit = async () => {
    setBusy("dialog");
    try {
      if (dialog === "export") {
        if (!repoId) return;
        await store.integrationService.exportSpec(workspaceSlug, projectId, issueId, {
          repository_binding_id: repoId,
          expected_base_commit: baseCommit,
        });
        showHubSuccessToast(t("project_hub.changes.exported"));
      } else if (dialog === "import") {
        await store.integrationService.importSpec(workspaceSlug, projectId, issueId, { content, commit });
        showHubSuccessToast(t("project_hub.changes.imported"));
      }
      setDialog(null);
      store.invalidateIssue(issueId);
    } catch (error) {
      // Moved head / 3-way conflicts come back as 409 and are shown in the list after refresh.
      showHubErrorToast(t, error);
      store.invalidate(PH_KEYS.spec(issueId));
    } finally {
      setBusy(null);
    }
  };

  const resolve = async (conflict: TSyncConflict, resolution: "platform" | "external") => {
    setBusy(conflict.id);
    try {
      await store.integrationService.resolveSyncConflict(workspaceSlug, projectId, issueId, conflict.id, resolution);
      store.invalidate(PH_KEYS.syncConflicts(issueId));
      store.invalidate(PH_KEYS.status(issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <HubSection
        title={t("project_hub.changes.spec")}
        actions={
          canEdit && (
            <>
              <Button
                variant="secondary"
                size="sm"
                stretch="auto"
                label={t("project_hub.changes.export")}
                onClick={() => setDialog("export")}
              />
              <Button
                variant="ghost"
                size="sm"
                stretch="auto"
                label={t("project_hub.changes.import")}
                onClick={() => setDialog("import")}
              />
            </>
          )
        }
      >
        <HubResourceBoundary
          resource={spec}
          loadingRows={1}
          isEmpty={(d) => (d.items ?? []).length === 0}
          empty={<HubEmpty title={t("project_hub.changes.spec_empty")} />}
        >
          {(data) => (
            <ul className="flex flex-col gap-2">
              {data.items.map((item) => (
                <li key={`${item.repository_binding_id}-${item.spec_path}`}>
                  <HubCard className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge
                        tone={SPEC_TONE[item.state]}
                        size="xs"
                        label={t(`project_hub.changes.spec_state.${item.state}`)}
                      />
                      <code className="font-mono text-caption-sm-regular text-secondary">{item.spec_path}</code>
                      {item.repository_name && (
                        <span className="text-caption-sm-regular text-tertiary">{item.repository_name}</span>
                      )}
                    </div>
                    {item.published_commit && (
                      <p className="text-caption-sm-regular text-tertiary">
                        {t("project_hub.changes.published", {
                          number: item.published_revision_number ?? "?",
                          commit: shortHash(item.published_commit),
                        })}
                      </p>
                    )}
                    {item.state === "conflict" && item.conflict && (
                      <div
                        className="flex flex-col gap-1"
                        role="group"
                        aria-label={t("project_hub.changes.conflict_title")}
                      >
                        <p className="text-caption-md-medium text-primary">{t("project_hub.changes.conflict_title")}</p>
                        <div className="grid gap-2 md:grid-cols-3">
                          {(
                            [
                              ["conflict_base", item.conflict.base],
                              ["conflict_platform", item.conflict.platform],
                              ["conflict_git", item.conflict.git],
                            ] as const
                          ).map(([label, value]) => (
                            <div key={label} className="flex flex-col gap-1">
                              <span className="text-caption-sm-medium text-tertiary">
                                {t(`project_hub.changes.${label}`)}
                              </span>
                              <pre className="font-mono max-h-48 overflow-auto rounded-md border border-subtle bg-layer-2 p-2 text-caption-sm-regular whitespace-pre-wrap">
                                {value ?? "—"}
                              </pre>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </HubCard>
                </li>
              ))}
            </ul>
          )}
        </HubResourceBoundary>
      </HubSection>

      {conflicts.data && conflicts.data.filter((c) => c.status === "open").length > 0 && (
        <HubSection title={t("project_hub.changes.sync_conflicts")}>
          <ul className="flex flex-col gap-2">
            {conflicts.data
              .filter((c) => c.status === "open")
              .map((conflict) => (
                <li key={conflict.id}>
                  <HubCard className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <ToneBadge tone="danger" size="xs" label={t("project_hub.flag.sync_conflict")} />
                      <span className="text-body-xs-medium text-primary">{conflict.field}</span>
                    </div>
                    <div className="grid gap-2 text-caption-sm-regular sm:grid-cols-2">
                      <div>
                        <p className="text-tertiary">
                          {t("project_hub.changes.platform_value")} ·{" "}
                          {t("project_hub.changes.changed_at", { time: formatDateTime(conflict.platform_changed_at) })}
                        </p>
                        <p className="break-words text-primary">{show(conflict.platform_value)}</p>
                      </div>
                      <div>
                        <p className="text-tertiary">
                          {t("project_hub.changes.external_value")} ·{" "}
                          {t("project_hub.changes.changed_at", { time: formatDateTime(conflict.external_changed_at) })}
                        </p>
                        <p className="break-words text-primary">{show(conflict.external_value)}</p>
                      </div>
                    </div>
                    {canEdit && (
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          stretch="auto"
                          loading={busy === conflict.id}
                          label={t("project_hub.changes.keep_platform")}
                          onClick={() => void resolve(conflict, "platform")}
                        />
                        <Button
                          variant="secondary"
                          size="sm"
                          stretch="auto"
                          disabled={busy === conflict.id}
                          label={t("project_hub.changes.keep_external")}
                          onClick={() => void resolve(conflict, "external")}
                        />
                      </div>
                    )}
                  </HubCard>
                </li>
              ))}
          </ul>
        </HubSection>
      )}

      <HubDialog
        isOpen={!!dialog}
        onClose={() => setDialog(null)}
        isBusy={busy === "dialog"}
        title={dialog === "import" ? t("project_hub.changes.import") : t("project_hub.changes.export")}
        onSubmit={() => void submit()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setDialog(null)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              loading={busy === "dialog"}
              disabled={dialog === "export" ? !repoId : !content.trim() || !commit.trim()}
              label={dialog === "import" ? t("project_hub.changes.import") : t("project_hub.changes.export")}
            />
          </>
        }
      >
        {dialog === "export" ? (
          <>
            <HubSelect
              label={t("project_hub.changes.repository")}
              value={repoId}
              onChange={(v) => {
                setRepoId(v);
                const repo = repositories.data?.find((r) => r.id === v);
                if (repo?.observed_commit) setBaseCommit(repo.observed_commit);
              }}
              options={(repositories.data ?? []).map((r) => ({ value: r.id, label: r.path_with_namespace }))}
            />
            <HubTextField label={t("project_hub.changes.expected_base")} value={baseCommit} onChange={setBaseCommit} />
          </>
        ) : (
          <>
            <HubTextAreaField label={t("project_hub.changes.import_content")} value={content} onChange={setContent} />
            <HubTextField label={t("project_hub.changes.import_commit")} value={commit} onChange={setCommit} />
          </>
        )}
      </HubDialog>
    </>
  );
});
