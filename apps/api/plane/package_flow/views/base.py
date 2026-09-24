# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Base view + scope resolution for package-flow endpoints.

Scope resolution always goes through native Plane rows:
workspace slug -> Workspace, project_id must belong to it, issue_id must belong
to the project. Soft-deleted rows, archived projects and non-members are
rejected; foreign references are reported as 404 (no existence oracle).
"""

import hashlib
import json

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.authentication.session import BaseSessionAuthentication
from plane.db.models import Issue, Project, Workspace

from ..capabilities import (
    is_project_member,
    require_capability,
    require_extension_enabled,
    workspace_role,
)
from ..errors import DomainError, NotFound
from ..models import IdempotencyRecord
from ..principal import RunnerTokenAuthentication, resolve_principal


class PackageFlowBaseView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [BaseSessionAuthentication, RunnerTokenAuthentication]

    # -- error mapping -------------------------------------------------------
    def handle_exception(self, exc):
        if isinstance(exc, DomainError):
            return Response(exc.as_dict(), status=exc.status_code)
        return super().handle_exception(exc)

    # -- principal / scope ---------------------------------------------------
    @property
    def principal(self):
        if not hasattr(self, "_principal"):
            self._principal = resolve_principal(self.request)
        return self._principal

    def get_workspace(self, slug):
        workspace = Workspace.objects.filter(slug=slug, deleted_at__isnull=True).first()
        if workspace is None or workspace_role(self.request.user, workspace.id) is None:
            raise NotFound("Workspace not found")
        runner = self.principal.runner
        if runner is not None and runner.workspace_id != workspace.id:
            raise NotFound("Workspace not found")
        return workspace

    def get_project(self, slug, project_id, *, allow_archived=False):
        workspace = self.get_workspace(slug)
        qs = Project.objects.filter(id=project_id, workspace=workspace, deleted_at__isnull=True)
        project = qs.first()
        if project is None or not is_project_member(self.request.user, project.id):
            raise NotFound("Project not found")
        if project.archived_at is not None and not allow_archived:
            from ..errors import Conflict

            raise Conflict("Project is archived", code="PROJECT_ARCHIVED")
        return project

    def get_issue(self, slug, project_id, issue_id, *, allow_archived=False):
        """Load a native issue *including authorized drafts*, excluding deleted/foreign ones (FR-B07)."""
        project = self.get_project(slug, project_id, allow_archived=allow_archived)
        issue = (
            Issue.all_objects.filter(id=issue_id, project=project, workspace_id=project.workspace_id)
            .filter(deleted_at__isnull=True)
            .select_related("state", "project", "workspace")
            .first()
        )
        if issue is None:
            raise NotFound("Work item not found")
        if issue.archived_at is not None and not allow_archived:
            from ..errors import Conflict

            raise Conflict("Work item is archived", code="WORK_ITEM_ARCHIVED")
        return issue

    def require(self, workspace_id, project_id, capability, *, enabled=True):
        require_capability(self.request.user, workspace_id, project_id, capability)
        if enabled:
            require_extension_enabled(workspace_id, project_id)

    # -- idempotency ---------------------------------------------------------
    def idempotent(self, workspace_id, scope, payload, fn):
        """Run ``fn`` once per ``Idempotency-Key``; replay stored response (PRD §12.3).

        ``fn`` returns ``(status_code, body_dict)``. Same key + different payload -> 409.
        """
        key = self.request.headers.get("Idempotency-Key")
        if not key:
            code, body = fn()
            return Response(body, status=code)
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        user = self.request.user
        existing = IdempotencyRecord.objects.filter(workspace_id=workspace_id, actor=user, scope=scope, key=key).first()
        if existing:
            return self._replay(existing, request_hash)
        try:
            with transaction.atomic():
                code, body = fn()
                IdempotencyRecord.objects.create(
                    workspace_id=workspace_id,
                    actor=user,
                    scope=scope,
                    key=key,
                    request_hash=request_hash,
                    response_status=code,
                    response_body=json.loads(json.dumps(body, default=str)),
                )
        except IntegrityError:
            existing = IdempotencyRecord.objects.get(workspace_id=workspace_id, actor=user, scope=scope, key=key)
            return self._replay(existing, request_hash)
        return Response(body, status=code)

    @staticmethod
    def _replay(record, request_hash):
        if record.request_hash != request_hash:
            return Response(
                {"error": "Idempotency-Key reused with a different payload", "code": "IDEMPOTENCY_MISMATCH"},
                status=status.HTTP_409_CONFLICT,
            )
        response = Response(record.response_body, status=record.response_status)
        response["Idempotent-Replay"] = "true"
        return response
