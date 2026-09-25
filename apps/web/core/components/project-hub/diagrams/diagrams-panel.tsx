/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { UnlinkOutline, WorkflowsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TPHDiagramDocument } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubChip } from "../common/chip";
import { HubDialog } from "../common/dialog";
import { HubTextField } from "../common/field";
import { useProjectHubCapabilities } from "../common/gate";
import { HubList, HubListRow } from "../common/list";
import { HubSection } from "../common/section";
import { HubEmptyState, HubResourceBoundary } from "../common/states";
import { showHubErrorToast } from "../common/toast";
import { useHubResource } from "../common/use-hub-resource";
import { DiagramEditor } from "./diagram-editor";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

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

  const createAction = canEdit && (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      label={t("project_hub.diagram.create")}
      onClick={() => setIsOpen(true)}
    />
  );

  return (
    <HubSection
      as={headingLevel}
      title={t("project_hub.diagram.title")}
      description={t("project_hub.diagram.description")}
      actions={createAction}
    >
      <HubResourceBoundary
        resource={diagrams}
        loadingRows={2}
        isEmpty={(d) => d.length === 0}
        empty={
          <HubEmptyState
            icon={WorkflowsOutline as TGlyph}
            title={t("project_hub.diagram.empty")}
            action={
              canEdit ? (
                <Button
                  variant="tertiary"
                  size="sm"
                  stretch="auto"
                  label={t("project_hub.diagram.create")}
                  onClick={() => setIsOpen(true)}
                />
              ) : undefined
            }
          />
        }
      >
        {(data) => (
          <HubList variant="card" aria-label={t("project_hub.diagram.title")}>
            {data.map((d) => {
              const isCurrent = openId === d.id;
              return (
                <HubListRow
                  key={d.id}
                  icon={WorkflowsOutline as TGlyph}
                  title={d.name}
                  selected={isCurrent}
                  onClick={() => setOpenId(isCurrent ? null : d.id)}
                  aria-label={`${d.name}: ${isCurrent ? t("project_hub.diagram.close") : t("project_hub.diagram.open")}`}
                  meta={
                    <>
                      <span className="text-caption-md-regular text-tertiary">
                        {t("project_hub.diagram.counts", {
                          nodes: d.semantic?.nodes?.length ?? 0,
                          edges: d.semantic?.edges?.length ?? 0,
                        })}
                      </span>
                      {!issueId && !d.issue_id && (
                        <HubChip
                          variant="soft"
                          icon={UnlinkOutline as TGlyph}
                          label={t("project_hub.diagram.unlinked")}
                        />
                      )}
                    </>
                  }
                  trailing={
                    <span className="text-caption-md-regular text-tertiary">
                      {isCurrent ? t("project_hub.diagram.close") : t("project_hub.diagram.open")}
                    </span>
                  }
                />
              );
            })}
          </HubList>
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
