# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Hooks on native Plane write paths (FR-B05, FR-B06, FR-B07, FR-I07).

Rules:
* Native title/description change of an approved package -> ``scope_changed``
  flag, events, active runs paused. The run/action gates do *not* depend on
  this hook: they recompute the native source hash synchronously (PF06), so a
  ``QuerySet.update`` that bypasses signals is still caught.
* State or ``is_draft`` changes never create approvals; they are only observed.
* Project archive/delete -> revoke claims, cancel runs. ProjectMember or
  WorkspaceMember deactivation -> revoke that member's claims/runs.

Hooks are cheap (one indexed lookup when no profile exists) and wrapped so
native flows never break because of the extension.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from plane.db.models import Issue, Project, ProjectMember, WorkspaceMember

logger = logging.getLogger("plane.package_flow")

_OLD = "_pf_old_values"


def _safe(fn):
    def wrapper(*args, **kwargs):
        try:
            with transaction.atomic():
                return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - never break native flows
            logger.exception("package_flow native hook %s failed", fn.__name__)
            return None

    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------
@receiver(pre_save, sender=Issue, dispatch_uid="pf_issue_pre_save")
def issue_pre_save(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    try:
        from plane.package_flow.models import PackageProfile

        if not PackageProfile.objects.filter(issue_id=instance.pk, deleted_at__isnull=True).exists():
            return
        old = (
            Issue.all_objects.filter(pk=instance.pk).values("name", "description_html", "state_id", "is_draft").first()
        )
        setattr(instance, _OLD, old)
    except Exception:  # noqa: BLE001
        logger.exception("package_flow issue_pre_save failed")


@receiver(post_save, sender=Issue, dispatch_uid="pf_issue_post_save")
def issue_post_save(sender, instance, created=False, raw=False, **kwargs):
    old = getattr(instance, _OLD, None)
    if raw or created or not old:
        return
    try:
        delattr(instance, _OLD)
    except AttributeError:
        pass
    _handle_issue_change(instance, old)


@_safe
def _handle_issue_change(issue, old):
    from plane.package_flow.models import PackageProfile

    from . import events
    from .execution import pause_runs_for_scope_change
    from .packages import native_source_hash, valid_approval_for

    profile = PackageProfile.objects.filter(issue_id=issue.pk, deleted_at__isnull=True).first()
    if profile is None:
        return
    content_changed = (old.get("name") or "") != (issue.name or "") or (
        (old.get("description_html") or "").strip() != (issue.description_html or "").strip()
    )
    if content_changed:
        new_hash = native_source_hash(issue)
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.pk,
            event_type="native.description.changed",
            aggregate_type="package",
            aggregate_id=issue.pk,
            actor_kind="system",
            actor_id="plane-native",
            payload={"nativeSourceHash": new_hash},
        )
        approval = valid_approval_for(issue, profile)
        if approval is not None and approval.native_source_hash != new_hash:
            flags = list(profile.flags or [])
            if "scope_changed" not in flags:
                flags.append("scope_changed")
                PackageProfile.objects.filter(pk=profile.pk).update(flags=flags)
            paused = pause_runs_for_scope_change(issue.pk, new_hash)
            events.emit(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.pk,
                event_type="package.scope_changed",
                aggregate_type="package",
                aggregate_id=issue.pk,
                actor_kind="system",
                actor_id="plane-native",
                payload={"approvalId": str(approval.id), "pausedRuns": paused},
                summary="Native title/description changed after approval",
            )
    state_changed = str(old.get("state_id")) != str(issue.state_id) or bool(old.get("is_draft")) != bool(issue.is_draft)
    if state_changed:
        # Observation only — a state/draft change is never an execution approval (FR-B05, PF05).
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.pk,
            event_type="native.state.observed",
            aggregate_type="package",
            aggregate_id=issue.pk,
            actor_kind="system",
            actor_id="plane-native",
            payload={
                "stateId": str(issue.state_id) if issue.state_id else None,
                "previousStateId": str(old.get("state_id")) if old.get("state_id") else None,
                "isDraft": bool(issue.is_draft),
            },
        )


# ---------------------------------------------------------------------------
# Project archive / delete
# ---------------------------------------------------------------------------
@receiver(pre_save, sender=Project, dispatch_uid="pf_project_pre_save")
def project_pre_save(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    try:
        old = Project.all_objects.filter(pk=instance.pk).values("archived_at", "deleted_at").first()
        setattr(instance, _OLD, old)
    except Exception:  # noqa: BLE001
        logger.exception("package_flow project_pre_save failed")


@receiver(post_save, sender=Project, dispatch_uid="pf_project_post_save")
def project_post_save(sender, instance, created=False, raw=False, **kwargs):
    old = getattr(instance, _OLD, None)
    if raw or created or not old:
        return
    if old.get("archived_at") is None and instance.archived_at is not None:
        _revoke_project(instance, "project_archived")
    elif old.get("deleted_at") is None and instance.deleted_at is not None:
        _revoke_project(instance, "project_deleted")


@_safe
def _revoke_project(project, reason):
    from .execution import revoke_for_project

    revoke_for_project(project, reason)


# ---------------------------------------------------------------------------
# Membership deactivation
# ---------------------------------------------------------------------------
@receiver(pre_save, sender=ProjectMember, dispatch_uid="pf_project_member_pre_save")
def project_member_pre_save(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    try:
        old = ProjectMember.all_objects.filter(pk=instance.pk).values("is_active", "deleted_at").first()
        setattr(instance, _OLD, old)
    except Exception:  # noqa: BLE001
        logger.exception("package_flow project_member_pre_save failed")


@receiver(post_save, sender=ProjectMember, dispatch_uid="pf_project_member_post_save")
def project_member_post_save(sender, instance, created=False, raw=False, **kwargs):
    old = getattr(instance, _OLD, None)
    if raw or created or not old:
        return
    lost = (old.get("is_active") and not instance.is_active) or (
        old.get("deleted_at") is None and instance.deleted_at is not None
    )
    if lost:
        _revoke_member(instance.member_id, instance.project_id)


@receiver(post_delete, sender=ProjectMember, dispatch_uid="pf_project_member_post_delete")
def project_member_post_delete(sender, instance, **kwargs):
    _revoke_member(instance.member_id, instance.project_id)


@_safe
def _revoke_member(member_id, project_id):
    from plane.db.models import User

    from .execution import revoke_for_member

    project = Project.all_objects.filter(pk=project_id).first()
    user = User.objects.filter(pk=member_id).first()
    if project is not None and user is not None:
        revoke_for_member(user, project)


@receiver(pre_save, sender=WorkspaceMember, dispatch_uid="pf_workspace_member_pre_save")
def workspace_member_pre_save(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    try:
        old = WorkspaceMember.all_objects.filter(pk=instance.pk).values("is_active", "deleted_at").first()
        setattr(instance, _OLD, old)
    except Exception:  # noqa: BLE001
        logger.exception("package_flow workspace_member_pre_save failed")


@receiver(post_save, sender=WorkspaceMember, dispatch_uid="pf_workspace_member_post_save")
def workspace_member_post_save(sender, instance, created=False, raw=False, **kwargs):
    old = getattr(instance, _OLD, None)
    if raw or created or not old:
        return
    lost = (old.get("is_active") and not instance.is_active) or (
        old.get("deleted_at") is None and instance.deleted_at is not None
    )
    if lost:
        _revoke_workspace_member(instance.member_id, instance.workspace_id)


@_safe
def _revoke_workspace_member(member_id, workspace_id):
    from plane.package_flow.models import Claim, ExecutionRun

    project_ids = set(
        Claim.objects.filter(workspace_id=workspace_id, holder_id=member_id, status="active").values_list(
            "project_id", flat=True
        )
    ) | set(
        ExecutionRun.objects.filter(
            workspace_id=workspace_id, responsible_id=member_id, status__in=("queued", "claimed", "running", "waiting")
        ).values_list("project_id", flat=True)
    )
    for project_id in project_ids:
        _revoke_member(member_id, project_id)
