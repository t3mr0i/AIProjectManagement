/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { useTranslation } from "@plane/i18n";
import type {
  TExecutionApproval,
  TExecutionRepositoryScope,
  TPackageReadiness,
  TPackageRevision,
  TRepositoryBinding,
} from "@plane/types";
import { getApprovalValidity, parseCheckLines, shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField, HubTextField } from "../../common/field";
import { useProjectHubCapabilities } from "../../common/gate";
import { useMemberDisplayName } from "../../common/member-name";
import { HubCard, HubMeta, HubSection } from "../../common/section";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import type { THubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

const ALLOWED_ACTIONS = ["commit", "push", "open_merge_request", "run_checks"] as const;

const sortByApprovedAt = (list: TExecutionApproval[]) =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted typing)
  [...list].sort((a, b) => Date.parse(b.approved_at) - Date.parse(a.approved_at));

type TScopeDraft = TExecutionRepositoryScope & { selected: boolean; paths_text: string };

type Props = {
  scope: TWorkPackageScope;
  approvals: THubResource<TExecutionApproval[]>;
  revisions: TPackageRevision[] | undefined;
  readiness: TPackageReadiness | undefined;
};

/** Execution approval (J04). The UI never shows "approved" before the server confirmed it. */
export const ApprovalPanel = observer(function ApprovalPanel({ scope, approvals, revisions, readiness }: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime } = useHubFormatters();
  const { has, isHuman } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const displayName = useMemberDisplayName();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<TExecutionApproval | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [scopeDraft, setScopeDraft] = useState<TScopeDraft[]>([]);
  const [actions, setActions] = useState<string[]>(["commit", "push", "open_merge_request", "run_checks"]);
  const [expiresIn, setExpiresIn] = useState("72");
  const [checksText, setChecksText] = useState("");
  const parsedChecks = parseCheckLines(checksText);

  const repositories = useHubResource<TRepositoryBinding[]>(
    isDialogOpen ? PH_KEYS.repositories(scope.workspaceSlug, scope.projectId) : null,
    () => store.integrationService.listRepositories(scope.workspaceSlug, scope.projectId)
  );

  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022
  const latest = useMemo(() => [...(revisions ?? [])].sort((a, b) => b.number - a.number)[0], [revisions]);

  // Disabled reasons are shown as text, not only as a tooltip.
  const disabledReason = (() => {
    if (!isHuman) return t("project_hub.approval.disabled_agent");
    if (!has("package.approve_execution")) return t("project_hub.approval.disabled_no_capability");
    if (!latest) return t("project_hub.approval.disabled_no_revision");
    if (latest.is_stale) return t("project_hub.approval.disabled_stale");
    if (latest.is_approved) return t("project_hub.approval.disabled_already");
    if (!readiness?.ready) return t("project_hub.approval.disabled_not_ready");
    return null;
  })();

  const openDialog = () => {
    setScopeDraft([]);
    setIsDialogOpen(true);
  };

  // Pre-fill the repository scope from the bound repositories once they are loaded.
  const repositoryData = repositories.data;
  useEffect(() => {
    if (!isDialogOpen || !repositoryData) return;
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
  }, [isDialogOpen, repositoryData]);

  const handleApprove = async () => {
    if (!latest) return;
    setIsSubmitting(true);
    try {
      await store.packageService.createExecutionApproval(scope.workspaceSlug, scope.projectId, scope.issueId, {
        revision_id: latest.id,
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
      setIsDialogOpen(false);
      store.invalidateIssue(scope.issueId);
      store.invalidate(PH_KEYS.rows(scope.workspaceSlug, scope.projectId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget || !revokeReason.trim()) return;
    setIsSubmitting(true);
    try {
      await store.packageService.revokeExecutionApproval(
        scope.workspaceSlug,
        scope.projectId,
        scope.issueId,
        revokeTarget.id,
        revokeReason.trim()
      );
      setRevokeTarget(null);
      setRevokeReason("");
      store.invalidateIssue(scope.issueId);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderApproval = (approval: TExecutionApproval) => {
    const validity = getApprovalValidity(approval);
    const isRevoked = validity.kind === "revoked";
    return (
      <HubCard key={approval.id} className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-body-xs-medium text-primary">
            {t("project_hub.revisions.number", {
              number: revisions?.find((r) => r.id === approval.revision_id)?.number ?? "?",
            })}
          </span>
          {validity.kind === "revoked" ? (
            <ToneBadge
              tone="danger"
              size="xs"
              label={t("project_hub.approval.revoked", {
                time: formatDateTime(approval.revoked_at),
                reason: validity.reason ?? "",
              })}
            />
          ) : validity.kind === "valid" ? (
            <ToneBadge tone="success" size="xs" label={t("project_hub.approval.valid")} />
          ) : (
            <ToneBadge
              tone="warning"
              size="xs"
              label={t("project_hub.approval.invalid", { reason: validity.reason ?? "" })}
            />
          )}
        </div>
        <p className="text-caption-sm-regular text-secondary">
          {t("project_hub.approval.approved_by", {
            name: displayName(approval.approved_by),
            time: formatDateTime(approval.approved_at),
          })}{" "}
          · {t("project_hub.approval.expires", { time: formatDateTime(approval.expires_at) })}
        </p>
        <HubMeta
          items={[
            {
              label: t("project_hub.approval.hash"),
              value: <code className="font-mono">{approval.revision_hash}</code>,
            },
            {
              label: t("project_hub.approval.allowed_actions"),
              value: approval.allowed_actions.join(", ") || "—",
            },
            {
              label: t("project_hub.approval.checks"),
              value:
                (approval.checks ?? []).length === 0 ? (
                  "—"
                ) : (
                  <ul className="flex flex-col gap-0.5">
                    {(approval.checks ?? []).map((c) => (
                      <li key={c.name}>
                        <code className="font-mono">
                          {c.name}: {c.command.join(" ")}
                        </code>
                        {c.trusted ? ` (${t("project_hub.approval.trusted")})` : ""}
                      </li>
                    ))}
                  </ul>
                ),
            },
            {
              label: t("project_hub.approval.scope"),
              value:
                approval.repository_scope.length === 0 ? (
                  t("project_hub.approval.no_repositories")
                ) : (
                  <ul className="flex flex-col gap-0.5">
                    {approval.repository_scope.map((s) => (
                      <li key={s.binding_id}>
                        {s.target_branch} @ <code className="font-mono">{shortHash(s.base_commit)}</code>
                        {s.allowed_paths.length > 0 && ` · ${s.allowed_paths.join(", ")}`}
                      </li>
                    ))}
                  </ul>
                ),
            },
          ]}
        />
        {!isRevoked && has("package.approve_execution") && isHuman && !scope.readOnly && (
          <div>
            <Button
              variant="danger-outline"
              size="sm"
              stretch="auto"
              label={t("project_hub.approval.revoke")}
              onClick={() => setRevokeTarget(approval)}
            />
          </div>
        )}
      </HubCard>
    );
  };

  return (
    <HubSection
      title={t("project_hub.approval.title")}
      actions={
        !scope.readOnly && (
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            disabled={!!disabledReason}
            aria-describedby={disabledReason ? `approve-reason-${scope.issueId}` : undefined}
            label={t("project_hub.approval.approve")}
            onClick={openDialog}
          />
        )
      }
    >
      {!scope.readOnly && disabledReason && (
        <p id={`approve-reason-${scope.issueId}`} className="text-caption-sm-regular text-tertiary">
          {disabledReason}
        </p>
      )}
      <HubResourceBoundary
        resource={approvals}
        loadingRows={1}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.approval.none")} />}
      >
        {(data) => <div className="flex flex-col gap-2">{sortByApprovedAt(data).map(renderApproval)}</div>}
      </HubResourceBoundary>

      {latest && (
        <HubDialog
          isOpen={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          isBusy={isSubmitting}
          title={t("project_hub.approval.dialog_title", { number: latest.number })}
          onSubmit={() => void handleApprove()}
          actions={
            <>
              <Button
                variant="secondary"
                size="md"
                stretch="auto"
                disabled={isSubmitting}
                label={t("project_hub.common.cancel")}
                onClick={() => setIsDialogOpen(false)}
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
                    : t("project_hub.approval.confirm", { number: latest.number })
                }
              />
            </>
          }
        >
          <p className="text-body-xs-regular text-secondary">{t("project_hub.approval.dialog_description")}</p>
          <HubMeta
            items={[
              { label: t("project_hub.approval.revision"), value: `#${latest.number} · ${latest.title}` },
              {
                label: t("project_hub.approval.hash"),
                value: <code className="font-mono break-all">{latest.content_hash}</code>,
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
            <legend className="text-caption-md-medium text-tertiary">
              {t("project_hub.approval.allowed_actions")}
            </legend>
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
            hint={
              parsedChecks === null ? t("project_hub.approval.checks_invalid") : t("project_hub.approval.checks_hint")
            }
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
      )}

      <HubDialog
        isOpen={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        isBusy={isSubmitting}
        title={t("project_hub.approval.revoke")}
        onSubmit={() => void handleRevoke()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              disabled={isSubmitting}
              label={t("project_hub.common.cancel")}
              onClick={() => setRevokeTarget(null)}
            />
            <Button
              type="submit"
              variant="danger"
              size="md"
              stretch="auto"
              loading={isSubmitting}
              disabled={!revokeReason.trim()}
              label={t("project_hub.approval.revoke_confirm")}
            />
          </>
        }
      >
        <HubTextAreaField
          label={t("project_hub.approval.revoke_reason")}
          value={revokeReason}
          required
          onChange={setRevokeReason}
        />
      </HubDialog>
    </HubSection>
  );
});
