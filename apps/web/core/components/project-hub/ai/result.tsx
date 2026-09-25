/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
// plane imports
import {
  FlagOutline,
  LockOutline,
  SearchOutline,
  TickCircleOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHAIContext, TPHAIFlag, TPHAIResult, TPHAIRetrievedRef, TPHSourceRef } from "@plane/types";
import type { TProjectHubTone } from "@plane/utils";
import { cn } from "@plane/utils";
// local imports
import { HubChip } from "../common/chip";
import { HubNotice } from "../common/states";
import { ToneBadge } from "../common/tone-badge";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

const STATEMENT_STATUSES = new Set<string>(["observed", "confirmed", "inferred", "proposed"]);
const STATEMENT_TONE: Record<string, TProjectHubTone> = {
  observed: "info",
  confirmed: "success",
  inferred: "warning",
  proposed: "brand",
};

const RESULT_STATUSES = new Set<string>(["ok", "timeout", "budget_exceeded", "cancelled", "error", "unavailable"]);

const BLOCK_REASONS = new Set<string>([
  "unavailable",
  "private_source",
  "audience_mismatch",
  "quarantined",
  "scan_pending",
]);

const KNOWN_FLAGS = new Set<string>([
  "unverified_claim",
  "missing_evidence",
  "contradiction",
  "unknown_intent",
  "scope_change_requires_new_approval",
  "instruction_like_content",
]);

export const sourceRefLabel = (ref: TPHSourceRef, title?: string | null) =>
  title || `${ref.type}:${String(ref.id).slice(0, 8)}`;

type TStatementLike = { text: string; status?: string; kind?: string; sources?: unknown[] };

/** Observed / confirmed / inferred / proposed (PRD §14.2) — icon + text, never colour alone. */
export function HubAIStatementBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const known = STATEMENT_STATUSES.has(status);
  return (
    <ToneBadge
      tone={STATEMENT_TONE[status] ?? "neutral"}
      size="xs"
      label={known ? t(`project_hub.proposals.statement.${status}`) : status}
    />
  );
}

/** AI statements, each with its status badge; the number of cited sources is shown quietly. */
export function HubAIStatements({ statements, className }: { statements: TStatementLike[]; className?: string }) {
  const { t } = useTranslation();
  if (statements.length === 0) return null;
  return (
    <ul className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      {statements.map((statement, i) => {
        const status = statement.status ?? statement.kind;
        const sourceCount = statement.sources?.length ?? 0;
        return (
          // oxlint-disable-next-line react/no-array-index-key -- statements have no id
          <li key={i} className="flex min-w-0 items-start gap-2 text-body-xs-regular text-secondary">
            {status && (
              <span className="shrink-0 pt-px">
                <HubAIStatementBadge status={status} />
              </span>
            )}
            <span className="min-w-0 break-words whitespace-pre-wrap text-primary">
              {statement.text}
              {sourceCount > 0 && (
                <span className="ml-1.5 text-caption-sm-regular text-tertiary">
                  {t("project_hub.ai.statement_sources", { count: sourceCount })}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Failure (timeout, budget, provider error…) or clarification notice for an AI result. */
export function HubAIResultNotice({ result }: { result?: Partial<TPHAIResult> | null }) {
  const { t } = useTranslation();
  if (!result) return null;
  const status = result.status;
  if (status && status !== "ok") {
    const label = RESULT_STATUSES.has(status) ? t(`project_hub.ai.result_status.${status}`) : status;
    return (
      <HubNotice
        role="alert"
        tone="warning"
        icon={WarningTriangleOutline as TGlyph}
        title={t("project_hub.ai.result_failed", { status: label })}
        description={result.error || result.error_code || undefined}
      />
    );
  }
  if (result.needs_clarification)
    return (
      <HubNotice
        tone="warning"
        icon={WarningTriangleOutline as TGlyph}
        title={t("project_hub.ai.needs_clarification")}
      />
    );
  return null;
}

const flagDetail = (flag: TPHAIFlag): string | undefined => {
  for (const key of ["text", "detail", "reason", "message", "statement"]) {
    const value = flag[key];
    if (typeof value === "string" && value) return value;
  }
  return undefined;
};

/** Structured findings (flags) and free-form notes of an AI result. */
export function HubAIFindings({ flags = [], notes = [] }: { flags?: TPHAIFlag[]; notes?: string[] }) {
  const { t } = useTranslation();
  if (flags.length === 0 && notes.length === 0) return null;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {flags.length > 0 && (
        <ul className="flex min-w-0 flex-col gap-1" aria-label={t("project_hub.ai.flags_title")}>
          {flags.map((flag, i) => {
            const detail = flagDetail(flag);
            return (
              // oxlint-disable-next-line react/no-array-index-key -- flags have no id
              <li key={i} className="flex min-w-0 items-start gap-2 text-caption-md-regular text-secondary">
                <FlagOutline className="mt-0.5 size-3 shrink-0 text-warning-primary" aria-hidden="true" />
                <span className="min-w-0 break-words">
                  <span className="font-medium text-primary">
                    {KNOWN_FLAGS.has(flag.kind) ? t(`project_hub.ai.flag.${flag.kind}`) : flag.kind}
                  </span>
                  {detail && <span className="text-tertiary"> · {detail}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {notes.length > 0 && (
        <div className="flex min-w-0 flex-col">
          <p className="text-caption-md-medium text-tertiary">{t("project_hub.ai.notes_title")}</p>
          <ul className="list-inside list-disc text-caption-md-regular text-secondary">
            {notes.map((note) => (
              <li key={note} className="break-words">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** One muted line: "Generated by OpenAI · gpt-4o-mini" (or rule-based). */
export function HubAIModelLine({
  provider,
  model,
  className,
}: {
  provider?: string;
  model?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const name = [provider, model].filter(Boolean).join(" · ");
  return (
    <p className={cn("truncate text-caption-sm-regular text-tertiary", className)}>
      {name ? t("project_hub.ai.generated_by", { model: name }) : t("project_hub.ai.status.rule_based")}
    </p>
  );
}

/** Sources the AI used (allowed), found by semantic search (retrieved) and blocked ones with reasons. */
export function HubAISources({
  context,
  retrieved = [],
  className,
}: {
  context?: Partial<TPHAIContext> | null;
  retrieved?: TPHAIRetrievedRef[];
  className?: string;
}) {
  const { t } = useTranslation();
  const allowed = context?.allowed ?? [];
  const blocked = context?.blocked ?? [];
  const retrievedKeys = new Set(retrieved.map((r) => `${r.type}:${r.id}`));
  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)}>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-caption-md-medium text-tertiary">{t("project_hub.ai.sources_used")}</p>
        {allowed.length === 0 ? (
          <p className="text-caption-md-regular text-placeholder">{t("project_hub.ai.no_sources")}</p>
        ) : (
          <ul className="flex min-w-0 flex-wrap gap-1">
            {allowed.map((source) => {
              const found = retrievedKeys.has(`${source.ref.type}:${source.ref.id}`);
              return (
                <li key={`${source.ref.type}:${source.ref.id}`} className="min-w-0">
                  <HubChip
                    variant="soft"
                    icon={(found ? SearchOutline : TickCircleOutline) as TGlyph}
                    label={sourceRefLabel(source.ref, source.title)}
                    title={[
                      `${source.ref.type}:${source.ref.id}`,
                      found ? t("project_hub.ai.sources_retrieved") : "",
                      source.confirmed ? t("project_hub.proposals.statement.confirmed") : "",
                      source.stale ? t("project_hub.ai.source_stale") : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    trailing={
                      source.stale ? (
                        <span className="text-caption-sm-regular text-warning-primary">
                          {t("project_hub.ai.source_stale")}
                        </span>
                      ) : undefined
                    }
                  />
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {blocked.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-caption-md-medium text-tertiary">
            {t("project_hub.ai.sources_blocked", { count: blocked.length })}
          </p>
          <ul className="flex min-w-0 flex-col gap-0.5">
            {blocked.map((source) => (
              <li
                key={`${source.ref.type}:${source.ref.id}`}
                className="flex min-w-0 items-center gap-1.5 text-caption-md-regular text-secondary"
              >
                <LockOutline className="size-3 shrink-0 text-tertiary" aria-hidden="true" />
                <span className="truncate">{sourceRefLabel(source.ref)}</span>
                <span className="truncate text-tertiary">
                  ·{" "}
                  {BLOCK_REASONS.has(source.reason) ? t(`project_hub.ai.block_reason.${source.reason}`) : source.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
