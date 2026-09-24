# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""OpenSpec endpoints (API §6): ``P/work-items/{issue_id}/spec[/export|/import]``."""

from rest_framework import status
from rest_framework.response import Response

from ..capabilities import require_capability
from ..models import Capability
from ..services import specs as spec_service
from .base import PackageFlowBaseView


class SpecStateEndpoint(PackageFlowBaseView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        require_capability(request.user, issue.workspace_id, issue.project_id, Capability.PROJECT_READ)
        return Response(spec_service.get_spec_state(issue))


class SpecExportEndpoint(PackageFlowBaseView):
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_EDIT)
        data = request.data or {}

        def run():
            body = spec_service.export_spec(
                issue,
                self.principal,
                repository_binding_id=data.get("repository_binding_id"),
                expected_base_commit=data.get("expected_base_commit"),
                revision_id=data.get("revision_id"),
            )
            return status.HTTP_200_OK, body

        return self.idempotent(issue.workspace_id, f"spec.export:{issue.id}", data, run)


class SpecImportEndpoint(PackageFlowBaseView):
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_EDIT)
        data = request.data or {}

        def run():
            body = spec_service.import_spec(
                issue,
                self.principal,
                files=data.get("files"),
                content=data.get("content"),
                commit=data.get("commit"),
                repository_binding_id=data.get("repository_binding_id"),
                resolutions=data.get("resolutions"),
            )
            if body.get("conflict"):
                return status.HTTP_409_CONFLICT, {
                    "error": "OpenSpec import conflicts with the platform draft",
                    "code": "SPEC_CONFLICT",
                    "detail": {"conflicts": body["conflicts"], "state": body["state"]},
                }
            return status.HTTP_200_OK, body

        return self.idempotent(issue.workspace_id, f"spec.import:{issue.id}", data, run)
