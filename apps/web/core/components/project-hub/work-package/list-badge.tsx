/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
// local imports
import { PackagePhaseIndicator } from "../common/phase-indicator";

type Props = { projectId: string | null | undefined; issueId: string };

/**
 * Small phase badge for native list/kanban rows. Uses one cached package listing per project
 * (no request per row); rows without a profile render nothing, so the native list is unchanged.
 */
export const WorkPackageListBadge = observer(function WorkPackageListBadge({ projectId, issueId }: Props) {
  const { workspaceSlug } = useParams();
  const store = useProjectHub();
  const slug = workspaceSlug?.toString();
  const enabled = !!slug && !!projectId && store.isEnabled(slug, projectId);

  useEffect(() => {
    if (!slug || !projectId) return;
    if (store.getCapabilities(slug, projectId) === undefined) void store.fetchCapabilities(slug, projectId);
  }, [slug, projectId, store]);

  useEffect(() => {
    if (enabled && slug && projectId) store.ensureProjectRows(slug, projectId);
  }, [enabled, slug, projectId, store]);

  if (!enabled || !slug || !projectId) return null;
  const row = store.getRowForIssue(slug, projectId, issueId);
  if (!row) return null;
  return <PackagePhaseIndicator status={row} variant="compact" className="h-5 shrink-0" />;
});
