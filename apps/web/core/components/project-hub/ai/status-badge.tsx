/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { observer } from "mobx-react";
// plane imports
import { AiStarOneOutline, SettingsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHAIStatus } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/** Which AI is active for the workspace (cached once per workspace; never contains secrets). */
export const useHubAIStatus = (workspaceSlug: string) => {
  const store = useProjectHub();
  return useHubResource<TPHAIStatus>(PH_KEYS.aiStatus(workspaceSlug), () => store.aiService.getStatus(workspaceSlug));
};

/**
 * Small badge: "OpenAI · gpt-4o-mini" when a model is configured, otherwise
 * "Rule-based (no model configured)". Renders nothing while loading or when the status is unavailable.
 */
export const HubAIStatusBadge = observer(function HubAIStatusBadge({
  workspaceSlug,
  size = "xs",
}: {
  workspaceSlug: string;
  size?: "xs" | "sm";
}) {
  const { t } = useTranslation();
  const status = useHubAIStatus(workspaceSlug);
  const data = status.data;
  if (!data) return null;
  if (data.mode === "llm") {
    const label = t("project_hub.ai.status.llm", { provider: data.provider_label || data.provider, model: data.model });
    return (
      <ToneBadge
        tone="brand"
        size={size}
        icon={AiStarOneOutline as TGlyph}
        label={label}
        title={
          data.embeddings && data.embedding_model
            ? `${label} · ${t("project_hub.ai.status.embeddings", { model: data.embedding_model })}`
            : label
        }
      />
    );
  }
  return (
    <ToneBadge
      tone="neutral"
      size={size}
      icon={SettingsOutline as TGlyph}
      label={t("project_hub.ai.status.rule_based")}
      title={t("project_hub.ai.status.rule_based_hint")}
    />
  );
});
