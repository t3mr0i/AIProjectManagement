/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// components
import { PageHead } from "@/components/core/page-title";
// local imports
import { ProjectHubGate } from "./gate";
import { HubErrorState, HubLoading } from "./states";

type Props = {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

/** Standard page body for Project Hub pages (same surface/spacing as native list pages). */
export function HubPage({ title, description, actions, children, className }: Props) {
  return (
    <div className="size-full overflow-y-auto">
      <PageHead title={title} />
      <main className={cn("mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-5 md:px-6", className)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="text-h5-semibold text-primary">{title}</h1>
            {description && <p className="text-body-xs-regular text-tertiary">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
        {children}
      </main>
    </div>
  );
}

/** Page-level feature gate: disabled extension renders the designed "disabled" state, not a 404. */
export const HubPageGate = observer(function HubPageGate({
  workspaceSlug,
  projectId,
  children,
}: {
  workspaceSlug: string;
  projectId?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <ProjectHubGate
      workspaceSlug={workspaceSlug}
      projectId={projectId}
      loading={
        <div className="p-6">
          <HubLoading rows={4} />
        </div>
      }
      fallback={
        <div className="mx-auto max-w-2xl p-6">
          <PageHead title={t("project_hub.name")} />
          <HubErrorState error={{ status: 403, code: "EXTENSION_DISABLED", error: "" }} />
        </div>
      }
    >
      {children}
    </ProjectHubGate>
  );
});
