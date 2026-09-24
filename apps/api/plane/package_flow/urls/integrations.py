# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Integrations, delivery and review routes (API.md §4). Mounted under ``api/``."""

from django.urls import path

from ..views import integrations as v

P = "workspaces/<str:slug>/projects/<uuid:project_id>/package-flow/"
W = "workspaces/<str:slug>/package-flow/"
WI = P + "work-items/<uuid:issue_id>/"


def both(route, view, name):
    route = route.rstrip("/")
    return [path(route + "/", view, name=name), path(route, view)]


urlpatterns = [
    *both(W + "providers", v.ProvidersView.as_view(), "pf-providers"),
    *both(W + "connections", v.ConnectionListView.as_view(), "pf-connections"),
    *both(W + "connections/<uuid:connection_id>", v.ConnectionDetailView.as_view(), "pf-connection-detail"),
    *both(W + "connections/<uuid:connection_id>/health", v.ConnectionHealthView.as_view(), "pf-connection-health"),
    *both(
        W + "connections/<uuid:connection_id>/reconcile", v.ConnectionReconcileView.as_view(), "pf-connection-reconcile"
    ),
    *both("package-flow/webhooks/<uuid:connection_id>", v.WebhookIngressView.as_view(), "pf-webhook-ingress"),
    *both(P + "repositories", v.RepositoryListView.as_view(), "pf-repositories"),
    *both(P + "repositories/import-preview", v.ImportPreviewView.as_view(), "pf-import-preview"),
    *both(WI + "external-links", v.ExternalLinkListView.as_view(), "pf-external-links"),
    *both(WI + "merge-requests", v.MergeRequestListView.as_view(), "pf-merge-requests"),
    *both(WI + "evidence", v.EvidenceListView.as_view(), "pf-evidence"),
    *both(WI + "review", v.ReviewView.as_view(), "pf-review"),
    *both(WI + "delivery", v.DeliveryView.as_view(), "pf-delivery"),
    *both(WI + "sync-conflicts", v.SyncConflictListView.as_view(), "pf-sync-conflicts"),
    *both(
        WI + "sync-conflicts/<uuid:conflict_id>/resolve",
        v.SyncConflictResolveView.as_view(),
        "pf-sync-conflict-resolve",
    ),
    *both(P + "reviews/<uuid:issue_id>/approvals", v.ReviewApprovalView.as_view(), "pf-review-approvals"),
    *both(P + "merge-requests/<uuid:link_id>/merge", v.MergeView.as_view(), "pf-merge"),
]
