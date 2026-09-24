# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Thin cross-project planning, activity and notification models.

Native Cycles/Modules/Views/dates stay the planning basis; these tables only
add what the Community baseline does not provide (PLANE_FOUNDATION §2).
Requirement refs: FR-M01..FR-M06, FR-C06, FR-C07, FR-P02..FR-P05, FR-B10.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from plane.db.models.base import BaseModel

from .base import ExtensionBaseModel


class TeamScope(ExtensionBaseModel):
    """Planning scope for the native ``db.Team`` (reused, not duplicated).

    Adds the project/member assignment the Community Team model lacks.
    """

    team = models.OneToOneField("db.Team", on_delete=models.CASCADE, related_name="package_flow_scope")
    members = models.JSONField(default=list, blank=True)  # native user ids
    projects = models.JSONField(default=list, blank=True)  # native project ids

    class Meta:
        db_table = "pf_team_scopes"


class Milestone(ExtensionBaseModel):
    """Project milestone with timezone and owner (FR-C06, FR-M01)."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    target_at = models.DateTimeField(null=True, blank=True)  # stored UTC
    timezone = models.CharField(max_length=64, default="UTC")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=16, default="planned")  # planned | at_risk | done | cancelled
    issues = models.JSONField(default=list, blank=True)  # native issue ids
    # Unknown duration/capacity must not show as reliable date (FR-M04).
    date_confidence = models.CharField(max_length=16, default="unknown")  # confirmed | estimated | unknown

    class Meta:
        db_table = "pf_milestones"
        ordering = ("target_at",)


class PlanningDependency(ExtensionBaseModel):
    """Typed, directed, sourced dependency with confirmation state (FR-M02).

    ``predecessor`` must be finished before ``successor`` (for hard deps).
    Nodes are native issues, milestones or projects.
    """

    class NodeType(models.TextChoices):
        ISSUE = "issue", "Work package"
        MILESTONE = "milestone", "Milestone"
        PROJECT = "project", "Project"

    class Strength(models.TextChoices):
        HARD = "hard", "Hard (blocking)"
        SOFT = "soft", "Soft (informational)"

    class Confirmation(models.TextChoices):
        SUGGESTED = "suggested", "Suggested (unconfirmed)"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    predecessor_type = models.CharField(max_length=16, choices=NodeType.choices)
    predecessor_id = models.UUIDField()
    predecessor_project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+", null=True)
    successor_type = models.CharField(max_length=16, choices=NodeType.choices)
    successor_id = models.UUIDField()
    successor_project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="+", null=True)
    strength = models.CharField(max_length=8, choices=Strength.choices, default=Strength.HARD)
    confirmation = models.CharField(max_length=16, choices=Confirmation.choices, default=Confirmation.SUGGESTED)
    source = models.CharField(max_length=16, default="human")  # human | ai | native_relation | import
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    # Policy: may an anonymous "external prerequisite open" blocker be shown? (PRD §15.2)
    allow_anonymous_blocker = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pf_planning_dependencies"
        constraints = [
            models.UniqueConstraint(
                fields=["predecessor_type", "predecessor_id", "successor_type", "successor_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_dependency_unique",
            )
        ]


class PlanScenario(ExtensionBaseModel):
    """What-if variant; does not change the binding plan until confirmed (FR-M03)."""

    name = models.CharField(max_length=255)
    changes = models.JSONField(default=list)  # [{"type":"milestone","id":..,"target_at":..}]
    impact = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, default="draft")  # draft | applied | discarded
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = "pf_plan_scenarios"


class Risk(ExtensionBaseModel):
    """Project risk with traceable cause (FR-M06)."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    severity = models.CharField(max_length=16, default="medium")
    status = models.CharField(max_length=16, default="open")
    origin = models.CharField(max_length=16, default="human")  # human | automatic
    cause = models.JSONField(default=dict, blank=True)  # {"type":"dependency","id":..}

    class Meta:
        db_table = "pf_risks"


class CalendarEvent(ExtensionBaseModel):
    """Project event with timezone and owner (FR-C06). Export via ICS only."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "pf_calendar_events"
        ordering = ("starts_at",)


class DomainEvent(BaseModel):
    """Transactional outbox + normalized event store (schema domain-event 1.1.0).

    Written in the same DB transaction as the business change (MIGRATION §4).
    ``deduplication_key`` is unique so redelivery never duplicates (INV-07).
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, null=True, related_name="+")
    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, related_name="+")
    event_type = models.CharField(max_length=64, db_index=True)
    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.UUIDField()
    occurred_at = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField()
    correlation_id = models.UUIDField()
    causation_id = models.UUIDField(null=True, blank=True)
    deduplication_key = models.CharField(max_length=255)
    source_kind = models.CharField(max_length=16)  # platform | provider | runner
    source_id = models.CharField(max_length=255)
    source_instance_id = models.CharField(max_length=255)
    actor_kind = models.CharField(max_length=16)  # human | agent | system
    actor_id = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    # Fixture/test events are visibly marked (R0).
    is_fixture = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    summary = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "pf_domain_events"
        ordering = ("-occurred_at",)
        constraints = [
            models.UniqueConstraint(fields=["workspace", "deduplication_key"], name="pf_domain_event_dedup")
        ]


class VisitMarker(BaseModel):
    """Personal "since my last visit" marker; view-only, never project state (J08)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, null=True, related_name="+")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    last_visited_at = models.DateTimeField()
    previous_visited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pf_visit_markers"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "project", "member"],
                condition=Q(deleted_at__isnull=True),
                name="pf_visit_marker_unique",
            )
        ]


class NotificationItem(BaseModel):
    """Targeted vs. bundled notifications (FR-C07)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, null=True, related_name="+")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    category = models.CharField(max_length=32)  # mention | decision_needed | blocked | review_request | technical
    delivery = models.CharField(max_length=16)  # immediate | digest
    bundle_key = models.CharField(max_length=255, blank=True, default="")
    count = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=500)
    target = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pf_notification_items"
        ordering = ("-created_at",)
