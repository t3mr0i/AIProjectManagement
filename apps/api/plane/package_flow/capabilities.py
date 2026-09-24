# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Capability checks layered on native Plane memberships (PRD §5.2, FR-I07).

Rules:
* Every capability requires an *active* native membership at evaluation time,
  so revoking the Plane membership immediately removes all extension rights.
* ``project.read`` and ``package.edit`` follow native project membership
  (guests: read only).
* All execution/review/merge/decision/planning/integration capabilities need
  an explicit ``CapabilityGrant`` — native roles are not equated with them.
* ``workspace.admin`` follows the native workspace admin role; workspace admins
  get ``integration.manage`` but *no* implicit access to private DMs.
"""

from plane.db.models import Project, ProjectMember, WorkspaceMember

from .errors import ExtensionDisabled, PermissionDenied
from .models import Capability, CapabilityGrant, ExtensionActivation

ADMIN, MEMBER, GUEST = 20, 15, 5


def workspace_role(user, workspace_id):
    wm = (
        WorkspaceMember.objects.filter(workspace_id=workspace_id, member=user, is_active=True)
        .values_list("role", flat=True)
        .first()
    )
    return wm


def project_role(user, project_id):
    return (
        ProjectMember.objects.filter(
            project_id=project_id,
            member=user,
            is_active=True,
            member__is_active=True,
        )
        .values_list("role", flat=True)
        .first()
    )


def is_project_member(user, project_id) -> bool:
    return project_role(user, project_id) is not None and _project_accessible(project_id)


def _project_accessible(project_id) -> bool:
    return Project.objects.filter(id=project_id, deleted_at__isnull=True).exists()


def accessible_project_ids(user, workspace_id):
    """Native project memberships = the read boundary for all extension data (NFR-08)."""
    return list(
        ProjectMember.objects.filter(
            workspace_id=workspace_id,
            member=user,
            is_active=True,
            project__deleted_at__isnull=True,
        ).values_list("project_id", flat=True)
    )


def has_capability(user, workspace_id, project_id, capability) -> bool:
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    ws_role = workspace_role(user, workspace_id)
    if ws_role is None:
        return False

    if capability == Capability.WORKSPACE_ADMIN:
        return ws_role == ADMIN or _granted(user, workspace_id, None, capability)

    if capability == Capability.INTEGRATION_MANAGE and ws_role == ADMIN:
        return True

    if project_id is not None:
        role = project_role(user, project_id)
        if role is None or not _project_accessible(project_id):
            return False
        if capability == Capability.PROJECT_READ:
            return True
        if capability == Capability.PACKAGE_EDIT:
            return role >= MEMBER
        if role < MEMBER:
            # Guests never receive execution/review rights, even through grants.
            return False
    elif capability == Capability.PROJECT_READ:
        return True

    return _granted(user, workspace_id, project_id, capability)


def _granted(user, workspace_id, project_id, capability) -> bool:
    qs = CapabilityGrant.objects.filter(
        workspace_id=workspace_id, member=user, capability=capability, deleted_at__isnull=True
    )
    if project_id is None:
        return qs.filter(project__isnull=True).exists()
    # Workspace-wide grant or project grant.
    return qs.filter(project_id__in=[project_id]).exists() or qs.filter(project__isnull=True).exists()


def require_capability(user, workspace_id, project_id, capability):
    if not has_capability(user, workspace_id, project_id, capability):
        raise PermissionDenied(
            f"Missing capability '{capability}'",
            detail={"capability": str(capability)},
        )


def is_extension_enabled(workspace_id, project_id=None) -> bool:
    ws = ExtensionActivation.objects.filter(
        workspace_id=workspace_id, project__isnull=True, deleted_at__isnull=True
    ).first()
    if ws is None or not ws.is_enabled:
        return False
    if project_id is None:
        return True
    proj = ExtensionActivation.objects.filter(
        workspace_id=workspace_id, project_id=project_id, deleted_at__isnull=True
    ).first()
    # Project default follows workspace unless explicitly disabled.
    return proj is None or proj.is_enabled


def require_extension_enabled(workspace_id, project_id=None):
    """Backend policy: disabled extension blocks new extension writes and runs (MIGRATION §6)."""
    if not is_extension_enabled(workspace_id, project_id):
        raise ExtensionDisabled("Project Hub extension is not enabled for this scope")
