# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Targeted vs. bundled notifications (FR-C07, PRD §15.2).

* ``mention``, ``decision_needed``, ``blocked``, ``review_request`` are
  delivered immediately to the concerned people.
* Ordinary technical events (builds, checks, progress, deployments) are
  bundled into **one** unread digest per recipient and package whose ``count``
  increments — ten successful builds are one digest item, not ten pushes.
* A recipient only receives notifications for projects they can currently
  read; the list endpoint re-checks membership (revocation hides them).
"""

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from plane.db.models import IssueAssignee

from ..capabilities import accessible_project_ids, is_project_member
from ..models import NotificationItem, PackageProfile

logger = logging.getLogger("plane.package_flow.notifications")

IMMEDIATE = {"mention", "decision_needed", "blocked", "review_request"}
TECHNICAL = "technical"

TECHNICAL_EVENTS = {
    "ci.check.observed",
    "run.progress",
    "run.heartbeat",
    "run.started",
    "run.claimed",
    "git.commit.observed",
    "git.merge.observed",
    "deployment.observed",
    "release.observed",
    "native.state.observed",
    "integration.recovered",
    "spec.exported",
    "spec.imported",
}
SILENT_EVENTS = {"run.heartbeat"}


def _can_receive(user_id, project_id):
    from plane.db.models import User

    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is None:
        return None
    if project_id is not None and not is_project_member(user, project_id):
        return None
    return user


def notify(*, recipient_id, workspace_id, category, title, project_id=None, target=None, bundle_key=""):
    """Create an immediate item or bump the recipient's open digest."""
    user = _can_receive(recipient_id, project_id)
    if user is None:
        return None
    target = target or {}
    if category in IMMEDIATE:
        return NotificationItem.objects.create(
            workspace_id=workspace_id,
            project_id=project_id,
            recipient=user,
            category=category,
            delivery="immediate",
            title=title[:500],
            target=target,
        )
    key = bundle_key or f"{TECHNICAL}:{target.get('issue_id') or project_id}"
    with transaction.atomic():
        item = (
            NotificationItem.objects.select_for_update()
            .filter(recipient=user, workspace_id=workspace_id, bundle_key=key, delivery="digest", read_at__isnull=True)
            .first()
        )
        if item is not None:
            NotificationItem.objects.filter(pk=item.pk).update(
                count=F("count") + 1, title=title[:500], updated_at=timezone.now(), target=target
            )
            item.refresh_from_db()
            return item
        return NotificationItem.objects.create(
            workspace_id=workspace_id,
            project_id=project_id,
            recipient=user,
            category=TECHNICAL,
            delivery="digest",
            bundle_key=key,
            count=1,
            title=title[:500],
            target=target,
        )


def package_watchers(issue_id):
    """People concerned with a package: native assignees plus the profile activator."""
    if issue_id is None:
        return set()
    ids = {
        str(u)
        for u in IssueAssignee.objects.filter(issue_id=issue_id, deleted_at__isnull=True).values_list(
            "assignee_id", flat=True
        )
    }
    profile = PackageProfile.objects.filter(issue_id=issue_id).values_list("activated_by_id", "created_by_id").first()
    if profile:
        ids |= {str(x) for x in profile if x}
    return ids


def _event_category(event):
    payload = event.payload or {}
    et = event.event_type
    status = str(payload.get("status") or payload.get("conclusion") or "").lower()
    if et in SILENT_EVENTS:
        return None
    if et == "question.raised":
        return "decision_needed"
    if (
        et in ("run.paused",)
        or payload.get("blocked")
        or (et in ("run.finished", "ci.check.observed") and status in ("blocked", "waiting_for_decision"))
    ):
        return "blocked"
    if et == "run.finished" and status in ("failed", "failure", "error"):
        return "blocked"
    if payload.get("review_requested_ids") or et == "review.invalidated":
        return "review_request"
    if et in TECHNICAL_EVENTS or et.startswith("run.") or et.startswith("ci."):
        return TECHNICAL
    return None


def notify_for_event(event):
    """Derive notifications from a DomainEvent (called from the post_save hook)."""
    category = _event_category(event)
    if category is None:
        return []
    payload = event.payload or {}
    if category == "review_request" and payload.get("review_requested_ids"):
        recipients = {str(x) for x in payload.get("review_requested_ids") or []}
    elif payload.get("recipient_ids"):
        recipients = {str(x) for x in payload["recipient_ids"]}
    else:
        recipients = package_watchers(event.issue_id)
    # The actor does not need to be notified about their own action.
    recipients.discard(str(event.actor_id))
    title = event.summary or event.event_type
    target = {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "issue_id": str(event.issue_id) if event.issue_id else None,
        "project_id": str(event.project_id) if event.project_id else None,
    }
    items = []
    for rid in recipients:
        item = notify(
            recipient_id=rid,
            workspace_id=event.workspace_id,
            project_id=event.project_id,
            category=category,
            title=title,
            target=target,
            bundle_key=f"{TECHNICAL}:{event.issue_id or event.project_id}" if category == TECHNICAL else "",
        )
        if item is not None:
            items.append(item)
    return items


def list_for(user, workspace, *, unread_only=False, limit=100):
    projects = [str(p) for p in accessible_project_ids(user, workspace.id)]
    qs = NotificationItem.objects.filter(recipient=user, workspace=workspace)
    qs = qs.filter(project__isnull=True) | qs.filter(project_id__in=projects)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    return list(qs.order_by("-updated_at")[:limit])


def serialize(item):
    return {
        "id": str(item.id),
        "category": item.category,
        "delivery": item.delivery,
        "count": item.count,
        "title": item.title,
        "project_id": str(item.project_id) if item.project_id else None,
        "target": item.target,
        "read_at": item.read_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
