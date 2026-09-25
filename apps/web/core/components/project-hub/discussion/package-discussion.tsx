/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import type { TPHConversation } from "@plane/types";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";
import { PH_KEYS } from "@/store/project-hub";
// local imports
import { HubResourceBoundary } from "../common/states";
import { useHubResource } from "../common/use-hub-resource";
import { ConversationView } from "./conversation-view";

/** Package thread (get-or-create per issue on the server — one thread per package, FR-C01). */
export const PackageDiscussion = observer(function PackageDiscussion({
  workspaceSlug,
  projectId,
  issueId,
}: {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
}) {
  const store = useProjectHub();
  const thread = useHubResource<TPHConversation>(PH_KEYS.thread(issueId), () =>
    store.collaborationService.getPackageThread(workspaceSlug, projectId, issueId)
  );
  return (
    <HubResourceBoundary resource={thread} loadingRows={3}>
      {(conversation) => (
        <ConversationView workspaceSlug={workspaceSlug} conversation={conversation} issueId={issueId} />
      )}
    </HubResourceBoundary>
  );
});
