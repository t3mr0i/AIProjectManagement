/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { observer } from "mobx-react";
// plane imports
import {
  BuildOutline,
  CubeOutline,
  DeleteArrowOutline,
  GitMergeOutline,
  RocketOutline,
  TickCircleOutline,
  UpdatesOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TDeliveryStage, TPackageDeliveryView, TPHActivityFeed, TPHDecision } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import { adaptActivityFeed, getDeliveryLabelKey, groupActivityByDay, shortHash } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { ActivityGroupItem, HubTimelineRow } from "../../common/activity-group";
import { HubChip } from "../../common/chip";
import { HubGroupBar } from "../../common/list";
import { HubEmpty, HubResourceBoundary } from "../../common/states";
import { ToneBadge } from "../../common/tone-badge";
import { useHubResource } from "../../common/use-hub-resource";
import { useHubFormatters } from "../../common/use-relative-time";
import { WpEntry, WpEntryList, WpMutedLine, WpSection } from "../panel";
import type { TWorkPackageScope } from "../types";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const STAGE_TONE: Record<TDeliveryStage | "unknown", TProjectHubTone> = {
  integrated: "info",
  artifact_built: "info",
  deployed: "brand",
  released: "success",
  rolled_back: "danger",
  unknown: "neutral",
};

const STAGE_ICON: Record<TDeliveryStage | "unknown", TGlyph> = {
  integrated: GitMergeOutline as TGlyph,
  artifact_built: BuildOutline as TGlyph,
  deployed: RocketOutline as TGlyph,
  released: TickCircleOutline as TGlyph,
  rolled_back: DeleteArrowOutline as TGlyph,
  unknown: CubeOutline as TGlyph,
};

/** Package history horizon: activity of the last 90 days. */
const HISTORY_SINCE = () => new Date(Date.now() - 90 * 86_400_000).toISOString();

/** "Verlauf" tab: delivery chain incl. rollbacks, linked decisions, compacted package activity (S07). */
export const HistoryTab = observer(function HistoryTab({ scope }: { scope: TWorkPackageScope }) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { formatDateTime, formatDate, formatAge } = useHubFormatters();
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
    <div className="flex min-w-0 flex-col gap-5">
      <WpSection title={t("project_hub.history.delivery")}>
        <HubResourceBoundary
          resource={delivery}
          loadingRows={2}
          size="sm"
          isEmpty={(d) => d.repositories.length === 0 && d.history.length === 0}
          empty={<HubEmpty size="sm" title={t("project_hub.history.delivery_empty")} />}
        >
          {(data) => (
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <HubChip
                  tone={STAGE_TONE[data.delivery as TDeliveryStage] ?? "neutral"}
                  label={t("project_hub.history.aggregate", { state: t(getDeliveryLabelKey(data.delivery)) })}
                />
                {data.integrations.map((i) => (
                  <HubChip
                    key={i.connection_id}
                    tone="warning"
                    label={t("project_hub.activity.source_health", {
                      source: i.provider,
                      time: formatDateTime(i.last_successful_sync_at),
                    })}
                  />
                ))}
                <span className="text-caption-md-regular text-tertiary">
                  {t("project_hub.history.local_state_unknown")}
                </span>
              </div>
              {data.repositories.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-caption-md-regular">
                    <caption className="sr-only">{t("project_hub.history.delivery")}</caption>
                    <thead>
                      <tr className="border-b border-subtle text-tertiary">
                        <th scope="col" className="py-1 pr-3 font-medium">
                          {t("project_hub.changes.repository")}
                        </th>
                        <th scope="col" className="py-1 pr-3 font-medium">
                          {t("project_hub.history.delivery")}
                        </th>
                        <th scope="col" className="py-1 pr-3 font-medium">
                          {t("project_hub.history.environment")}
                        </th>
                        <th scope="col" className="py-1 font-medium">
                          {t("project_hub.history.commit")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.repositories.map((repo) => (
                        <tr key={repo.binding_id} className="border-b border-subtle align-top last:border-b-0">
                          <th scope="row" className="py-1.5 pr-3 font-medium text-primary">
                            {repo.name}
                            {repo.role && <span className="font-normal text-tertiary"> · {repo.role}</span>}
                          </th>
                          <td className="py-1.5 pr-3">
                            <HubChip
                              tone={STAGE_TONE[repo.delivery as TDeliveryStage] ?? "neutral"}
                              label={t(getDeliveryLabelKey(repo.delivery))}
                              title={
                                repo.delivery === "deployed"
                                  ? t("project_hub.history.deployed_not_released")
                                  : undefined
                              }
                            />
                            {repo.delivery === "deployed" && (
                              <span className="block pt-0.5 text-caption-sm-regular text-tertiary">
                                {t("project_hub.history.deployed_not_released")}
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 pr-3 text-secondary">
                            {repo.environments.length === 0
                              ? "—"
                              : repo.environments.map((env) => (
                                  <span key={env.name} className="block">
                                    {env.name}: {t(`project_hub.history.stage.${env.state}`)} (
                                    {shortHash(env.commit_sha)})
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
              )}
              {data.history.length > 0 && (
                <div className="flex min-w-0 flex-col">
                  <HubGroupBar
                    sticky={false}
                    icon={UpdatesOutline as TGlyph}
                    title={t("project_hub.history.history_title")}
                    count={data.history.length}
                    className="rounded-sm"
                  />
                  <ol className="flex min-w-0 flex-col py-1">
                    {data.history.map((entry) => {
                      const Glyph = STAGE_ICON[entry.stage] ?? STAGE_ICON.unknown;
                      const repoName = data.repositories.find((r) => r.binding_id === entry.binding_id)?.name ?? "";
                      return (
                        <li key={entry.id}>
                          <HubTimelineRow
                            icon={<Glyph />}
                            time={formatAge(entry.occurred_at)}
                            timeTitle={formatDateTime(entry.occurred_at)}
                            trailing={
                              entry.reverts ? (
                                <ToneBadge tone="danger" size="xs" label={t("project_hub.history.rollback")} />
                              ) : undefined
                            }
                          >
                            <span className="text-primary">{t(`project_hub.history.stage.${entry.stage}`)}</span>
                            {repoName && <span> · {repoName}</span>}
                            {entry.environment && <span> · {entry.environment}</span>}
                            {entry.commit_sha && (
                              <span>
                                {" "}
                                · <code className="font-mono">{shortHash(entry.commit_sha)}</code>
                              </span>
                            )}
                            <span className="text-tertiary"> · {entry.source}</span>
                          </HubTimelineRow>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              )}
            </div>
          )}
        </HubResourceBoundary>
      </WpSection>

      <WpSection title={t("project_hub.history.decisions")}>
        <HubResourceBoundary
          resource={decisions}
          loadingRows={1}
          size="sm"
          isEmpty={(d) => d.length === 0}
          empty={<HubEmpty size="sm" title={t("project_hub.history.decisions_empty")} />}
        >
          {(data) => (
            <WpEntryList>
              {data.map((decision) => (
                <WpEntry key={decision.id}>
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-13 font-medium text-primary">{decision.title}</span>
                    {decision.source_changed_since_decision && (
                      <HubChip tone="warning" label={t("project_hub.history.source_changed")} />
                    )}
                    <span className="shrink-0 text-caption-md-regular text-tertiary tabular-nums">
                      {formatDate(decision.confirmed_at ?? decision.created_at)}
                    </span>
                  </div>
                  <p className="text-caption-md-regular whitespace-pre-wrap text-secondary">{decision.text}</p>
                  {decision.rationale && <WpMutedLine className="whitespace-normal">{decision.rationale}</WpMutedLine>}
                </WpEntry>
              ))}
            </WpEntryList>
          )}
        </HubResourceBoundary>
      </WpSection>

      <WpSection title={t("project_hub.history.timeline")}>
        <HubResourceBoundary
          resource={activity}
          loadingRows={3}
          size="sm"
          isEmpty={(d) => adaptActivityFeed(d).filter((g) => g.issue_id === issueId).length === 0}
          empty={<HubEmpty size="sm" title={t("project_hub.history.timeline_empty")} />}
        >
          {(data) => (
            <div className="flex min-w-0 flex-col gap-2">
              {groupActivityByDay(adaptActivityFeed(data).filter((g) => g.issue_id === issueId)).map((section) => (
                <section key={section.day} className="flex min-w-0 flex-col" aria-label={formatDate(section.day)}>
                  <HubGroupBar
                    sticky={false}
                    title={formatDate(section.day)}
                    count={section.groups.reduce((n, g) => n + g.event_count, 0)}
                    className="rounded-sm"
                  />
                  {section.groups.map((group) => (
                    <ActivityGroupItem
                      key={`${group.issue_id}-${group.day}-${group.first_at}`}
                      group={group}
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                      hidePackage
                    />
                  ))}
                </section>
              ))}
            </div>
          )}
        </HubResourceBoundary>
      </WpSection>
    </div>
  );
});
