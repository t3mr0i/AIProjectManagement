# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Collaboration / AI / knowledge routes (API.md §5). Mounted under ``api/``."""

from django.urls import path

from ..views import collaboration as v

W = "workspaces/<str:slug>/package-flow/"
P = "workspaces/<str:slug>/projects/<uuid:project_id>/package-flow/"


def both(route, view, name):
    """Accept the path with and without trailing slash (API.md uses both forms)."""
    route = route.rstrip("/")
    return [path(route + "/", view, name=name), path(route, view, name=name + "-noslash")]


urlpatterns = [
    # conversations
    *both(W + "conversations/", v.ConversationListEndpoint.as_view(), "pf-conversations"),
    *both(W + "conversations/<uuid:conversation_id>/", v.ConversationDetailEndpoint.as_view(), "pf-conversation"),
    *both(W + "conversations/<uuid:conversation_id>/messages/", v.MessageListEndpoint.as_view(), "pf-messages"),
    *both(
        W + "conversations/<uuid:conversation_id>/messages/<uuid:message_id>/",
        v.MessageDetailEndpoint.as_view(),
        "pf-conversation-message",
    ),
    *both(
        W + "conversations/<uuid:conversation_id>/messages/<uuid:message_id>/versions/",
        v.MessageVersionsEndpoint.as_view(),
        "pf-conversation-message-versions",
    ),
    *both(W + "conversations/<uuid:conversation_id>/read", v.ConversationReadEndpoint.as_view(), "pf-conv-read"),
    # AI
    *both(W + "ai/context-preview", v.AIContextPreviewEndpoint.as_view(), "pf-ai-context-preview"),
    # search, notifications, retention
    *both(W + "search/", v.SearchEndpoint.as_view(), "pf-search"),
    *both(W + "notifications/", v.NotificationListEndpoint.as_view(), "pf-notifications"),
    *both(
        W + "notifications/<uuid:notification_id>/read", v.NotificationReadEndpoint.as_view(), "pf-notification-read"
    ),
    *both(W + "exports/", v.ExportListEndpoint.as_view(), "pf-exports"),
    *both(W + "exports/<uuid:export_id>/", v.ExportDetailEndpoint.as_view(), "pf-export"),
    *both(W + "retention/", v.RetentionEndpoint.as_view(), "pf-retention"),
    *both(W + "retention/apply", v.RetentionApplyEndpoint.as_view(), "pf-retention-apply"),
    # decisions
    *both(P + "decisions/preview", v.DecisionPreviewEndpoint.as_view(), "pf-decision-preview"),
    *both(P + "decisions/", v.DecisionListEndpoint.as_view(), "pf-decisions"),
    # clarification + package thread
    *both(P + "work-items/<uuid:issue_id>/clarify", v.ClarifyEndpoint.as_view(), "pf-clarify"),
    *both(P + "work-items/<uuid:issue_id>/thread", v.PackageThreadEndpoint.as_view(), "pf-package-thread"),
    # AI proposals
    *both(P + "proposals/", v.ProposalListEndpoint.as_view(), "pf-proposals"),
    *both(
        P + "proposals/<uuid:proposal_id>/<str:action>",
        v.ProposalDecisionEndpoint.as_view(),
        "pf-proposal-decision",
    ),
    # uploads
    *both(P + "uploads/<uuid:asset_id>/register", v.UploadRegisterEndpoint.as_view(), "pf-upload-register"),
    *both(P + "uploads/<uuid:asset_id>/", v.UploadDetailEndpoint.as_view(), "pf-upload"),
    # activity + overview
    *both(P + "activity/visit", v.ActivityVisitEndpoint.as_view(), "pf-activity-visit"),
    *both(P + "activity/", v.ActivityEndpoint.as_view(), "pf-activity"),
    *both(P + "overview", v.OverviewEndpoint.as_view(), "pf-overview"),
]
