# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Diagram endpoints (API §5): ``P/diagrams/``, ``P/diagrams/{id}/``, proposal accept/reject."""

from rest_framework import status
from rest_framework.response import Response

from plane.db.models import Issue

from ..capabilities import require_capability
from ..errors import NotFound
from ..models import AIProposal, Capability, DiagramDocument
from ..services import diagrams as diagram_service
from .base import PackageFlowBaseView


class DiagramListEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        qs = DiagramDocument.objects.filter(project=project, deleted_at__isnull=True).order_by("-updated_at")
        issue_id = request.query_params.get("issue_id")
        if issue_id:
            qs = qs.filter(issue_id=issue_id)
        return Response([diagram_service.serialize_diagram(d) for d in qs[:200]])

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        data = request.data or {}
        issue = None
        if data.get("issue_id"):
            issue = Issue.all_objects.filter(id=data["issue_id"], project=project, deleted_at__isnull=True).first()
            if issue is None:
                raise NotFound("Work item not found")
        diagram = diagram_service.create_diagram(project, self.principal, data, issue=issue)
        return Response(diagram_service.serialize_diagram(diagram), status=status.HTTP_201_CREATED)


class DiagramDetailEndpoint(PackageFlowBaseView):
    def _diagram(self, project, diagram_id):
        diagram = DiagramDocument.objects.filter(id=diagram_id, project=project, deleted_at__isnull=True).first()
        if diagram is None:
            raise NotFound("Diagram not found")
        return diagram

    def get(self, request, slug, project_id, diagram_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        require_capability(request.user, project.workspace_id, project.id, Capability.PROJECT_READ)
        diagram = self._diagram(project, diagram_id)
        body = diagram_service.serialize_diagram(diagram)
        body["versions"] = [diagram_service.serialize_version(v) for v in diagram.versions.order_by("-version")[:50]]
        body["proposals"] = [
            diagram_service.serialize_proposal(p)
            for p in AIProposal.objects.filter(
                project=project,
                kind=AIProposal.Kind.DIAGRAM_INTERPRETATION,
                content__diagram_id=str(diagram.id),
                deleted_at__isnull=True,
            ).order_by("-created_at")[:20]
        ]
        return Response(body)

    def put(self, request, slug, project_id, diagram_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        return Response(diagram_service.update_diagram(diagram_id, project, self.principal, request.data or {}))

    patch = put


class DiagramProposalDecisionEndpoint(PackageFlowBaseView):
    decision = "accept"

    def post(self, request, slug, project_id, diagram_id, proposal_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        diagram = DiagramDocument.objects.filter(id=diagram_id, project=project, deleted_at__isnull=True).first()
        if diagram is None:
            raise NotFound("Diagram not found")
        if self.decision == "accept":
            body = diagram_service.accept_diagram_proposal(diagram, proposal_id, self.principal, request.data or {})
        else:
            body = diagram_service.reject_proposal(diagram, proposal_id, self.principal)
        return Response(body)
