# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Planning, OpenSpec and diagram routes (API.md §5 diagrams, §6). Mounted under ``api/``."""

from django.urls import path

from ..views import diagrams as d
from ..views import planning as v
from ..views import specs as s

W = "workspaces/<str:slug>/package-flow/"
P = "workspaces/<str:slug>/projects/<uuid:project_id>/package-flow/"


def both(route, view, name):
    """Accept the path with and without trailing slash (API.md uses both forms)."""
    route = route.rstrip("/")
    return [path(route + "/", view, name=name), path(route, view, name=name + "-noslash")]


urlpatterns = [
    # milestones / risks / calendar / cycles (project scoped)
    *both(P + "milestones/", v.MilestoneListEndpoint.as_view(), "pf-milestones"),
    *both(P + "milestones/<uuid:milestone_id>/", v.MilestoneDetailEndpoint.as_view(), "pf-milestone"),
    *both(P + "risks/", v.RiskListEndpoint.as_view(), "pf-risks"),
    *both(P + "risks/<uuid:risk_id>/", v.RiskDetailEndpoint.as_view(), "pf-risk"),
    path(P + "events.ics", v.EventIcsEndpoint.as_view(), name="pf-events-ics"),
    *both(P + "events/", v.EventListEndpoint.as_view(), "pf-events"),
    *both(P + "events/<uuid:event_id>/", v.EventDetailEndpoint.as_view(), "pf-event"),
    *both(P + "cycles-context/", v.CyclesContextEndpoint.as_view(), "pf-cycles-context"),
    # dependencies / roadmap / scenarios / teams (workspace scoped)
    *both(W + "dependencies/", v.DependencyListEndpoint.as_view(), "pf-dependencies"),
    *both(W + "dependencies/<uuid:dependency_id>/", v.DependencyDetailEndpoint.as_view(), "pf-dependency"),
    *both(
        W + "dependencies/<uuid:dependency_id>/confirm",
        v.DependencyConfirmEndpoint.as_view(),
        "pf-dependency-confirm",
    ),
    *both(
        W + "dependencies/<uuid:dependency_id>/reject",
        v.DependencyConfirmEndpoint.as_view(reject=True),
        "pf-dependency-reject",
    ),
    *both(W + "roadmap/", v.RoadmapEndpoint.as_view(), "pf-roadmap"),
    *both(W + "scenarios/", v.ScenarioListEndpoint.as_view(), "pf-scenarios"),
    *both(W + "scenarios/<uuid:scenario_id>/impact", v.ScenarioImpactEndpoint.as_view(), "pf-scenario-impact"),
    *both(W + "scenarios/<uuid:scenario_id>/apply", v.ScenarioApplyEndpoint.as_view(), "pf-scenario-apply"),
    *both(W + "teams/", v.TeamListEndpoint.as_view(), "pf-teams"),
    *both(W + "teams/<uuid:team_id>/", v.TeamDetailEndpoint.as_view(), "pf-team"),
    # OpenSpec (FR-W08, FR-G02)
    *both(P + "work-items/<uuid:issue_id>/spec", s.SpecStateEndpoint.as_view(), "pf-spec"),
    *both(P + "work-items/<uuid:issue_id>/spec/export", s.SpecExportEndpoint.as_view(), "pf-spec-export"),
    *both(P + "work-items/<uuid:issue_id>/spec/import", s.SpecImportEndpoint.as_view(), "pf-spec-import"),
    *both(P + "work-items/<uuid:issue_id>/spec/resolve", s.SpecResolveEndpoint.as_view(), "pf-spec-resolve"),
    *both(
        P + "work-items/<uuid:issue_id>/spec/publish-confirm",
        s.SpecPublishConfirmEndpoint.as_view(),
        "pf-spec-publish-confirm",
    ),
    # diagrams (FR-E02, FR-E03)
    *both(P + "diagrams/", d.DiagramListEndpoint.as_view(), "pf-diagrams"),
    *both(P + "diagrams/<uuid:diagram_id>/", d.DiagramDetailEndpoint.as_view(), "pf-diagram"),
    *both(
        P + "diagrams/<uuid:diagram_id>/proposals/<uuid:proposal_id>/accept",
        d.DiagramProposalDecisionEndpoint.as_view(decision="accept"),
        "pf-diagram-proposal-accept",
    ),
    *both(
        P + "diagrams/<uuid:diagram_id>/proposals/<uuid:proposal_id>/reject",
        d.DiagramProposalDecisionEndpoint.as_view(decision="reject"),
        "pf-diagram-proposal-reject",
    ),
]
