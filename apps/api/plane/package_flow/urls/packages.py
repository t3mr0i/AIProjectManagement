# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Activation/capabilities/audit (API.md §1) and packages/revisions/approvals (API.md §2).

Mounted under ``api/``. Each route is registered with and without a trailing
slash so clients following the contract table literally both work.
"""

from django.urls import path

from ..views import admin, packages

P = "workspaces/<str:slug>/projects/<uuid:project_id>/package-flow/"
W = "workspaces/<str:slug>/package-flow/"
WI = P + "work-items/<uuid:issue_id>/"


def both(route, view, name):
    route = route.rstrip("/")
    return [path(route + "/", view, name=name), path(route, view)]


urlpatterns = [
    # §1 activation, capabilities, audit
    *both(W + "activation", admin.WorkspaceActivationView.as_view(), "pf-workspace-activation"),
    *both(P + "activation", admin.ProjectActivationView.as_view(), "pf-project-activation"),
    *both(W + "capabilities/me", admin.CapabilitiesMeView.as_view(), "pf-capabilities-me"),
    *both(W + "capability-grants", admin.CapabilityGrantListView.as_view(), "pf-capability-grants"),
    *both(
        W + "capability-grants/<uuid:grant_id>",
        admin.CapabilityGrantDetailView.as_view(),
        "pf-capability-grant-detail",
    ),
    *both(W + "audit", admin.AuditListView.as_view(), "pf-audit"),
    # §2 packages
    *both(P + "packages", packages.PackageListView.as_view(), "pf-packages"),
    *both(WI + "profile", packages.ProfileView.as_view(), "pf-profile"),
    *both(WI + "readiness", packages.ReadinessView.as_view(), "pf-readiness"),
    *both(WI + "revisions/compare", packages.RevisionCompareView.as_view(), "pf-revision-compare"),
    *both(WI + "revisions", packages.RevisionListView.as_view(), "pf-revisions"),
    *both(WI + "revisions/<uuid:revision_id>", packages.RevisionDetailView.as_view(), "pf-revision-detail"),
    *both(
        WI + "revisions/<uuid:revision_id>/contract",
        packages.RevisionContractView.as_view(),
        "pf-revision-contract",
    ),
    *both(WI + "execution-approvals", packages.ApprovalListView.as_view(), "pf-approvals"),
    *both(
        WI + "execution-approvals/<uuid:approval_id>/contract",
        packages.ApprovalContractView.as_view(),
        "pf-approval-contract",
    ),
    *both(
        WI + "execution-approvals/<uuid:approval_id>/revoke",
        packages.ApprovalRevokeView.as_view(),
        "pf-approval-revoke",
    ),
    *both(WI + "change-records", packages.ChangeRecordListView.as_view(), "pf-change-records"),
    *both(
        WI + "change-records/<uuid:record_id>",
        packages.ChangeRecordDetailView.as_view(),
        "pf-change-record-detail",
    ),
    *both(WI + "status", packages.StatusView.as_view(), "pf-status"),
]
