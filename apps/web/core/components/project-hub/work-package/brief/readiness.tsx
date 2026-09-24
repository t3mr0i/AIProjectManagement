/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { CircleDashedOutline, TickCircleOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPackageReadiness } from "@plane/types";
// local imports
import { HubSection } from "../../common/section";
import { HubResourceBoundary } from "../../common/states";
import { ToneBadge } from "../../common/tone-badge";
import type { THubResource } from "../../common/use-hub-resource";

/** Readiness checklist with explanations (FR-W, S04). Server is the source of truth. */
export const ReadinessPanel = observer(function ReadinessPanel({
  readiness,
}: {
  readiness: THubResource<TPackageReadiness>;
}) {
  const { t } = useTranslation();
  return (
    <HubSection
      title={t("project_hub.readiness.title")}
      actions={
        readiness.data && (
          <ToneBadge
            tone={readiness.data.ready ? "success" : "warning"}
            label={readiness.data.ready ? t("project_hub.readiness.ready") : t("project_hub.readiness.not_ready")}
          />
        )
      }
    >
      <HubResourceBoundary resource={readiness} loadingRows={2}>
        {(data) => (
          <div className="flex flex-col gap-3">
            {data.missing.length === 0 && data.policies.length === 0 && (
              <p className="flex items-center gap-2 text-body-xs-regular text-secondary">
                <Icon icon={TickCircleOutline} />
                {t("project_hub.readiness.all_good")}
              </p>
            )}
            {data.missing.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-caption-md-medium text-tertiary">{t("project_hub.readiness.missing")}</p>
                <ul className="flex flex-col gap-1">
                  {data.missing.map((item) => (
                    <li key={item.field} className="flex items-start gap-2 text-body-xs-regular text-secondary">
                      <Icon icon={CircleDashedOutline} tint="tertiary" />
                      <span>
                        <span className="font-medium text-primary">{item.field}</span> — {item.message}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.policies.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-caption-md-medium text-tertiary">{t("project_hub.readiness.policies")}</p>
                <ul className="flex flex-col gap-1">
                  {data.policies.map((policy) => (
                    <li key={policy.id} className="flex items-start gap-2 text-body-xs-regular text-secondary">
                      <Icon icon={CircleDashedOutline} tint="tertiary" />
                      <span>{policy.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </HubResourceBoundary>
    </HubSection>
  );
});
