/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TPHClarifyStep,
  TPHContextPreview,
  TPHContextPreviewRequest,
  TPHConversation,
  TPHConversationCreate,
  TPHDecision,
  TPHDecisionCreate,
  TPHDecisionPreview,
  TPHDecisionPreviewRequest,
  TPHMessage,
  TPHNotificationItem,
  TPHProposal,
} from "@plane/types";
import { ProjectHubBaseService, projectHubProjectPath, projectHubWorkspacePath } from "./base.service";

/** Conversations, messages, decisions, clarification, AI proposals, notifications (API §5). */
export class ProjectHubCollaborationService extends ProjectHubBaseService {
  listConversations(workspaceSlug: string) {
    return this.getJson<TPHConversation[]>(`${projectHubWorkspacePath(workspaceSlug)}/conversations/`);
  }

  /** Package threads are get-or-create per issue on the server. */
  createConversation(workspaceSlug: string, data: TPHConversationCreate) {
    return this.postJson<TPHConversation>(`${projectHubWorkspacePath(workspaceSlug)}/conversations/`, data);
  }

  getConversation(workspaceSlug: string, conversationId: string) {
    return this.getJson<TPHConversation>(`${projectHubWorkspacePath(workspaceSlug)}/conversations/${conversationId}/`);
  }

  listMessages(workspaceSlug: string, conversationId: string) {
    return this.getJson<TPHMessage[]>(
      `${projectHubWorkspacePath(workspaceSlug)}/conversations/${conversationId}/messages/`
    );
  }

  postMessage(workspaceSlug: string, conversationId: string, data: { body: string; parent_id?: string }) {
    return this.postJson<TPHMessage>(
      `${projectHubWorkspacePath(workspaceSlug)}/conversations/${conversationId}/messages/`,
      data
    );
  }

  editMessage(workspaceSlug: string, conversationId: string, messageId: string, body: string) {
    return this.patchJson<TPHMessage>(
      `${projectHubWorkspacePath(workspaceSlug)}/conversations/${conversationId}/messages/${messageId}/`,
      { body }
    );
  }

  /** Explicit read marker — reading a preview never marks everything as read (J08). */
  markRead(workspaceSlug: string, conversationId: string) {
    return this.postJson<unknown>(`${projectHubWorkspacePath(workspaceSlug)}/conversations/${conversationId}/read`);
  }

  previewContext(workspaceSlug: string, data: TPHContextPreviewRequest) {
    return this.postJson<TPHContextPreview>(`${projectHubWorkspacePath(workspaceSlug)}/ai/context-preview`, data);
  }

  previewDecision(workspaceSlug: string, projectId: string, data: TPHDecisionPreviewRequest) {
    return this.postJson<TPHDecisionPreview>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/decisions/preview`,
      data
    );
  }

  confirmDecision(workspaceSlug: string, projectId: string, data: TPHDecisionCreate) {
    return this.postJson<TPHDecision>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/decisions`,
      data,
      data.idempotency_key
    );
  }

  listDecisions(workspaceSlug: string, projectId: string, issueId?: string) {
    return this.getJson<TPHDecision[]>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/decisions/`,
      issueId ? { issue_id: issueId } : undefined
    );
  }

  clarify(workspaceSlug: string, projectId: string, issueId: string, answer?: string) {
    return this.postJson<TPHClarifyStep>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/work-items/${issueId}/clarify`,
      answer ? { answer } : {}
    );
  }

  listProposals(workspaceSlug: string, projectId: string, issueId?: string) {
    return this.getJson<TPHProposal[]>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/proposals/`,
      issueId ? { issue_id: issueId } : undefined
    );
  }

  acceptProposal(workspaceSlug: string, projectId: string, proposalId: string) {
    return this.postJson<TPHProposal>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/proposals/${proposalId}/accept`
    );
  }

  rejectProposal(workspaceSlug: string, projectId: string, proposalId: string) {
    return this.postJson<TPHProposal>(
      `${projectHubProjectPath(workspaceSlug, projectId)}/proposals/${proposalId}/reject`
    );
  }

  listNotifications(workspaceSlug: string) {
    return this.getJson<TPHNotificationItem[]>(`${projectHubWorkspacePath(workspaceSlug)}/notifications/`);
  }
}
