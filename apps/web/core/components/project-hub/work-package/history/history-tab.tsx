/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { TDeliveryStage, TPackageDeliveryView, TPHActivityFeed, TPHDecision } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import { adaptActivityFeed, getDeliveryLabelKey, groupActivityByDay, shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { ActivityGroupItem } from "../../common/activity-group";
import { HubCard, HubSection } from "../../common/section";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import type { TWorkPackageScope } from "../types";

const STAGE_TONE: Record<TDeliveryStage | "unknown", TProjectHubTone> = {
  integrated: "info",
  artifact_built: "info",
  deployed: "brand",
  released: "success",
  rolled_back: "danger",
  unknown: "neutral",
};

/** Package history horizon: activity of the last 90 days. */
const HISTORY_SINCE = () => new Date(Date.now() - 90 * 86_400_000).toISOString();

/** "Verlauf" tab: compacted package activity, linked decisions, delivery chain incl. rollbacks (S07). */
export const HistoryTab = observer(function HistoryTab({ scope }: { scope: TWorkPackageScope }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime, formatDate } = useHubFormatters();
  const { workspaceSlug, projectId, issueId } = scope;

  const activity = useHubResource<TPHActivityFeed>(
    PH_KEYS.activity(workspaceSlug, projectId, `issue:${issueId}`, ""),
    () => store.knowledgeService.getActivity(workspaceSlug, projectId, { since: HISTORY_SINCE(), issue_id: issueId })
  );
  const decisions = useHubResource<TPHDecision[]>(PH_KEYS.decisions(workspaceSlug, projectId, issueId), () =>
    store.collaborationService.listDecisions(workspaceSlug, projectId, issueId)
  );
  const delivery = useHubResource<TPackageDeliveryView>(PH_KEYS.delivery(issueId), () =>
    store.integrationService.getDelivery(workspaceSlug, projectId, issueId)
  );

  return (
    <div className="flex flex-col gap-6">
      <HubSection title={t("project_hub.history.delivery")}>
        <HubResourceBoundary
          resource={delivery}
          loadingRows={2}
          isEmpty={(d) => d.repositories.length === 0 && d.history.length === 0}
          empty={<HubEmpty title={t("project_hub.history.delivery_empty")} />}
        >
          {(data) => (
            <div className="flex flex-col gap-3">
              <p className="text-caption-sm-regular text-secondary">
                {t("project_hub.history.aggregate", { state: t(getDeliveryLabelKey(data.delivery)) })} ·{" "}
                {t("project_hub.history.local_state_unknown")}
              </p>
              {data.integrations.length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {data.integrations.map((i) => (
                    <li key={i.connection_id}>
                      <ToneBadge
                        tone="warning"
                        size="xs"
                        label={t("project_hub.activity.source_health", {
                          source: i.provider,
                          time: formatDateTime(i.last_successful_sync_at),
                        })}
                      />
                    </li>
                  ))}
                </ul>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-body-xs-regular">
                  <caption className="sr-only">{t("project_hub.history.delivery")}</caption>
                  <thead>
                    <tr className="border-b border-subtle text-tertiary">
                      <th scope="col" className="py-1.5 pr-3 font-medium">
                        {t("project_hub.changes.repository")}
                      </th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">
                        {t("project_hub.history.delivery")}
                      </th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">
                        {t("project_hub.history.environment")}
                      </th>
                      <th scope="col" className="py-1.5 font-medium">
                        {t("project_hub.history.commit")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.repositories.map((repo) => (
                      <tr key={repo.binding_id} className="border-b border-subtle align-top">
                        <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                          {repo.name}
                          {repo.role && <span className="text-tertiary"> · {repo.role}</span>}
                        </th>
                        <td className="py-1.5 pr-3">
                          <ToneBadge
                            tone={STAGE_TONE[repo.delivery as TDeliveryStage] ?? "neutral"}
                            size="xs"
                            label={t(getDeliveryLabelKey(repo.delivery))}
                          />
                          {repo.delivery === "deployed" && (
                            <p className="pt-1 text-caption-sm-regular text-tertiary">
                              {t("project_hub.history.deployed_not_released")}
                            </p>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-secondary">
                          {repo.environments.length === 0
                            ? "—"
                            : repo.environments.map((env) => (
                                <span key={env.name} className="block">
                                  {env.name}: {t(`project_hub.history.stage.${env.state}`)} ({shortHash(env.commit_sha)}
                                  )
                                </span>
                              ))}
                        </td>
                        <td className="py-1.5 text-secondary">
                          {repo.integrated_commit_sha ? (
                            <code className="font-mono">{shortHash(repo.integrated_commit_sha)}</code>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.history.length > 0 && (
                <div className="flex flex-col gap-1">
                  <p className="text-caption-md-medium text-tertiary">{t("project_hub.history.history_title")}</p>
                  <ol className="flex flex-col gap-1 border-l-2 border-subtle pl-3">
                    {data.history.map((entry) => (
                      <li key={entry.id} className="text-caption-sm-regular text-secondary">
                        <ToneBadge
                          tone={STAGE_TONE[entry.stage] ?? "neutral"}
                          size="xs"
                          label={t(`project_hub.history.stage.${entry.stage}`)}
                        />{" "}
                        {data.repositories.find((r) => r.binding_id === entry.binding_id)?.name ?? ""}{" "}
                        {entry.environment && `· ${entry.environment}`}{" "}
                        {entry.commit_sha && (
                          <>
                            · <code className="font-mono">{shortHash(entry.commit_sha)}</code>
                          </>
                        )}{" "}
                        · {entry.source} · {formatDateTime(entry.occurred_at)}
                        {entry.reverts && ` · ${t("project_hub.history.rollback")}`}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}
        </HubResourceBoundary>
      </HubSection>

      <HubSection title={t("project_hub.history.decisions")}>
        <HubResourceBoundary
          resource={decisions}
          loadingRows={1}
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty title={t("project_hub.history.decisions_empty")} />}
        >
          {(data) => (
            <ul className="flex flex-col gap-2">
              {data.map((decision) => (
                <li key={decision.id}>
                  <HubCard className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body-xs-medium text-primary">{decision.title}</span>
                      {decision.source_changed_since_decision && (
                        <ToneBadge tone="warning" size="xs" label={t("project_hub.history.source_changed")} />
                      )}
                    </div>
                    <p className="text-caption-sm-regular whitespace-pre-wrap text-secondary">{decision.text}</p>
                    {decision.rationale && (
                      <p className="text-caption-sm-regular text-tertiary">{decision.rationale}</p>
                    )}
                    <p className="text-caption-sm-regular text-tertiary">
                      {formatDate(decision.confirmed_at ?? decision.created_at)}
                    </p>
                  </HubCard>
                </li>
              ))}
            </ul>
          )}
        </HubResourceBoundary>
      </HubSection>

      <HubSection title={t("project_hub.history.timeline")}>
        <HubResourceBoundary
          resource={activity}
          loadingRows={3}
          isEmpty={(d) => adaptActivityFeed(d).filter((g) => g.issue_id === issueId).length === 0}
          empty={<HubEmpty title={t("project_hub.history.timeline_empty")} />}
        >
          {(data) => (
            <div className="flex flex-col gap-4">
              {groupActivityByDay(adaptActivityFeed(data).filter((g) => g.issue_id === issueId)).map((section) => (
                <div key={section.day} className="flex flex-col gap-2">
                  <h4 className="text-caption-md-medium text-tertiary">{formatDate(section.day)}</h4>
                  {section.groups.map((group) => (
                    <ActivityGroupItem
                      key={`${group.issue_id}-${group.day}-${group.first_at}`}
                      group={group}
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                      hidePackage
                    />
                  ))}
                </div>
              ))}
            </div>
          )}
        </HubResourceBoundary>
      </HubSection>
    </div>
  );
});
