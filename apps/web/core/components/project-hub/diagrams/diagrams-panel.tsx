/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import type { TPHDiagramDocument } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubSection } from "../common/section";
import { HubEmpty, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { ToneBadge } from "../common/tone-badge";
import { useHubResource } from "../common/use-hub-resource";
import { DiagramEditor } from "./diagram-editor";

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** When set, only diagrams of this work package are listed and new ones are attached to it. */
  issueId?: string;
  readOnly?: boolean;
  headingLevel?: "h2" | "h3";
};

/** S08 entry point: list of structured diagrams, create dialog, and the editor for the selected one. */
export const DiagramsPanel = observer(function DiagramsPanel({
  workspaceSlug,
  projectId,
  issueId,
  readOnly,
  headingLevel = "h3",
}: Props) {
  const { t } = useTranslation();
  const store = useProjectHub();
  const { has } = useProjectHubCapabilities(workspaceSlug, projectId);
  const canEdit = has("package.edit") && !readOnly;
  const listKey = issueId
    ? `${PH_KEYS.diagrams(workspaceSlug, projectId)}:${issueId}`
    : PH_KEYS.diagrams(workspaceSlug, projectId);
  const diagrams = useHubResource<TPHDiagramDocument[]>(listKey, () =>
    store.knowledgeService.listDiagrams(workspaceSlug, projectId, issueId)
  );
  const [openId, setOpenId] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const created = await store.knowledgeService.createDiagram(workspaceSlug, projectId, {
        name: name.trim(),
        ...(issueId ? { issue_id: issueId } : {}),
        semantic: { nodes: [], edges: [] },
        layout: {},
      });
      setIsOpen(false);
      setName("");
      store.invalidate(PH_KEYS.diagrams(workspaceSlug, projectId));
      setOpenId(created.id);
    } catch (error) {
      showHubErrorToast(t, error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <HubSection
      as={headingLevel}
      title={t("project_hub.diagram.title")}
      description={t("project_hub.diagram.description")}
      actions={
        canEdit && (
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t("project_hub.diagram.create")}
            onClick={() => setIsOpen(true)}
          />
        )
      }
    >
      <HubResourceBoundary
        resource={diagrams}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={<HubEmpty title={t("project_hub.diagram.empty")} />}
      >
        {(data) => (
          <ul className="flex flex-col divide-y divide-subtle rounded-md border border-subtle">
            {data.map((d) => {
              const isCurrent = openId === d.id;
              return (
                <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="text-body-xs-medium text-primary">{d.name}</span>
                    <ToneBadge
                      tone="neutral"
                      size="xs"
                      label={t("project_hub.diagram.counts", {
                        nodes: d.semantic?.nodes?.length ?? 0,
                        edges: d.semantic?.edges?.length ?? 0,
                      })}
                    />
                    {!issueId && !d.issue_id && (
                      <span className="text-caption-sm-regular text-tertiary">{t("project_hub.diagram.unlinked")}</span>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    stretch="auto"
                    aria-expanded={isCurrent}
                    label={isCurrent ? t("project_hub.diagram.close") : t("project_hub.diagram.open")}
                    onClick={() => setOpenId(isCurrent ? null : d.id)}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </HubResourceBoundary>
      {openId && (
        <div className="@container">
          <DiagramEditor key={openId} workspaceSlug={workspaceSlug} projectId={projectId} diagramId={openId} />
        </div>
      )}
      <HubDialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        isBusy={busy}
        title={t("project_hub.diagram.create")}
        onSubmit={() => void handleCreate()}
        actions={
          <>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("project_hub.common.cancel")}
              onClick={() => setIsOpen(false)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              disabled={!name.trim()}
              loading={busy}
              label={t("project_hub.diagram.create")}
            />
          </>
        }
      >
        <HubTextField label={t("project_hub.diagram.name")} value={name} onChange={setName} required />
      </HubDialog>
    </HubSection>
  );
});
