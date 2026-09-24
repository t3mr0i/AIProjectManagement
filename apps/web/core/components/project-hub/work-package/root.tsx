/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { ChatOutline, CloseOutline } from "@makeplane/propel/icons";
import { Tab, Tabs, TabsList, TabsPanel } from "@makeplane/propel/components/tabs";
import { useTranslation } from "@plane/i18n";
// local imports
import { PackageDiscussion } from "../discussion/package-discussion";
import { ProjectHubGate } from "../common/gate";
import { PackagePhaseIndicator } from "../common/phase-indicator";
import { HubErrorState, HubFreshnessBanner, HubLoading } from "../common/states";
import { ActivateWorkPackage } from "./activate";
import { BriefTab } from "./brief/brief-tab";
import { ChangesTab } from "./changes/changes-tab";
import { HistoryTab } from "./history/history-tab";
import { ReviewTab } from "./review/review-tab";
import type { TWorkPackageScope } from "./types";
import { usePackageProfile, usePackageStatus } from "./use-work-package";

type TTab = "brief" | "changes" | "review" | "history";
const TABS: TTab[] = ["brief", "changes", "review", "history"];

const WorkPackageContent = observer(function WorkPackageContent(scope: TWorkPackageScope) {
  const { t } = useTranslation();
  const headingId = useId();
  const panelId = useId();
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
    if (profile.error) return <HubErrorState error={profile.error} onRetry={() => void profile.refresh()} />;
    return <HubLoading rows={2} />;
  }
  if (profile.data === null) return <ActivateWorkPackage {...scope} />;

  const packageProfile = profile.data;

  return (
    <section aria-labelledby={headingId} className="@container flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={headingId} className="text-body-md-medium text-primary">
            {t("project_hub.work_package.title")}
          </h2>
          {status.data && <PackagePhaseIndicator status={status.data} />}
        </div>
        <Button
          variant={isDiscussionOpen ? "secondary" : "ghost"}
          size="sm"
          stretch="auto"
          icon={<Icon icon={ChatOutline} />}
          aria-expanded={isDiscussionOpen}
          aria-controls={panelId}
          label={
            isDiscussionOpen
              ? t("project_hub.work_package.close_discussion")
              : t("project_hub.work_package.open_discussion")
          }
          onClick={() => setIsDiscussionOpen((v) => !v)}
        />
      </div>
      {status.data?.explanations && status.data.explanations.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-caption-sm-regular text-secondary">
          {status.data.explanations.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      <HubFreshnessBanner resource={profile} />

      <div className="flex flex-col gap-4 @4xl:flex-row">
        <div className="min-w-0 flex-1">
          <Tabs variant="underline" value={tab} onValueChange={(v) => setTab(v as TTab)}>
            <TabsList aria-label={t("project_hub.work_package.tabs_label")}>
              {TABS.map((key) => (
                <Tab key={key} value={key} label={t(`project_hub.work_package.tabs.${key}`)} />
              ))}
            </TabsList>
            <TabsPanel value="brief">
              <div className="pt-4">
                <BriefTab scope={scope} profile={packageProfile} />
              </div>
            </TabsPanel>
            <TabsPanel value="changes">
              <div className="pt-4">
                <ChangesTab scope={scope} status={status.data} />
              </div>
            </TabsPanel>
            <TabsPanel value="review">
              <div className="pt-4">
                <ReviewTab scope={scope} />
              </div>
            </TabsPanel>
            <TabsPanel value="history">
              <div className="pt-4">
                <HistoryTab scope={scope} />
              </div>
            </TabsPanel>
          </Tabs>
        </div>
        {isDiscussionOpen && (
          <aside
            id={panelId}
            ref={discussionRef}
            tabIndex={-1}
            aria-label={t("project_hub.work_package.discussion")}
            className="focus-visible:outline-accent-primary flex w-full shrink-0 flex-col gap-3 rounded-md border border-subtle bg-layer-1 p-3 focus-visible:outline-2 @4xl:w-[380px]"
            onKeyDown={(e) => {
              if (e.key === "Escape") setIsDiscussionOpen(false);
            }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-body-sm-semibold text-primary">{t("project_hub.work_package.discussion")}</h3>
              <IconButton
                variant="ghost"
                size="sm"
                icon={<Icon icon={CloseOutline} />}
                aria-label={t("project_hub.work_package.close_discussion")}
                onClick={() => setIsDiscussionOpen(false)}
              />
            </div>
            <PackageDiscussion
              workspaceSlug={scope.workspaceSlug}
              projectId={scope.projectId}
              issueId={scope.issueId}
            />
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
 * Work package area inside the native work item detail (PLANE_DELTA §6, PRD §11.2): tabs
 * Auftrag / Änderungen / Review / Verlauf and a toggleable Discussion side panel. Hidden unless the
 * extension is enabled; for issues without a profile only a compact activation action is shown.
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
      <div className="border-t border-subtle pt-4">
        <WorkPackageContent workspaceSlug={workspaceSlug} projectId={projectId} issueId={issueId} readOnly={disabled} />
      </div>
    </ProjectHubGate>
  );
});
