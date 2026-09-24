# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runner, claims and runs (API.md §3). ``package-flow/...`` is the runner ingress (runner token auth)."""

from django.urls import path

from ..views import execution

P = "workspaces/<str:slug>/projects/<uuid:project_id>/package-flow/"
W = "workspaces/<str:slug>/package-flow/"
WI = P + "work-items/<uuid:issue_id>/"
R = "package-flow/"


def both(route, view, name):
    route = route.rstrip("/")
    return [path(route + "/", view, name=name), path(route, view)]


urlpatterns = [
    *both(W + "runners", execution.RunnerListView.as_view(), "pf-runners"),
    *both(W + "runners/<uuid:runner_id>", execution.RunnerDetailView.as_view(), "pf-runner-detail"),
    *both(WI + "claims", execution.ClaimCreateView.as_view(), "pf-claims"),
    *both(WI + "runs", execution.RunListView.as_view(), "pf-runs"),
    *both(P + "runs/<uuid:run_id>/cancel", execution.RunCancelView.as_view(), "pf-run-cancel"),
    *both(R + "runner/me", execution.RunnerMeView.as_view(), "pf-runner-me"),
    *both(R + "claims/<uuid:claim_id>/heartbeat", execution.ClaimHeartbeatView.as_view(), "pf-claim-heartbeat"),
    *both(R + "claims/<uuid:claim_id>/release", execution.ClaimReleaseView.as_view(), "pf-claim-release"),
    *both(R + "runs/<uuid:run_id>/manifest", execution.RunManifestView.as_view(), "pf-run-manifest"),
    *both(R + "runs/<uuid:run_id>/events", execution.RunEventView.as_view(), "pf-run-events"),
    *both(R + "runs/<uuid:run_id>/actions", execution.RunActionView.as_view(), "pf-run-actions"),
    *both(R + "runs/<uuid:run_id>/evidence", execution.RunEvidenceView.as_view(), "pf-run-evidence"),
]
