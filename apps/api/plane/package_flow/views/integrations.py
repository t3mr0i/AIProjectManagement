# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Integrations, delivery and review endpoints (API.md §4; I04/I10/I12)."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..adapters import all_declarations
from ..errors import DomainError, NotFound, ValidationFailed
from ..models import (
    Capability,
    Evidence,
    ExternalLink,
    IntegrationConnection,
    MergeRequestLink,
    RepositoryBinding,
    SyncConflict,
)
from ..services import delivery as delivery_svc
from ..services import integrations as svc
from ..services import review as review_svc
from ..services.delivery import serialize_evidence, serialize_mr
from .base import PackageFlowBaseView


def _body(request):
    data = request.data
    if not isinstance(data, dict):
        raise ValidationFailed("JSON object body expected")
    return data


# ---------------------------------------------------------------------------
# Workspace scope
# ---------------------------------------------------------------------------


class _WorkspaceView(PackageFlowBaseView):
    def manage(self, slug, enabled=True):
        workspace = self.get_workspace(slug)
        self.require(workspace.id, None, Capability.INTEGRATION_MANAGE, enabled=enabled)
        return workspace

    def connection(self, workspace, connection_id):
        c = IntegrationConnection.objects.filter(id=connection_id, workspace=workspace, deleted_at__isnull=True).first()
        if c is None:
            raise NotFound("Connection not found")
        return c


class ProvidersView(_WorkspaceView):
    def get(self, request, slug):
        self.get_workspace(slug)
        return Response({"providers": all_declarations()})


class ConnectionListView(_WorkspaceView):
    def get(self, request, slug):
        workspace = self.manage(slug, enabled=False)
        rows = IntegrationConnection.objects.filter(workspace=workspace, deleted_at__isnull=True).order_by("created_at")
        return Response({"results": [svc.serialize_connection(c) for c in rows]})

    def post(self, request, slug):
        workspace = self.manage(slug)
        data = _body(request)
        # The idempotency hash must not contain the secret in clear text.
        fingerprint = {k: v for k, v in data.items() if k != "webhook_secret"}
        fingerprint["webhook_secret_set"] = bool(data.get("webhook_secret"))
        return self.idempotent(
            workspace.id,
            "integrations.connection.create",
            fingerprint,
            lambda: (201, svc.serialize_connection(svc.create_connection(workspace, request.user, data))),
        )


class ConnectionDetailView(_WorkspaceView):
    def get(self, request, slug, connection_id):
        workspace = self.manage(slug, enabled=False)
        return Response(svc.serialize_connection(self.connection(workspace, connection_id)))

    def patch(self, request, slug, connection_id):
        workspace = self.manage(slug)
        c = self.connection(workspace, connection_id)
        reconnecting = request.data.get("status") == "active" and c.status == IntegrationConnection.Status.DISABLED
        c = svc.update_connection(c, request.user, _body(request))
        if reconnecting:
            svc.schedule_reconcile(c.id)
        return Response(svc.serialize_connection(c))

    def delete(self, request, slug, connection_id):
        workspace = self.manage(slug, enabled=False)
        c = svc.disconnect_connection(self.connection(workspace, connection_id), request.user)
        return Response(svc.serialize_connection(c))


class ConnectionHealthView(_WorkspaceView):
    def get(self, request, slug, connection_id):
        workspace = self.manage(slug, enabled=False)
        return Response(svc.connection_health(self.connection(workspace, connection_id)))


class ConnectionReconcileView(_WorkspaceView):
    def post(self, request, slug, connection_id):
        workspace = self.manage(slug)
        c = self.connection(workspace, connection_id)
        if c.status == IntegrationConnection.Status.DISABLED:
            return Response({"error": "Connection is disconnected", "code": "CONNECTION_DISABLED"}, status=409)
        result = svc.schedule_reconcile(c.id)
        body = {"accepted": True, "connection_id": str(c.id)}
        if result is not None:
            body["result"] = result
        return Response(body, status=202)


# ---------------------------------------------------------------------------
# Webhook ingress (no session auth; adapter signature is the authentication)
# ---------------------------------------------------------------------------


class WebhookIngressView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request, connection_id):
        body = request.body  # raw bytes must be read before DRF parses them
        try:
            status_code, payload = svc.ingest_webhook(connection_id, request.headers, body)
        except DomainError as exc:
            response = Response(exc.as_dict(), status=exc.status_code)
            if exc.status_code == 429 and exc.detail.get("retry_after"):
                response["Retry-After"] = str(exc.detail["retry_after"])
            return response
        return Response(payload, status=status_code)


# ---------------------------------------------------------------------------
# Project scope
# ---------------------------------------------------------------------------


class _ProjectView(PackageFlowBaseView):
    def read_project(self, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        self.require(project.workspace_id, project.id, Capability.PROJECT_READ, enabled=False)
        return project

    def read_issue(self, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        self.require(issue.workspace_id, issue.project_id, Capability.PROJECT_READ, enabled=False)
        return issue


class RepositoryListView(_ProjectView):
    def get(self, request, slug, project_id):
        project = self.read_project(slug, project_id)
        rows = RepositoryBinding.objects.select_related("connection").filter(project=project, deleted_at__isnull=True)
        return Response({"results": [svc.serialize_binding(b) for b in rows.order_by("path_with_namespace")]})

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.INTEGRATION_MANAGE)
        data = _body(request)
        return self.idempotent(
            project.workspace_id,
            f"integrations.repository.bind:{project.id}",
            data,
            lambda: (201, svc.serialize_binding(svc.bind_repository(project, request.user, data))),
        )


class ImportPreviewView(_ProjectView):
    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.INTEGRATION_MANAGE, enabled=False)
        return Response(svc.import_preview(project, _body(request)))


class ExternalLinkListView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        rows = ExternalLink.objects.select_related("connection").filter(issue=issue, deleted_at__isnull=True)
        return Response({"results": [svc.serialize_link(link) for link in rows.order_by("created_at")]})

    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_EDIT)
        data = _body(request)
        return self.idempotent(
            issue.workspace_id,
            f"integrations.link.create:{issue.id}",
            data,
            lambda: (201, svc.serialize_link(svc.create_external_link(issue, request.user, data))),
        )


class MergeRequestListView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        rows = MergeRequestLink.objects.select_related("repository_binding").filter(
            issue=issue, deleted_at__isnull=True
        )
        return Response({"results": [serialize_mr(m) for m in rows.order_by("created_at")]})


class EvidenceListView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        rows = Evidence.objects.filter(issue=issue, deleted_at__isnull=True).order_by("-occurred_at")
        return Response({"results": [serialize_evidence(e) for e in rows]})


class ReviewView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        return Response(delivery_svc.review_view(issue))


class ReviewApprovalView(_ProjectView):
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        # Human check before anything else: agents are refused regardless of grants (INV-03).
        principal = self.principal
        data = _body(request)

        def run():
            approval = review_svc.create_review_approval(principal, issue, data)
            from ..services.delivery import approval_validity

            mr_by_id = {approval.merge_request_id: approval.merge_request} if approval.merge_request_id else {}
            return 201, delivery_svc.serialize_approval(
                approval, approval_validity(approval, approval.revision, mr_by_id)
            )

        return self.idempotent(issue.workspace_id, f"review.approval:{issue.id}", data, run)


class MergeView(_ProjectView):
    def post(self, request, slug, project_id, link_id):
        project = self.get_project(slug, project_id)
        link = (
            MergeRequestLink.objects.select_related("repository_binding__connection", "issue")
            .filter(id=link_id, project=project, deleted_at__isnull=True, issue__deleted_at__isnull=True)
            .first()
        )
        if link is None:
            raise NotFound("Merge request not found")
        data = _body(request)
        status_code, body = review_svc.request_merge(
            self.principal, link, (data.get("expected_head_sha") or "").strip(), squash=data.get("squash")
        )
        return Response(body, status=status_code)


class DeliveryView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        return Response(delivery_svc.delivery_view(issue))


class SyncConflictListView(_ProjectView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        rows = SyncConflict.objects.select_related("link__connection").filter(issue=issue, deleted_at__isnull=True)
        return Response({"results": [svc.serialize_conflict(c) for c in rows.order_by("-created_at")]})


class SyncConflictResolveView(_ProjectView):
    def post(self, request, slug, project_id, issue_id, conflict_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_EDIT)
        if not self.principal.is_human:
            from ..errors import HumanPrincipalRequired

            raise HumanPrincipalRequired("Conflict resolution requires a human principal")
        conflict = (
            SyncConflict.objects.select_related("link__connection", "issue")
            .filter(id=conflict_id, issue=issue, deleted_at__isnull=True)
            .first()
        )
        if conflict is None:
            raise NotFound("Conflict not found")
        conflict = svc.resolve_conflict(conflict, request.user, _body(request).get("resolution"))
        return Response(svc.serialize_conflict(conflict))
