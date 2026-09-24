# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Planning endpoints (API §6): milestones, dependencies, roadmap, scenarios, risks, events, teams."""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response

from ..capabilities import require_capability, require_extension_enabled
from ..errors import NotFound
from ..models import CalendarEvent, Capability, Milestone, PlanScenario
from ..services import planning
from .base import PackageFlowBaseView


def _csv(value):
    return [v for v in (value or "").split(",") if v]


# ---------------------------------------------------------------------------
# project scoped
# ---------------------------------------------------------------------------
class MilestoneListEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        tz = request.query_params.get("tz")
        if tz:
            planning._zone(tz)
        qs = Milestone.objects.filter(project=project, deleted_at__isnull=True)
        return Response([planning.serialize_milestone(m, tz) for m in qs])

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        m = planning.create_milestone(project, self.principal, request.data or {})
        return Response(planning.serialize_milestone(m), status=status.HTTP_201_CREATED)


class MilestoneDetailEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id, milestone_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        m = Milestone.objects.filter(id=milestone_id, project=project, deleted_at__isnull=True).first()
        if m is None:
            raise NotFound("Milestone not found")
        tz = request.query_params.get("tz")
        if tz:
            planning._zone(tz)
        return Response(planning.serialize_milestone(m, tz))

    def patch(self, request, slug, project_id, milestone_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        m = planning.update_milestone(project, self.principal, milestone_id, request.data or {})
        return Response(planning.serialize_milestone(m))

    def delete(self, request, slug, project_id, milestone_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        planning.delete_milestone(project, self.principal, milestone_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RiskListEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        return Response(planning.list_risks(project, request.user))

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        risk = planning.create_risk(project, self.principal, request.data or {})
        return Response(planning.serialize_risk(risk, request.user), status=status.HTTP_201_CREATED)


class RiskDetailEndpoint(PackageFlowBaseView):
    def patch(self, request, slug, project_id, risk_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        risk = planning.update_risk(project, self.principal, risk_id, request.data or {})
        return Response(planning.serialize_risk(risk, request.user))

    def delete(self, request, slug, project_id, risk_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        planning.delete_risk(project, self.principal, risk_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventDetailEndpoint(PackageFlowBaseView):
    def patch(self, request, slug, project_id, event_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        event = planning.update_event(project, self.principal, event_id, request.data or {})
        return Response(planning.serialize_event(event))

    def delete(self, request, slug, project_id, event_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        planning.delete_event(project, self.principal, event_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventListEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        tz = request.query_params.get("tz")
        if tz:
            planning._zone(tz)
        qs = CalendarEvent.objects.filter(project=project, deleted_at__isnull=True)
        return Response([planning.serialize_event(e, tz) for e in qs])

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_PLAN)
        event = planning.create_event(project, self.principal, request.data or {})
        return Response(planning.serialize_event(event), status=status.HTTP_201_CREATED)


class EventIcsEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        response = HttpResponse(planning.render_ics(project), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{project.identifier}.ics"'
        return response


class CyclesContextEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        return Response(planning.cycles_context(project))


# ---------------------------------------------------------------------------
# workspace scoped
# ---------------------------------------------------------------------------
class DependencyListEndpoint(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        project_ids = _csv(request.query_params.get("project_ids"))
        return Response(planning.list_dependencies(workspace, request.user, project_ids or None))

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        data = request.data or {}

        def run():
            return status.HTTP_201_CREATED, planning.create_dependency(workspace, self.principal, data)

        return self.idempotent(workspace.id, "dependency.create", data, run)


class DependencyDetailEndpoint(PackageFlowBaseView):
    def delete(self, request, slug, dependency_id):
        workspace = self.get_workspace(slug)
        planning.delete_dependency(workspace, self.principal, dependency_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DependencyConfirmEndpoint(PackageFlowBaseView):
    reject = False

    def post(self, request, slug, dependency_id):
        workspace = self.get_workspace(slug)
        return Response(planning.confirm_dependency(workspace, self.principal, dependency_id, reject=self.reject))


class RoadmapEndpoint(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        params = request.query_params
        return Response(
            planning.roadmap(
                workspace,
                request.user,
                project_ids=_csv(params.get("project_ids")) or None,
                team_id=params.get("team_id") or None,
                date_from=params.get("from") or None,
                date_to=params.get("to") or None,
                display_tz=params.get("tz") or None,
            )
        )


class ScenarioListEndpoint(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        out = []
        for scenario in PlanScenario.objects.filter(workspace=workspace, deleted_at__isnull=True).order_by(
            "-created_at"
        )[:100]:
            try:
                planning.load_scenario(workspace, request.user, scenario.id)
            except NotFound:
                continue
            out.append(planning.serialize_scenario(scenario))
        return Response(out)

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        require_extension_enabled(workspace.id)
        scenario = planning.create_scenario(workspace, self.principal, request.data or {})
        return Response(planning.serialize_scenario(scenario), status=status.HTTP_201_CREATED)


class ScenarioImpactEndpoint(PackageFlowBaseView):
    def get(self, request, slug, scenario_id):
        workspace = self.get_workspace(slug)
        scenario = planning.load_scenario(workspace, request.user, scenario_id)
        return Response(planning.scenario_impact(workspace, request.user, scenario))


class ScenarioApplyEndpoint(PackageFlowBaseView):
    def post(self, request, slug, scenario_id):
        workspace = self.get_workspace(slug)
        return Response(planning.apply_scenario(workspace, self.principal, scenario_id))


class TeamListEndpoint(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        return Response(planning.list_teams(workspace, request.user))

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        return Response(
            planning.upsert_team(workspace, self.principal, request.data or {}), status=status.HTTP_201_CREATED
        )


class TeamDetailEndpoint(PackageFlowBaseView):
    def patch(self, request, slug, team_id):
        workspace = self.get_workspace(slug)
        return Response(planning.upsert_team(workspace, self.principal, request.data or {}, team_id=team_id))
