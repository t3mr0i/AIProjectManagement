/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { TextArea } from "@makeplane/propel/components/text-area";
import { AiStarOneOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHAskResponse } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { showHubErrorToast } from "../common/toast";
import { HubAIFindings, HubAIModelLine, HubAIResultNotice, HubAISources, HubAIStatements } from "./result";
import { HubAIStatusBadge } from "./status-badge";

/**
 * Workspace "Ask AI": a private question across every project the viewer can read. The answer
 * shows each statement with its status and exactly which sources were used or blocked (and why).
 */
export const HubAskAIPanel = observer(function HubAskAIPanel({
  workspaceSlug,
  className,
}: {
  workspaceSlug: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const inputId = useId();
  const headingId = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<TPHAskResponse | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const submit = async () => {
    const q = question.trim();
    if (!q || isBusy) return;
    setIsBusy(true);
    try {
      setAnswer(await store.aiService.ask(workspaceSlug, { question: q }));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsBusy(false);
    }
  };

  const result = answer?.result;

  return (
    <section aria-labelledby={headingId} className={cn("flex min-w-0 flex-col gap-3", className)}>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-center gap-2">
          <AiStarOneOutline className="size-4 shrink-0 text-accent-primary" aria-hidden="true" />
          <h2 id={headingId} className="truncate text-13 font-medium text-primary">
            {t("project_hub.ai.ask.title")}
          </h2>
        </div>
        <HubAIStatusBadge workspaceSlug={workspaceSlug} />
      </div>
      <p className="-mt-2 text-caption-md-regular text-tertiary">{t("project_hub.ai.ask.description")}</p>
      <form
        className="flex min-w-0 flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          {t("project_hub.ai.ask.label")}
        </label>
        <TextArea
          id={inputId}
          size="md"
          surface="field"
          autoResize
          maxRows={8}
          value={question}
          placeholder={t("project_hub.ai.ask.placeholder")}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            stretch="auto"
            icon={<Icon icon={AiStarOneOutline} />}
            loading={isBusy}
            disabled={!question.trim()}
            label={t("project_hub.ai.ask.submit")}
          />
          {answer && (
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              disabled={isBusy}
              label={t("project_hub.ai.ask.clear")}
              onClick={() => {
                setAnswer(null);
                setQuestion("");
              }}
            />
          )}
          <span className="hidden text-caption-sm-regular text-placeholder sm:inline">
            {t("project_hub.ai.ask.shortcut")}
          </span>
        </div>
      </form>

      {answer && result && (
        <div aria-live="polite" className="flex min-w-0 flex-col gap-3 rounded-md border border-subtle bg-layer-1 p-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="text-caption-md-medium text-tertiary">{t("project_hub.ai.ask.answer")}</p>
            <p className="truncate text-caption-md-regular text-secondary" title={answer.question}>
              {answer.question}
            </p>
          </div>
          <HubAIResultNotice result={result} />
          {result.statements.length > 0 ? (
            <HubAIStatements statements={result.statements} />
          ) : (
            result.status === "ok" && (
              <p className="text-body-xs-regular text-tertiary">{t("project_hub.ai.no_statements")}</p>
            )
          )}
          <HubAIFindings flags={result.flags} notes={result.notes} />
          <HubAISources context={answer.context} retrieved={answer.retrieved} />
          <HubAIModelLine provider={result.provider} model={result.model} />
        </div>
      )}
    </section>
  );
});
