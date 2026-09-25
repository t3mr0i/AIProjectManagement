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
import type { TPackageClaim, TPackageRun, TRunStatus } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import { getHeartbeatState, shortHash } from "@plane/utils";
import type { THeartbeatState } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../../common/dialog";
import { useProjectHubCapabilities } from "../../common/gate";
import { useMemberDisplayName } from "../../common/member-name";
import { WpEntry, WpSection } from "../panel";
import { HubResourceBoundary } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

export type TRunsData = { runs: TPackageRun[]; claims: TPackageClaim[] };

const ACTIVE_RUN = new Set<TRunStatus>(["queued", "claimed", "running", "waiting"]);

const RUN_TONE: Record<TRunStatus, TProjectHubTone> = {
  queued: "neutral",
  claimed: "info",
  running: "brand",
  waiting: "warning",
  failed: "danger",
  cancelled: "neutral",
  finished: "success",
};

const HEARTBEAT_TONE: Record<THeartbeatState, TProjectHubTone> = {
  fresh: "success",
  stale: "warning",
  expired: "danger",
  unknown: "neutral",
};

/** Runs (`{results}`) and claims (`GET .../claims`) are loaded together for one consistent view. */
export const useRunsResource = (scope: TWorkPackageScope) => {
  const store = useProjectHub();
  return useHubResource<TRunsData>(PH_KEYS.runs(scope.issueId), async () => {
    const [runs, claims] = await Promise.all([
      store.executionService.listRuns(scope.workspaceSlug, scope.projectId, scope.issueId),
      store.executionService.listClaims(scope.workspaceSlug, scope.projectId, scope.issueId),
    ]);
    return { runs, claims };
  });
};

/**
 * Claims and runs (S05). Heartbeat age drives a "stale" badge; without any runner report the
 * local state is explicitly "unknown" (INV-09, AC32) instead of implying nothing happens.
 */
export const RunsPanel = observer(function RunsPanel({ scope }: { scope: TWorkPackageScope }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatAge, formatDateTime } = useHubFormatters();
  const displayName = useMemberDisplayName();
  const { has } = useProjectHubCapabilities(scope.workspaceSlug, scope.projectId);
  const runs = useRunsResource(scope);
  const [cancelTarget, setCancelTarget] = useState<TPackageRun | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const handleCancel = async () => {
    if (!cancelTarget) return;
    setIsCancelling(true);
    try {
      await store.executionService.cancelRun(scope.workspaceSlug, scope.projectId, cancelTarget.id);
      // 202: accepted, not finished — show the request, keep the server state.
      showHubSuccessToast(t("project_hub.changes.cancel_requested"));
      setCancelTarget(null);
      store.invalidate(PH_KEYS.runs(scope.issueId));
      store.invalidate(PH_KEYS.status(scope.issueId));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <WpSection title={t("project_hub.changes.runs")}>
      <HubResourceBoundary resource={runs} loadingRows={2}>
        {(data) => {
          const activeClaims = data.claims.filter((c) => c.status === "active");
          const hasRunnerSignal =
            data.runs.some((r) => !!r.last_heartbeat_at) || data.claims.some((c) => !!c.last_heartbeat_at);
          return (
            <div className="flex flex-col divide-y divide-subtle">
              {!hasRunnerSignal && (
                <WpEntry className="flex flex-col gap-1">
                  <ToneBadge tone="neutral" label={t("project_hub.changes.unknown_local")} />
                  <p className="text-caption-sm-regular text-secondary">
                    {t("project_hub.changes.unknown_local_description")}
                  </p>
                </WpEntry>
              )}
              {activeClaims.map((claim) => {
                const hb = getHeartbeatState(claim.last_heartbeat_at, claim.lease_expires_at);
                return (
                  <WpEntry key={claim.id} className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge tone="info" size="xs" label={t(`project_hub.changes.claim_status.${claim.status}`)} />
                      <ToneBadge
                        tone={HEARTBEAT_TONE[hb]}
                        size="xs"
                        label={t(`project_hub.changes.heartbeat_state.${hb}`)}
                      />
                      <span className="text-caption-sm-regular text-tertiary">
                        {claim.exclusive ? t("project_hub.changes.exclusive") : t("project_hub.changes.collaborative")}
                      </span>
                    </div>
                    <p className="text-caption-sm-regular text-secondary">
                      {t("project_hub.changes.claim_holder", { name: displayName(claim.holder_id) })}
                      {claim.repository_name ? ` · ${claim.repository_name}` : ""}
                      {claim.runner_name ? ` · ${claim.runner_name}` : ""}
                    </p>
                    <p className="text-caption-sm-regular text-tertiary">
                      {t("project_hub.changes.lease", { time: formatDateTime(claim.lease_expires_at) })} ·{" "}
                      {t("project_hub.changes.heartbeat", { age: formatAge(claim.last_heartbeat_at) })} ·{" "}
                      {t("project_hub.changes.fencing", { token: claim.fencing_token })}
                    </p>
                  </WpEntry>
                );
              })}
              {data.runs.length === 0 && activeClaims.length === 0 ? (
                <p className="text-body-xs-regular text-tertiary">{t("project_hub.changes.runs_empty")}</p>
              ) : (
                data.runs.map((run) => {
                  const isActive = ACTIVE_RUN.has(run.status);
                  const hb = isActive ? getHeartbeatState(run.last_heartbeat_at) : null;
                  return (
                    <WpEntry key={run.id} className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <ToneBadge
                          tone={RUN_TONE[run.status]}
                          size="xs"
                          label={t(`project_hub.changes.run_status.${run.status}`)}
                        />
                        <ToneBadge tone="neutral" size="xs" label={t(`project_hub.changes.mode.${run.mode}`)} />
                        {hb && (
                          <ToneBadge
                            tone={HEARTBEAT_TONE[hb]}
                            size="xs"
                            label={t(`project_hub.changes.heartbeat_state.${hb}`)}
                          />
                        )}
                        {run.manifest_hash && (
                          <code className="font-mono text-caption-sm-regular text-tertiary" title={run.manifest_hash}>
                            {t("project_hub.changes.manifest", { hash: shortHash(run.manifest_hash) })}
                          </code>
                        )}
                      </div>
                      <p className="text-caption-sm-regular text-secondary">
                        {displayName(run.responsible_id)}
                        {(() => {
                          const name = data.claims.find((c) => c.id === run.claim_id)?.runner_name;
                          return name ? ` · ${name}` : "";
                        })()}
                        {isActive &&
                          ` · ${t("project_hub.changes.heartbeat", { age: formatAge(run.last_heartbeat_at) })}`}
                      </p>
                      {run.progress?.summary && (
                        <p className="text-caption-sm-regular text-secondary">{run.progress.summary}</p>
                      )}
                      {run.progress?.question && (
                        <p className="text-caption-sm-regular text-primary">
                          {t("project_hub.changes.question", { question: run.progress.question })}
                        </p>
                      )}
                      {run.pause_reason && (
                        <p className="text-caption-sm-regular text-tertiary">
                          {t("project_hub.changes.pause_reason", { reason: run.pause_reason })}
                        </p>
                      )}
                      {run.cancel_requested_at && (
                        <p className="text-caption-sm-regular text-tertiary">
                          {t("project_hub.changes.cancel_requested")}
                        </p>
                      )}
                      {isActive && has("run.cancel") && !run.cancel_requested_at && !scope.readOnly && (
                        <div>
                          <Button
                            variant="danger-outline"
                            size="sm"
                            stretch="auto"
                            label={t("project_hub.changes.cancel_run")}
                            onClick={() => setCancelTarget(run)}
                          />
                        </div>
                      )}
                    </WpEntry>
                  );
                })
              )}
            </div>
          );
        }}
      </HubResourceBoundary>
      <HubDialog
        isOpen={!!cancelTarget}
        onClose={() => setCancelTarget(null)}
        isBusy={isCancelling}
        title={t("project_hub.changes.cancel_run_title")}
        onSubmit={() => void handleCancel()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setCancelTarget(null)}
            />
            <Button
              type="submit"
              variant="danger"
              size="md"
              stretch="auto"
              loading={isCancelling}
              label={t("project_hub.changes.cancel_run")}
            />
          </>
        }
      >
        <p className="text-body-xs-regular text-secondary">{t("project_hub.changes.cancel_run_description")}</p>
      </HubDialog>
    </WpSection>
  );
});
