/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { BriefsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { useProjectHubCapabilities } from "../common/gate";
import { showHubErrorToast, showHubSuccessToast } from "../common/toast";
import type { TWorkPackageScope } from "./types";

/** Compact, optional activation — never forced; normal issues stay normal (FR-B02). */
export const ActivateWorkPackage = observer(function ActivateWorkPackage({
  workspaceSlug,
  projectId,
  issueId,
  readOnly,
}: TWorkPackageScope) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const canEdit = has("package.edit") && !readOnly;

  const handleActivate = async () => {
    setIsSubmitting(true);
    try {
      await store.activateProfile(workspaceSlug, projectId, issueId);
      showHubSuccessToast(t("project_hub.work_package.activated"));
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-md border border-dashed border-subtle px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-2">
        <Icon icon={BriefsOutline} size="md" tint="tertiary" />
        <div className="flex flex-col gap-0.5">
          <p className="text-body-sm-medium text-secondary">{t("project_hub.work_package.activate_title")}</p>
          <p className="text-body-xs-regular text-tertiary">{t("project_hub.work_package.activate_description")}</p>
        </div>
      </div>
      {canEdit && (
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          loading={isSubmitting}
          label={isSubmitting ? t("project_hub.work_package.activating") : t("project_hub.work_package.activate")}
          onClick={() => void handleActivate()}
        />
      )}
    </div>
  );
});
