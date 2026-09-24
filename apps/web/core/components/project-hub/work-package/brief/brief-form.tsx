/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { AddOutline, CloseOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type {
  TPackageCriterion,
  TPackageProfile,
  TPackageProfileKind,
  TPackageRisk,
  TPackageType,
  TProjectHubApiError,
} from "@plane/types";
import { cn, getProjectHubErrorKind, toProjectHubApiError } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubTextAreaField, HubTextField } from "../../common/field";
import { HubSelect } from "../../common/select";
import { HubConflictBanner } from "../../common/states";
import { showHubErrorToast, showHubSuccessToast } from "../../common/toast";
import type { TWorkPackageScope } from "../types";

type TDraft = {
  profile_kind: TPackageProfileKind;
  package_type: TPackageType;
  intent: string;
  outcome: string;
  non_goals: string;
  scope_summary: string;
  touches_permissions: boolean;
  criteria: TPackageCriterion[];
  risk: TPackageRisk;
};

const toDraft = (profile: TPackageProfile): TDraft => ({
  profile_kind: profile.profile_kind,
  package_type: profile.package_type,
  intent: profile.intent ?? "",
  outcome: profile.outcome ?? "",
  non_goals: (profile.non_goals ?? []).join("\n"),
  scope_summary: typeof profile.scope?.summary === "string" ? profile.scope.summary : "",
  touches_permissions: !!profile.scope?.touches_permissions,
  criteria: profile.criteria ?? [],
  risk: profile.risk ?? {},
});

const newCriterionId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `c-${Date.now()}-${Math.random()}`;

type Props = TWorkPackageScope & { profile: TPackageProfile; canEdit: boolean };

/** Working draft editor (S04). Saving never approves anything. */
export const BriefForm = observer(function BriefForm({ workspaceSlug, projectId, issueId, profile, canEdit }: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const [draft, setDraft] = useState<TDraft>(() => toDraft(profile));
  // Draft as it was at `baseVersion` — used to detect local edits.
  const [baseDraft, setBaseDraft] = useState<TDraft>(() => toDraft(profile));
  const [baseVersion, setBaseVersion] = useState(profile.version);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<TProjectHubApiError | null>(null);
  const [remoteChanged, setRemoteChanged] = useState(false);

  const isDirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(baseDraft), [draft, baseDraft]);

  const adopt = (next: TPackageProfile) => {
    const nextDraft = toDraft(next);
    setDraft(nextDraft);
    setBaseDraft(nextDraft);
    setBaseVersion(next.version);
    setRemoteChanged(false);
  };

  // A newer server version: adopt it when there are no local edits; otherwise never overwrite the
  // user's text silently — show the conflict state instead.
  useEffect(() => {
    if (isSaving || profile.version === baseVersion) return;
    if (!isDirty) adopt(profile);
    else setRemoteChanged(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.version, isSaving]);

  const update = <K extends keyof TDraft>(key: K, value: TDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await store.updateProfile(workspaceSlug, projectId, issueId, {
        expected_version: baseVersion,
        profile_kind: draft.profile_kind,
        package_type: draft.package_type,
        intent: draft.intent,
        outcome: draft.outcome,
        non_goals: draft.non_goals
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
        scope: { ...profile.scope, summary: draft.scope_summary, touches_permissions: draft.touches_permissions },
        criteria: draft.criteria.filter((c) => c.text.trim().length > 0),
        risk: draft.profile_kind === "deep" ? draft.risk : profile.risk,
      });
      adopt(updated);
      showHubSuccessToast(t("project_hub.brief.draft_saved"));
    } catch (error) {
      const err = toProjectHubApiError(error);
      setSaveError(err);
      if (getProjectHubErrorKind(err) !== "conflict") showHubErrorToast(t, err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReloadLatest = () => {
    setSaveError(null);
    // Discard local edits and adopt the current server state (refetched in the background).
    adopt(profile);
    store.invalidate(PH_KEYS.profile(issueId));
  };

  const readOnly = !canEdit;
  const kindOptions: { value: TPackageProfileKind; label: string }[] = [
    { value: "light", label: t("project_hub.brief.light") },
    { value: "deep", label: t("project_hub.brief.deep") },
  ];

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!readOnly) void handleSave();
      }}
      aria-describedby={readOnly ? `brief-readonly-${issueId}` : undefined}
    >
      {readOnly && (
        <p id={`brief-readonly-${issueId}`} className="text-body-xs-regular text-tertiary">
          {t("project_hub.brief.readonly")}
        </p>
      )}
      {((saveError && getProjectHubErrorKind(saveError) === "conflict") || remoteChanged) && (
        <HubConflictBanner
          onReload={handleReloadLatest}
          onDismiss={() => {
            setSaveError(null);
            setRemoteChanged(false);
          }}
        />
      )}

      <div className="flex flex-wrap items-end gap-4">
        <fieldset className="flex flex-col gap-1">
          <legend className="text-caption-md-medium text-tertiary">{t("project_hub.brief.profile_kind")}</legend>
          <div className="flex gap-1" role="group">
            {kindOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={draft.profile_kind === option.value}
                disabled={readOnly}
                onClick={() => update("profile_kind", option.value)}
                className={cn(
                  "focus-visible:outline-accent-primary rounded-md border px-2.5 py-1 text-body-xs-medium focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed",
                  draft.profile_kind === option.value
                    ? "border-accent-strong bg-accent-subtle text-accent-primary"
                    : "border-subtle text-secondary hover:bg-layer-1"
                )}
              >
                {draft.profile_kind === option.value ? "✓ " : ""}
                {option.label}
              </button>
            ))}
          </div>
          <span className="text-caption-sm-regular text-tertiary">{t("project_hub.brief.profile_kind_help")}</span>
        </fieldset>
        <div className="min-w-40">
          <HubSelect
            label={t("project_hub.brief.package_type")}
            value={draft.package_type}
            disabled={readOnly}
            onChange={(v) => update("package_type", v as TPackageType)}
            options={(["code", "analysis", "design", "decision"] as TPackageType[]).map((v) => ({
              value: v,
              label: t(`project_hub.brief.package_types.${v}`),
            }))}
          />
        </div>
      </div>

      <HubTextAreaField
        label={t("project_hub.brief.intent")}
        placeholder={t("project_hub.brief.intent_placeholder")}
        value={draft.intent}
        disabled={readOnly}
        onChange={(v) => update("intent", v)}
      />
      <HubTextAreaField
        label={t("project_hub.brief.outcome")}
        placeholder={t("project_hub.brief.outcome_placeholder")}
        value={draft.outcome}
        disabled={readOnly}
        onChange={(v) => update("outcome", v)}
      />
      <HubTextAreaField
        label={t("project_hub.brief.non_goals")}
        placeholder={t("project_hub.brief.non_goals_placeholder")}
        value={draft.non_goals}
        disabled={readOnly}
        onChange={(v) => update("non_goals", v)}
      />
      <HubTextAreaField
        label={t("project_hub.brief.scope")}
        placeholder={t("project_hub.brief.scope_placeholder")}
        value={draft.scope_summary}
        disabled={readOnly}
        onChange={(v) => update("scope_summary", v)}
      />
      <label className="flex items-start gap-2 text-body-xs-regular text-secondary">
        <Checkbox
          checked={draft.touches_permissions}
          disabled={readOnly}
          onCheckedChange={(checked) => update("touches_permissions", !!checked)}
        />
        <span className="flex flex-col">
          <span>{t("project_hub.brief.permission_scope")}</span>
          {draft.touches_permissions && (
            <span className="text-caption-sm-regular text-tertiary">
              {t("project_hub.brief.permission_scope_help")}
            </span>
          )}
        </span>
      </label>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-caption-md-medium text-tertiary">{t("project_hub.brief.criteria")}</legend>
        <ol className="flex flex-col gap-2">
          {draft.criteria.map((criterion, index) => (
            <li key={criterion.id} className="flex items-start gap-2">
              <span className="pt-2 text-caption-sm-regular text-tertiary" aria-hidden="true">
                {index + 1}.
              </span>
              <div className="flex-1">
                <HubTextField
                  label={t("project_hub.brief.criterion_label", { index: index + 1 })}
                  hideLabel
                  placeholder={t("project_hub.brief.criteria_placeholder")}
                  value={criterion.text}
                  disabled={readOnly}
                  onChange={(v) =>
                    update(
                      "criteria",
                      draft.criteria.map((c) => (c.id === criterion.id ? { ...c, text: v } : c))
                    )
                  }
                />
              </div>
              {!readOnly && (
                <IconButton
                  variant="ghost"
                  size="md"
                  icon={<Icon icon={CloseOutline} />}
                  aria-label={t("project_hub.brief.remove_criterion", { index: index + 1 })}
                  onClick={() =>
                    update(
                      "criteria",
                      draft.criteria.filter((c) => c.id !== criterion.id)
                    )
                  }
                />
              )}
            </li>
          ))}
        </ol>
        {!readOnly && (
          <div>
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              icon={<AddOutline className="size-3.5" />}
              label={t("project_hub.brief.add_criterion")}
              onClick={() => update("criteria", [...draft.criteria, { id: newCriterionId(), text: "" }])}
            />
          </div>
        )}
      </fieldset>

      {draft.profile_kind === "deep" && (
        <fieldset className="flex flex-col gap-3 rounded-md border border-subtle p-3">
          <legend className="px-1 text-caption-md-medium text-tertiary">{t("project_hub.brief.risk")}</legend>
          <div className="max-w-48">
            <HubSelect
              label={t("project_hub.brief.risk_level")}
              value={draft.risk.level ?? null}
              disabled={readOnly}
              onChange={(v) => update("risk", { ...draft.risk, level: v as TPackageRisk["level"] })}
              options={(["low", "medium", "high"] as const).map((v) => ({
                value: v,
                label: t(`project_hub.brief.risk_levels.${v}`),
              }))}
            />
          </div>
          <HubTextAreaField
            label={t("project_hub.brief.risk_description")}
            value={draft.risk.description ?? ""}
            disabled={readOnly}
            onChange={(v) => update("risk", { ...draft.risk, description: v })}
          />
          <HubTextAreaField
            label={t("project_hub.brief.risk_mitigation")}
            value={draft.risk.mitigation ?? ""}
            disabled={readOnly}
            onChange={(v) => update("risk", { ...draft.risk, mitigation: v })}
          />
          <HubTextAreaField
            label={t("project_hub.brief.risk_rollback")}
            value={draft.risk.rollback ?? ""}
            disabled={readOnly}
            onChange={(v) => update("risk", { ...draft.risk, rollback: v })}
          />
        </fieldset>
      )}

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            variant="secondary"
            size="sm"
            stretch="auto"
            loading={isSaving}
            disabled={!isDirty || isSaving}
            label={isSaving ? t("project_hub.common.saving") : t("project_hub.brief.save_draft")}
          />
          <span className="text-caption-sm-regular text-tertiary" aria-live="polite">
            {isDirty
              ? t("project_hub.brief.unsaved_changes")
              : t("project_hub.brief.version", { version: profile.version })}
          </span>
        </div>
      )}
    </form>
  );
});
