/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { ApproverOutline, BriefsOutline, FlagOutline, PlayCircleOutline, RocketOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPackageDelivery } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import { buildPackageIndicator, cn, getDeliveryLabelKey } from "@plane/utils";
// local imports
import { HubChip } from "../common/chip";
import { ProjectHubGate, useProjectHubCapabilities } from "../common/gate";
import { HubPhaseBadge } from "../common/phase-indicator";
import { HubPropertyRow, HubSidebarCard } from "../common/sidebar-card";
import { HubErrorState, HubLoading } from "../common/states";
import { ApprovalDialog, useApprovalDisabledReason } from "./brief/approval-dialog";
import type { TWorkPackageScope } from "./types";
import {
  findValidApproval,
  useActivatePackage,
  useCreateRevision,
  useLatestRevision,
  usePackageApprovals,
  usePackageProfile,
  usePackageReadiness,
  usePackageRevisions,
  usePackageStatus,
} from "./use-work-package";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const DELIVERY_TONE: Record<TPackageDelivery, TProjectHubTone> = {
  not_integrated: "neutral",
  partially_integrated: "info",
  integrated: "info",
  deployed: "brand",
  released: "success",
  rolled_back: "danger",
  unknown: "neutral",
};

/** Sidebar-sized action button (32px row, right-aligned, never wraps). */
function ActionButton({
  label,
  onClick,
  loading,
  primary,
}: {
  label: string;
  onClick: () => void;
  loading?: boolean;
  primary?: boolean;
}) {
  return (
    <Button
      variant={primary ? "primary" : "secondary"}
      size="sm"
      stretch="auto"
      loading={loading}
      label={label}
      onClick={onClick}
    />
  );
}

const SidebarCardInner = observer(function SidebarCardInner(scope: TWorkPackageScope) {
  const { t } = useTranslation();
  const { has, isHuman } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const profile = usePackageProfile(scope);
  const hasProfile = !!profile.data;
  const status = usePackageStatus(scope, hasProfile);
  const revisions = usePackageRevisions(scope, hasProfile);
  const approvals = usePackageApprovals(scope, hasProfile);
  const readiness = usePackageReadiness(scope, hasProfile);
  const { activate, isActivating } = useActivatePackage(scope);
  const { create, isCreating } = useCreateRevision(scope);
  const [isApproveOpen, setIsApproveOpen] = useState(false);
  const canEdit = has("package.edit") && !scope.readOnly;

  const latest = useLatestRevision(revisions.data);
  const approveDisabledReason = useApprovalDisabledReason({
    isHuman,
    canApprove: has("package.approve_execution"),
    latest,
    ready: readiness.data?.ready,
  });

  if (profile.data === undefined) {
    return (
      <HubSidebarCard title={t("project_hub.work_package.title")} icon={BriefsOutline as TGlyph} body="content">
        {profile.error ? (
          <HubErrorState error={profile.error} size="sm" onRetry={() => void profile.refresh()} />
        ) : (
          <HubLoading rows={2} />
        )}
      </HubSidebarCard>
    );
  }

  // Normal work item: one muted line and the optional activation (never forced, FR-B02).
  if (profile.data === null) {
    return (
      <HubSidebarCard title={t("project_hub.work_package.title")} icon={BriefsOutline as TGlyph}>
        <HubPropertyRow
          icon={PlayCircleOutline as TGlyph}
          label={t("project_hub.work_package.sidebar.status")}
          value={<span className="text-secondary">{t("project_hub.work_package.activate_title")}</span>}
        />
        {canEdit && (
          <HubPropertyRow label={t("project_hub.work_package.sidebar.next_step")}>
            <ActionButton
              label={isActivating ? t("project_hub.work_package.activating") : t("project_hub.work_package.activate")}
              loading={isActivating}
              onClick={() => void activate()}
            />
          </HubPropertyRow>
        )}
        <p className="px-3 pt-1 pb-1 text-caption-md-regular text-tertiary">
          {t("project_hub.work_package.sidebar.hint")}
        </p>
      </HubSidebarCard>
    );
  }

  const indicator = status.data ? buildPackageIndicator(status.data) : undefined;
  const delivery = status.data?.delivery;
  const validApproval = findValidApproval(approvals.data);
  const approvedNumber = validApproval
    ? (revisions.data?.find((r) => r.id === validApproval.revision_id)?.number ?? latest?.number)
    : undefined;
  const revisionsLoaded = revisions.data !== undefined;
  const needsRevision = revisionsLoaded && (!latest || latest.is_stale);

  const approvalValue = !revisionsLoaded ? undefined : validApproval ? (
    <HubChip
      tone="success"
      label={t("project_hub.work_package.sidebar.approved_revision", { number: approvedNumber ?? "?" })}
    />
  ) : latest ? (
    <HubChip
      tone={latest.is_stale ? "warning" : "neutral"}
      label={
        latest.is_stale
          ? t("project_hub.revisions.stale")
          : t("project_hub.work_package.sidebar.pending_revision", { number: latest.number })
      }
    />
  ) : undefined;

  // Exactly one primary next step, in this order: create a revision → approve it → nothing.
  let nextStep: ReactNode = null;
  let nextStepHint: string | undefined;
  if (canEdit && needsRevision) {
    nextStep = (
      <ActionButton
        label={isCreating ? t("project_hub.revisions.creating") : t("project_hub.revisions.create")}
        loading={isCreating}
        onClick={() => void create()}
      />
    );
  } else if (latest && !latest.is_approved && !scope.readOnly) {
    if (approveDisabledReason === null) {
      nextStep = (
        <ActionButton
          primary
          label={t("project_hub.work_package.sidebar.approve", { number: latest.number })}
          onClick={() => setIsApproveOpen(true)}
        />
      );
    } else {
      nextStepHint = approveDisabledReason;
    }
  }

  return (
    <HubSidebarCard title={t("project_hub.work_package.title")} icon={BriefsOutline as TGlyph}>
      <HubPropertyRow
        icon={PlayCircleOutline as TGlyph}
        label={t("project_hub.work_package.sidebar.phase")}
        value={indicator ? <HubPhaseBadge phase={indicator.phase} size="xs" /> : undefined}
        placeholder={status.error ? t("project_hub.common.not_available") : t("project_hub.common.loading")}
      />
      <HubPropertyRow
        icon={RocketOutline as TGlyph}
        label={t("project_hub.work_package.sidebar.delivery")}
        value={
          delivery ? <HubChip tone={DELIVERY_TONE[delivery]} label={t(getDeliveryLabelKey(delivery))} /> : undefined
        }
        placeholder={status.error ? t("project_hub.common.not_available") : t("project_hub.common.loading")}
      />
      <HubPropertyRow
        icon={ApproverOutline as TGlyph}
        label={t("project_hub.work_package.sidebar.approval")}
        value={approvalValue}
        placeholder={
          revisions.error
            ? t("project_hub.common.not_available")
            : revisionsLoaded
              ? t("project_hub.work_package.sidebar.no_revision")
              : t("project_hub.common.loading")
        }
      />
      {indicator && indicator.flags.length > 0 && (
        <HubPropertyRow
          icon={FlagOutline as TGlyph}
          label={t("project_hub.work_package.sidebar.flags")}
          value={
            <span
              className="flex min-w-0 items-center gap-1"
              title={indicator.flags.map((f) => t(f.labelKey)).join(", ")}
            >
              <HubChip tone={indicator.flags[0].tone} label={t(indicator.flags[0].labelKey)} />
              {indicator.flags.length > 1 && (
                <span className="shrink-0 text-caption-md-regular text-tertiary">+{indicator.flags.length - 1}</span>
              )}
            </span>
          }
        />
      )}
      {(nextStep || nextStepHint) && (
        <HubPropertyRow
          label={t("project_hub.work_package.sidebar.next_step")}
          value={
            nextStepHint ? (
              <span className={cn("truncate text-caption-md-regular text-tertiary")} title={nextStepHint}>
                {nextStepHint}
              </span>
            ) : undefined
          }
        >
          {nextStep ?? undefined}
        </HubPropertyRow>
      )}
      {latest && (
        <ApprovalDialog
          scope={scope}
          revision={latest}
          isOpen={isApproveOpen}
          onClose={() => setIsApproveOpen(false)}
        />
      )}
    </HubSidebarCard>
  );
});

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  /** Archived or not editable in native Plane. */
  disabled?: boolean;
  className?: string;
};

/**
 * "Work package" card for the native right properties sidebar (UI_GUIDELINES "Detail pages"):
 * phase, delivery, approval state, flags and exactly one primary next step. Hidden unless the
 * extension is enabled; a normal work item shows the optional activation here instead of a callout.
 */
export const WorkPackageSidebarCard = observer(function WorkPackageSidebarCard({
  workspaceSlug,
  projectId,
  issueId,
  disabled = false,
  className,
}: Props) {
  if (!workspaceSlug || !projectId || !issueId) return null;
  return (
    <ProjectHubGate workspaceSlug={workspaceSlug} projectId={projectId}>
      <div className={cn("w-full min-w-0", className)}>
        <SidebarCardInner workspaceSlug={workspaceSlug} projectId={projectId} issueId={issueId} readOnly={disabled} />
      </div>
    </ProjectHubGate>
  );
});
