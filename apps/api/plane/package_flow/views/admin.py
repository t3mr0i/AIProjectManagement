# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Activation, capability grants, capabilities/me and audit (API.md §1, I01)."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from plane.db.models import Project, WorkspaceMember

from ..capabilities import has_capability, is_extension_enabled, require_capability
from ..errors import Conflict, HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import AuditEntry, Capability, CapabilityGrant, ExtensionActivation
from ..services import events
from .base import PackageFlowBaseView


def _body(request):
    data = request.data
    if not isinstance(data, dict):
        raise ValidationFailed("JSON object body expected")
    return data


def _grant_data(grant):
    return {
        "id": str(grant.id),
        "member_id": str(grant.member_id),
        "capability": grant.capability,
        "project_id": str(grant.project_id) if grant.project_id else None,
        "granted_by": str(grant.granted_by_id) if grant.granted_by_id else None,
        "created_at": grant.created_at.isoformat() if grant.created_at else None,
    }


class _AdminView(PackageFlowBaseView):
    def require_admin(self, workspace, *, human=False):
        require_capability(self.request.user, workspace.id, None, Capability.WORKSPACE_ADMIN)
        # Admin writes (activation, grants) are never delegated to automation (INV-03).
        if human and not self.principal.is_human:
            raise HumanPrincipalRequired("Administrative changes require an interactive human principal")


def _set_activation(workspace, project, is_enabled, reason, principal):
    with transaction.atomic():
        row = (
            ExtensionActivation.objects.select_for_update()
            .filter(workspace=workspace, project=project, deleted_at__isnull=True)
            .first()
        )
        if row is None:
            row = ExtensionActivation(workspace=workspace, project=project)
        previous = row.is_enabled if row.pk else None
        row.is_enabled = bool(is_enabled)
        row.reason = str(reason or "")
        row.changed_by = principal.user
        row.save()
        events.audit(
            workspace_id=workspace.id,
            project_id=project.id if project else None,
            actor=principal.user,
            actor_kind=principal.kind,
            action="extension.activation_changed",
            target_type="extension_activation",
            target_id=row.id,
            detail={"is_enabled": row.is_enabled, "previous": previous, "reason": row.reason},
        )
    return row


def _parse_enabled(data):
    value = data.get("is_enabled")
    if not isinstance(value, bool):
        raise ValidationFailed("is_enabled must be a boolean", detail={"field": "is_enabled"})
    return value


class WorkspaceActivationView(_AdminView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        rows = ExtensionActivation.objects.filter(
            workspace=workspace, project__isnull=False, deleted_at__isnull=True
        ).values_list("project_id", "is_enabled")
        return Response(
            {
                "workspace_enabled": is_extension_enabled(workspace.id),
                "projects": [{"project_id": str(p), "is_enabled": e} for p, e in rows],
            }
        )

    def put(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace, human=True)
        data = _body(request)
        row = _set_activation(workspace, None, _parse_enabled(data), data.get("reason"), self.principal)
        return Response({"workspace_enabled": row.is_enabled, "reason": row.reason})


class ProjectActivationView(_AdminView):
    def put(self, request, slug, project_id):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace, human=True)
        project = Project.objects.filter(id=project_id, workspace=workspace, deleted_at__isnull=True).first()
        if project is None:
            raise NotFound("Project not found")
        data = _body(request)
        row = _set_activation(workspace, project, _parse_enabled(data), data.get("reason"), self.principal)
        return Response({"project_id": str(project.id), "is_enabled": row.is_enabled, "reason": row.reason})


class CapabilitiesMeView(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        project_id = request.query_params.get("project_id") or None
        if project_id:
            project = Project.objects.filter(id=project_id, workspace=workspace, deleted_at__isnull=True).first()
            if project is None or not has_capability(request.user, workspace.id, project.id, Capability.PROJECT_READ):
                raise NotFound("Project not found")
        caps = [c.value for c in Capability if has_capability(request.user, workspace.id, project_id, c.value)]
        if not self.principal.is_human:
            # Agents can hold delegated rights but never the human-only approval capabilities (INV-03).
            caps = [c for c in caps if c not in (Capability.PACKAGE_APPROVE_EXECUTION, Capability.WORKSPACE_ADMIN)]
        return Response(
            {
                "capabilities": caps,
                "principal_kind": self.principal.kind,
                "extension_enabled": is_extension_enabled(workspace.id, project_id),
            }
        )


class CapabilityGrantListView(_AdminView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace)
        qs = CapabilityGrant.objects.filter(workspace=workspace, deleted_at__isnull=True).order_by("-created_at")
        if request.query_params.get("member_id"):
            qs = qs.filter(member_id=request.query_params["member_id"])
        if request.query_params.get("project_id"):
            qs = qs.filter(project_id=request.query_params["project_id"])
        return Response({"results": [_grant_data(g) for g in qs]})

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace, human=True)
        data = _body(request)
        capability = data.get("capability")
        if capability not in Capability.values:
            raise ValidationFailed("Unknown capability", detail={"allowed": list(Capability.values)})
        member = (
            WorkspaceMember.objects.filter(workspace=workspace, member_id=data.get("member_id"), is_active=True).first()
            if data.get("member_id")
            else None
        )
        if member is None:
            raise NotFound("Member not found")
        project = None
        if data.get("project_id"):
            project = Project.objects.filter(
                id=data["project_id"], workspace=workspace, deleted_at__isnull=True
            ).first()
            if project is None:
                raise NotFound("Project not found")

        def run():
            try:
                with transaction.atomic():
                    grant = CapabilityGrant.objects.create(
                        workspace=workspace,
                        project=project,
                        member_id=member.member_id,
                        capability=capability,
                        granted_by=request.user,
                    )
            except IntegrityError:
                raise Conflict("Grant already exists", code="GRANT_EXISTS")
            events.audit(
                workspace_id=workspace.id,
                project_id=project.id if project else None,
                actor=request.user,
                actor_kind=self.principal.kind,
                action="capability.granted",
                target_type="capability_grant",
                target_id=grant.id,
                detail={"member_id": str(member.member_id), "capability": capability},
            )
            return 201, _grant_data(grant)

        return self.idempotent(workspace.id, "capability-grant", data, run)


class CapabilityGrantDetailView(_AdminView):
    def delete(self, request, slug, grant_id):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace, human=True)
        grant = CapabilityGrant.objects.filter(id=grant_id, workspace=workspace, deleted_at__isnull=True).first()
        if grant is None:
            raise NotFound("Grant not found")
        with transaction.atomic():
            CapabilityGrant.objects.filter(pk=grant.pk).update(deleted_at=timezone.now())
            events.audit(
                workspace_id=workspace.id,
                project_id=grant.project_id,
                actor=request.user,
                actor_kind=self.principal.kind,
                action="capability.revoked",
                target_type="capability_grant",
                target_id=grant.id,
                detail={"member_id": str(grant.member_id), "capability": grant.capability},
            )
        return Response(status=204)


class AuditListView(_AdminView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_admin(workspace)
        qs = AuditEntry.objects.filter(workspace=workspace).order_by("-created_at")
        if request.query_params.get("project_id"):
            qs = qs.filter(project_id=request.query_params["project_id"])
        if request.query_params.get("action"):
            qs = qs.filter(action=request.query_params["action"])
        try:
            limit = max(1, min(500, int(request.query_params.get("limit", 100))))
        except ValueError:
            limit = 100
        return Response(
            {
                "results": [
                    {
                        "id": str(e.id),
                        "action": e.action,
                        "actor_id": str(e.actor_id) if e.actor_id else None,
                        "actor_kind": e.actor_kind,
                        "project_id": str(e.project_id) if e.project_id else None,
                        "issue_id": str(e.issue_id) if e.issue_id else None,
                        "target_type": e.target_type,
                        "target_id": e.target_id,
                        "detail": e.detail,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in qs[:limit]
                ]
            }
        )
