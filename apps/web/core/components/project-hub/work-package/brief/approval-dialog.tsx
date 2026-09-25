/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { useTranslation } from "@plane/i18n";
import type { TExecutionRepositoryScope, TPackageRevision, TRepositoryBinding } from "@plane/types";
import { parseCheckLines } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField, HubTextField } from "../../common/field";
import { HubMeta } from "../../common/section";
import { showHubErrorToast } from "../../common/toast";
import { useHubResource } from "../../common/use-hub-resource";
import type { TWorkPackageScope } from "../types";

const ALLOWED_ACTIONS = ["commit", "push", "open_merge_request", "run_checks"] as const;

type TScopeDraft = TExecutionRepositoryScope & { selected: boolean; paths_text: string };

type Props = {
  scope: Omit<TWorkPackageScope, "readOnly">;
  /** The revision to approve (always the latest one). */
  revision: TPackageRevision;
  isOpen: boolean;
  onClose: () => void;
};

/**
 * Execution approval dialog (J04): exactly this revision and scope. Shared by the brief tab and
 * the sidebar card. The UI never shows "approved" before the server confirmed it.
 */
export const ApprovalDialog = observer(function ApprovalDialog({ scope, revision, isOpen, onClose }: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<TScopeDraft[]>([]);
  const [actions, setActions] = useState<string[]>([...ALLOWED_ACTIONS]);
  const [expiresIn, setExpiresIn] = useState("72");
  const [checksText, setChecksText] = useState("");
  const parsedChecks = parseCheckLines(checksText);

  const repositories = useHubResource<TRepositoryBinding[]>(
    isOpen ? PH_KEYS.repositories(scope.workspaceSlug, scope.projectId) : null,
    () => store.integrationService.listRepositories(scope.workspaceSlug, scope.projectId)
  );

  // Pre-fill the repository scope from the bound repositories once they are loaded.
  const repositoryData = repositories.data;
  useEffect(() => {
    if (!isOpen) {
      setScopeDraft([]);
      return;
    }
    if (!repositoryData) return;
    setScopeDraft(
      repositoryData.map((repo) => ({
        binding_id: repo.id,
        base_commit: repo.observed_commit ?? "",
        target_branch: repo.default_branch,
        allowed_paths: [],
        selected: true,
        paths_text: "",
      }))
    );
  }, [isOpen, repositoryData]);

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await store.packageService.createExecutionApproval(scope.workspaceSlug, scope.projectId, scope.issueId, {
        revision_id: revision.id,
        repository_scope: scopeDraft
          .filter((s) => s.selected)
          .map((s) => ({
            binding_id: s.binding_id,
            base_commit: s.base_commit,
            target_branch: s.target_branch,
            allowed_paths: s.paths_text
              .split(/[\n,]/)
              .map((p) => p.trim())
              .filter(Boolean),
          })),
        allowed_actions: actions,
        limits: {},
        ...(parsedChecks && parsedChecks.length > 0 ? { checks: parsedChecks } : {}),
        expires_in_hours: Number(expiresIn) > 0 ? Number(expiresIn) : undefined,
      });
      onClose();
      store.invalidateIssue(scope.issueId);
      store.invalidate(PH_KEYS.rows(scope.workspaceSlug, scope.projectId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <HubDialog
      isOpen={isOpen}
      onClose={onClose}
      isBusy={isSubmitting}
      title={t("project_hub.approval.dialog_title", { number: revision.number })}
      onSubmit={() => void handleApprove()}
      actions={
        <>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            disabled={isSubmitting}
            label={t("project_hub.common.cancel")}
            onClick={onClose}
          />
          <Button
            type="submit"
            variant="primary"
            size="md"
            stretch="auto"
            loading={isSubmitting}
            disabled={parsedChecks === null}
            label={
              isSubmitting
                ? t("project_hub.approval.approving")
                : t("project_hub.approval.confirm", { number: revision.number })
            }
          />
        </>
      }
    >
      <p className="text-body-xs-regular text-secondary">{t("project_hub.approval.dialog_description")}</p>
      <HubMeta
        items={[
          { label: t("project_hub.approval.revision"), value: `#${revision.number} · ${revision.title}` },
          {
            label: t("project_hub.approval.hash"),
            value: <code className="font-mono break-all">{revision.content_hash}</code>,
          },
        ]}
      />
      <fieldset className="flex flex-col gap-2">
        <legend className="text-caption-md-medium text-tertiary">{t("project_hub.approval.scope")}</legend>
        {repositories.isLoading ? (
          <p className="text-caption-sm-regular text-tertiary">{t("project_hub.common.loading")}</p>
        ) : scopeDraft.length === 0 ? (
          <p className="text-caption-sm-regular text-tertiary">{t("project_hub.approval.no_repositories")}</p>
        ) : (
          scopeDraft.map((row, index) => {
            const repo = repositories.data?.find((r) => r.id === row.binding_id);
            const updateRow = (patch: Partial<TScopeDraft>) =>
              setScopeDraft((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
            return (
              <div key={row.binding_id} className="flex flex-col gap-2 rounded-md border border-subtle p-2">
                <label className="flex items-center gap-2 text-body-xs-medium text-primary">
                  <Checkbox checked={row.selected} onCheckedChange={(c) => updateRow({ selected: !!c })} />
                  {repo?.path_with_namespace ?? row.binding_id}
                </label>
                {row.selected && (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <HubTextField
                      label={t("project_hub.approval.branch")}
                      value={row.target_branch}
                      onChange={(v) => updateRow({ target_branch: v })}
                    />
                    <HubTextField
                      label={t("project_hub.approval.base_commit")}
                      value={row.base_commit}
                      onChange={(v) => updateRow({ base_commit: v })}
                    />
                    <div className="sm:col-span-2">
                      <HubTextAreaField
                        label={t("project_hub.approval.paths")}
                        value={row.paths_text}
                        onChange={(v) => updateRow({ paths_text: v })}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </fieldset>
      <fieldset className="flex flex-col gap-1">
        <legend className="text-caption-md-medium text-tertiary">{t("project_hub.approval.allowed_actions")}</legend>
        <div className="flex flex-wrap gap-3">
          {ALLOWED_ACTIONS.map((action) => (
            <label key={action} className="flex items-center gap-1.5 text-body-xs-regular text-secondary">
              <Checkbox
                checked={actions.includes(action)}
                onCheckedChange={(c) =>
                  setActions((prev) => (c ? [...prev, action] : prev.filter((a) => a !== action)))
                }
              />
              <code className="font-mono">{action}</code>
            </label>
          ))}
        </div>
      </fieldset>
      <HubTextAreaField
        label={t("project_hub.approval.checks")}
        placeholder="unit: pnpm test"
        hint={parsedChecks === null ? t("project_hub.approval.checks_invalid") : t("project_hub.approval.checks_hint")}
        value={checksText}
        onChange={setChecksText}
      />
      <div className="max-w-40">
        <HubTextField
          type="number"
          label={t("project_hub.approval.expires_in")}
          value={expiresIn}
          onChange={setExpiresIn}
        />
      </div>
    </HubDialog>
  );
});

type TApproveGate = {
  isHuman: boolean;
  canApprove: boolean;
  latest: TPackageRevision | undefined;
  ready: boolean | undefined;
};

/** Why approving is not possible right now — shown as text, never only as a tooltip. `null` = allowed. */
export const useApprovalDisabledReason = ({ isHuman, canApprove, latest, ready }: TApproveGate): string | null => {
  const { t } = useTranslation();
  if (!isHuman) return t("project_hub.approval.disabled_agent");
  if (!canApprove) return t("project_hub.approval.disabled_no_capability");
  if (!latest) return t("project_hub.approval.disabled_no_revision");
  if (latest.is_stale) return t("project_hub.approval.disabled_stale");
  if (latest.is_approved) return t("project_hub.approval.disabled_already");
  if (!ready) return t("project_hub.approval.disabled_not_ready");
  return null;
};
