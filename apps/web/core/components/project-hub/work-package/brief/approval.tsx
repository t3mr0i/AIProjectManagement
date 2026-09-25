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
import type { TExecutionApproval, TPackageReadiness, TPackageRevision } from "@plane/types";
import { getApprovalValidity, shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { HubTextAreaField } from "../../common/field";
import { useProjectHubCapabilities } from "../../common/gate";
import { useMemberDisplayName } from "../../common/member-name";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { showHubErrorToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import type { THubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import { WpEntry, WpEntryList, WpMutedLine, WpSection } from "../panel";
import type { TWorkPackageScope } from "../types";
import { useLatestRevision } from "../use-work-package";
import { ApprovalDialog, useApprovalDisabledReason } from "./approval-dialog";

const sortByApprovedAt = (list: TExecutionApproval[]) =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted typing)
  [...list].sort((a, b) => Date.parse(b.approved_at) - Date.parse(a.approved_at));

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

  const latest = useLatestRevision(revisions);
  const disabledReason = useApprovalDisabledReason({
    isHuman,
    canApprove: has("package.approve_execution"),
    latest,
    ready: readiness?.ready,
  });

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
    const checks = approval.checks ?? [];
    return (
      <WpEntry key={approval.id}>
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 text-13 font-medium text-primary">
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
          <span className="flex-1" />
          {!isRevoked && has("package.approve_execution") && isHuman && !scope.readOnly && (
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              label={t("project_hub.approval.revoke")}
              onClick={() => setRevokeTarget(approval)}
            />
          )}
        </div>
        <WpMutedLine>
          {t("project_hub.approval.approved_by", {
            name: displayName(approval.approved_by),
            time: formatDateTime(approval.approved_at),
          })}{" "}
          · {t("project_hub.approval.expires", { time: formatDateTime(approval.expires_at) })}
        </WpMutedLine>
        <WpMutedLine title={approval.revision_hash}>
          {t("project_hub.approval.hash")}: <code className="font-mono">{shortHash(approval.revision_hash)}</code> ·{" "}
          {t("project_hub.approval.allowed_actions")}: {approval.allowed_actions.join(", ") || "—"}
        </WpMutedLine>
        <WpMutedLine className="whitespace-normal">
          {t("project_hub.approval.scope")}:{" "}
          {approval.repository_scope.length === 0
            ? t("project_hub.approval.no_repositories")
            : approval.repository_scope.map((s, i) => (
                <span key={s.binding_id}>
                  {i > 0 && " · "}
                  {s.target_branch} @ <code className="font-mono">{shortHash(s.base_commit)}</code>
                  {s.allowed_paths.length > 0 && ` (${s.allowed_paths.join(", ")})`}
                </span>
              ))}
        </WpMutedLine>
        {checks.length > 0 && (
          <WpMutedLine className="whitespace-normal">
            {t("project_hub.approval.checks")}:{" "}
            {checks.map((c, i) => (
              <span key={c.name}>
                {i > 0 && " · "}
                <code className="font-mono">
                  {c.name}: {c.command.join(" ")}
                </code>
                {c.trusted ? ` (${t("project_hub.approval.trusted")})` : ""}
              </span>
            ))}
          </WpMutedLine>
        )}
      </WpEntry>
    );
  };

  return (
    <WpSection
      title={t("project_hub.approval.title")}
      description={!scope.readOnly && disabledReason ? disabledReason : undefined}
      actions={
        !scope.readOnly && (
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            disabled={!!disabledReason}
            label={t("project_hub.approval.approve")}
            onClick={() => setIsDialogOpen(true)}
          />
        )
      }
    >
      <HubResourceBoundary
        resource={approvals}
        loadingRows={1}
        size="sm"
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty size="sm" title={t("project_hub.approval.none")} />}
      >
        {(data) => <WpEntryList>{sortByApprovedAt(data).map(renderApproval)}</WpEntryList>}
      </HubResourceBoundary>

      {latest && (
        <ApprovalDialog scope={scope} revision={latest} isOpen={isDialogOpen} onClose={() => setIsDialogOpen(false)} />
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
    </WpSection>
  );
});
