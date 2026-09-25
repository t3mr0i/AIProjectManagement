/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useId, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AiStarOneOutline, ChevronRightOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHProposal } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubEmptyState, HubErrorState, HubLoading } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { useHubFormatters } from "../common/use-relative-time";
import { HubAIFindings, HubAIModelLine, HubAIResultNotice, HubAISources, HubAIStatements } from "./result";
import { HubAIStatusBadge } from "./status-badge";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/** Latest project status report = newest `answer` proposal without work item and `task: report`. */
const pickLatestReport = (proposals: TPHProposal[]): TPHProposal | null =>
  proposals.find((p) => !p.issue_id && p.content.task === "report") ?? null;

/** Collapsed "facts the report is based on" block (the aggregated snapshot text). */
function SnapshotDisclosure({ snapshot }: { snapshot: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="-ml-1 flex h-6 w-fit items-center gap-1 rounded-sm px-1 text-caption-md-medium text-tertiary transition-colors duration-100 hover:bg-layer-transparent-hover hover:text-primary focus-visible:ring-1 focus-visible:ring-accent-strong focus-visible:outline-none"
      >
        <ChevronRightOutline className={cn("size-3 transition-transform", open && "rotate-90")} aria-hidden="true" />
        {t("project_hub.ai.report.snapshot")}
      </button>
      {open && (
        <pre
          id={panelId}
          className="font-mono overflow-x-auto rounded-md border border-subtle bg-layer-2 px-3 py-2 text-caption-sm-regular whitespace-pre-wrap text-secondary"
        >
          {snapshot}
        </pre>
      )}
    </div>
  );
}

/**
 * "AI status report" card on the project overview: generates a report from the data every project
 * member can read and shows each statement with its status plus the sources used.
 */
export const HubProjectAIReportCard = observer(function HubProjectAIReportCard({
  workspaceSlug,
  projectId,
  className,
}: {
  workspaceSlug: string;
  projectId: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const headingId = useId();
  const { formatAge, formatDateTime } = useHubFormatters();
  const [isBusy, setIsBusy] = useState(false);
  const key = PH_KEYS.aiReport(workspaceSlug, projectId);
  const report = useHubResource<TPHProposal | null>(key, async () =>
    pickLatestReport(await store.collaborationService.listProposals(workspaceSlug, projectId, { kind: "answer" }))
  );

  const generate = async () => {
    setIsBusy(true);
    try {
      const proposal = await store.aiService.createProjectReport(workspaceSlug, projectId);
      // A failed AI call is still stored (status + error) and rendered as a notice below.
      store.setResource(key, proposal);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsBusy(false);
    }
  };

  const data = report.data;
  const content = data?.content;
  const result = content?.result;

  return (
    <section
      aria-labelledby={headingId}
      className={cn("flex min-w-0 flex-col gap-3 rounded-md border border-subtle bg-layer-1 p-3", className)}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-center gap-2">
          <AiStarOneOutline className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
          <h2 id={headingId} className="truncate text-13 font-medium text-primary">
            {t("project_hub.ai.report.title")}
          </h2>
          <HubAIStatusBadge workspaceSlug={workspaceSlug} />
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {data?.created_at && (
            <span className="text-caption-md-regular text-tertiary" title={formatDateTime(data.created_at)}>
              {formatAge(data.created_at)}
            </span>
          )}
          <Button
            variant={data ? "secondary" : "primary"}
            size="sm"
            stretch="auto"
            icon={<Icon icon={AiStarOneOutline} />}
            loading={isBusy}
            label={data ? t("project_hub.ai.report.regenerate") : t("project_hub.ai.report.generate")}
            onClick={() => void generate()}
          />
        </div>
      </div>

      {data === undefined ? (
        report.error ? (
          <HubErrorState size="sm" error={report.error} onRetry={() => void report.refresh()} />
        ) : (
          <HubLoading rows={2} />
        )
      ) : !content ? (
        <HubEmptyState
          size="sm"
          icon={AiStarOneOutline as TGlyph}
          title={t("project_hub.ai.report.empty")}
          description={t("project_hub.ai.report.description")}
        />
      ) : (
        <div aria-live="polite" className="flex min-w-0 flex-col gap-3">
          <HubAIResultNotice result={result} />
          {(content.statements ?? []).length > 0 ? (
            <HubAIStatements statements={content.statements ?? []} />
          ) : (
            result?.status === "ok" && (
              <p className="text-body-xs-regular text-tertiary">{t("project_hub.ai.no_statements")}</p>
            )
          )}
          <HubAIFindings flags={result?.flags} notes={result?.notes} />
          {typeof content.snapshot === "string" && content.snapshot && (
            <SnapshotDisclosure snapshot={content.snapshot} />
          )}
          <HubAISources context={content.context} retrieved={content.retrieved} />
          <HubAIModelLine provider={result?.provider} model={result?.model} />
        </div>
      )}
    </section>
  );
});
