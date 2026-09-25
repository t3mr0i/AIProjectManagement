/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { ChatOutline, CloseOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { PackageDiscussion } from "../discussion/package-discussion";
import { ProjectHubGate } from "../common/gate";
import { HubViewTabs } from "../common/page";
import { HubErrorState, HubFreshnessBanner, HubLoading } from "../common/states";
import { BriefTab } from "./brief/brief-tab";
import { ChangesTab } from "./changes/changes-tab";
import { HistoryTab } from "./history/history-tab";
import { WpMutedLine } from "./panel";
import { ReviewTab } from "./review/review-tab";
import type { TWorkPackageScope } from "./types";
import { usePackageProfile, usePackageStatus } from "./use-work-package";

type TTab = "brief" | "changes" | "review" | "history";
const TABS: TTab[] = ["brief", "changes", "review", "history"];

const WorkPackageContent = observer(function WorkPackageContent(scope: TWorkPackageScope) {
  const { t } = useTranslation();
  const headingId = useId();
  const panelId = useId();
  const discussionId = useId();
  const [tab, setTab] = useState<TTab>("brief");
  const [isDiscussionOpen, setIsDiscussionOpen] = useState(false);
  const discussionRef = useRef<HTMLElement>(null);
  const profile = usePackageProfile(scope);
  const status = usePackageStatus(scope, !!profile.data);

  // Move focus into the side panel when it opens (keyboard users land in the discussion).
  useEffect(() => {
    if (isDiscussionOpen) discussionRef.current?.focus();
  }, [isDiscussionOpen]);

  if (profile.data === undefined) {
    if (profile.error)
      return (
        <div className="border-t border-subtle pt-3">
          <HubErrorState error={profile.error} size="sm" onRetry={() => void profile.refresh()} />
        </div>
      );
    return (
      <div className="border-t border-subtle pt-3">
        <HubLoading rows={2} />
      </div>
    );
  }
  // Normal work item: nothing in the content flow — activation lives in the sidebar card.
  if (profile.data === null) return null;

  const packageProfile = profile.data;
  const explanations = status.data?.explanations ?? [];
  const discussionLabel = isDiscussionOpen
    ? t("project_hub.work_package.close_discussion")
    : t("project_hub.work_package.open_discussion");

  return (
    <section aria-labelledby={headingId} className="@container flex min-w-0 flex-col gap-3 border-t border-subtle pt-3">
      <div className="flex min-w-0 items-center gap-3">
        <h2 id={headingId} className="shrink-0 text-13 font-medium text-primary">
          {t("project_hub.work_package.title")}
        </h2>
        <HubViewTabs
          aria-label={t("project_hub.work_package.tabs_label")}
          activeKey={tab}
          onTabChange={(key) => setTab(key as TTab)}
          tabs={TABS.map((key) => ({ key, label: t(`project_hub.work_package.tabs.${key}`) }))}
        />
        <span className="flex-1" />
        <Tooltip label={discussionLabel}>
          <IconButton
            variant={isDiscussionOpen ? "secondary" : "ghost"}
            size="sm"
            icon={<Icon icon={ChatOutline} />}
            aria-label={discussionLabel}
            aria-pressed={isDiscussionOpen}
            aria-expanded={isDiscussionOpen}
            aria-controls={discussionId}
            onClick={() => setIsDiscussionOpen((v) => !v)}
          />
        </Tooltip>
      </div>
      {explanations.length > 0 && (
        <WpMutedLine title={explanations.join(" · ")}>{explanations.join(" · ")}</WpMutedLine>
      )}
      <HubFreshnessBanner resource={profile} />

      <div className="flex min-w-0 flex-col gap-4 @4xl:flex-row">
        <div id={panelId} role="tabpanel" className="min-w-0 flex-1">
          {tab === "brief" && <BriefTab scope={scope} profile={packageProfile} />}
          {tab === "changes" && <ChangesTab scope={scope} status={status.data} />}
          {tab === "review" && <ReviewTab scope={scope} />}
          {tab === "history" && <HistoryTab scope={scope} />}
        </div>
        {isDiscussionOpen && (
          <aside
            id={discussionId}
            ref={discussionRef}
            tabIndex={-1}
            aria-label={t("project_hub.work_package.discussion")}
            className={cn(
              "flex w-full shrink-0 flex-col overflow-hidden rounded-md border border-subtle bg-layer-1",
              "focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none @4xl:w-[360px]"
            )}
            onKeyDown={(e) => {
              if (e.key === "Escape") setIsDiscussionOpen(false);
            }}
          >
            <div className="flex h-8 shrink-0 items-center gap-1 bg-layer-2 pr-1 pl-3">
              <h3 className="min-w-0 flex-1 truncate text-13 font-medium text-primary">
                {t("project_hub.work_package.discussion")}
              </h3>
              <IconButton
                variant="ghost"
                size="xs"
                icon={<Icon icon={CloseOutline} />}
                aria-label={t("project_hub.work_package.close_discussion")}
                onClick={() => setIsDiscussionOpen(false)}
              />
            </div>
            <div className="flex min-w-0 flex-col gap-2 p-2">
              <PackageDiscussion
                workspaceSlug={scope.workspaceSlug}
                projectId={scope.projectId}
                issueId={scope.issueId}
              />
            </div>
          </aside>
        )}
      </div>
    </section>
  );
});

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  /** Archived or not editable in native Plane. */
  disabled?: boolean;
};

/**
 * Work package area inside the native work item detail (PLANE_DELTA §6, PRD §11.2): compact
 * pill tabs Brief / Changes / Review / History below the description and a toggleable
 * Discussion side panel. Hidden unless the extension is enabled; issues without a profile render
 * nothing here (activation lives in the sidebar "Work package" card).
 */
export const WorkPackageSection = observer(function WorkPackageSection({
  workspaceSlug,
  projectId,
  issueId,
  disabled = false,
}: Props) {
  if (!workspaceSlug || !projectId || !issueId) return null;
  return (
    <ProjectHubGate workspaceSlug={workspaceSlug} projectId={projectId}>
      <WorkPackageContent workspaceSlug={workspaceSlug} projectId={projectId} issueId={issueId} readOnly={disabled} />
    </ProjectHubGate>
  );
});
