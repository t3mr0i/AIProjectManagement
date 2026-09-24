# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Core package models: activation, capabilities, profile, revisions, approvals.

Requirement refs: FR-W01, FR-W02, FR-W04, FR-W05, FR-W06, FR-W10, FR-B02,
FR-B04, FR-B05, FR-I07, INV-01, INV-03, INV-04.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from plane.db.models.base import BaseModel

from .base import ExtensionBaseModel, IssueScopedModel


class Capability(models.TextChoices):
    """Separately granted business capabilities (PRD §5.2).

    Native Plane roles are *not* equated with run/merge rights.
    """

    PROJECT_READ = "project.read"
    PACKAGE_EDIT = "package.edit"
    PACKAGE_APPROVE_EXECUTION = "package.approve_execution"
    RUN_START = "run.start"
    RUN_CANCEL = "run.cancel"
    REVIEW_APPROVE_CODE = "review.approve_code"
    REVIEW_ACCEPT_OUTCOME = "review.accept_outcome"
    MERGE_REQUEST = "merge.request"
    DECISION_PUBLISH = "decision.publish"
    PROJECT_PLAN = "project.plan"
    INTEGRATION_MANAGE = "integration.manage"
    WORKSPACE_ADMIN = "workspace.admin"


class ExtensionActivation(ExtensionBaseModel):
    """Audited per-workspace/project activation of the extension (FR-B04, §6 Rückfall).

    A row with ``project=None`` is the workspace-level switch. Project rows
    require the workspace switch to be on as well.
    """

    is_enabled = models.BooleanField(default=False)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pf_extension_activations"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "project"],
                condition=Q(deleted_at__isnull=True),
                name="pf_activation_unique_scope",
            ),
            models.UniqueConstraint(
                fields=["workspace"],
                condition=Q(project__isnull=True, deleted_at__isnull=True),
                name="pf_activation_unique_workspace",
            ),
        ]


class CapabilityGrant(ExtensionBaseModel):
    """Grants one capability to a native Plane user in a workspace or project."""

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    capability = models.CharField(max_length=64, choices=Capability.choices)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = "pf_capability_grants"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "project", "member", "capability"],
                condition=Q(deleted_at__isnull=True),
                name="pf_capability_grant_unique",
            )
        ]


class PackageProfile(IssueScopedModel):
    """0..1 package profile on a native Issue. ``workItemId`` == ``issue_id``.

    Title, priority, assignees and planning state stay on the native Issue and
    are *not* copied here (PRD §7.1).
    """

    class ProfileKind(models.TextChoices):
        LIGHT = "light", "Light"
        DEEP = "deep", "Deep"

    class PackageType(models.TextChoices):
        CODE = "code", "Code"
        ANALYSIS = "analysis", "Analysis"
        DESIGN = "design", "Design"
        DECISION = "decision", "Decision"

    class CompletionCriterion(models.TextChoices):
        DELIVERY_AND_ACCEPTANCE = "delivery_and_acceptance", "Confirmed delivery and required acceptance"
        ACCEPTED_DELIVERABLE = "accepted_deliverable", "Accepted non-code deliverable"

    # OneToOne on the native issue guarantees 0..1 (FR-B02, PF02).
    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="package_profile")
    profile_kind = models.CharField(max_length=16, choices=ProfileKind.choices, default=ProfileKind.LIGHT)
    package_type = models.CharField(max_length=16, choices=PackageType.choices, default=PackageType.CODE)
    completion_criterion = models.CharField(
        max_length=32, choices=CompletionCriterion.choices, default=CompletionCriterion.DELIVERY_AND_ACCEPTANCE
    )
    # Working draft fields (editable); snapshots live in PackageRevision.
    intent = models.TextField(blank=True, default="")
    outcome = models.TextField(blank=True, default="")
    non_goals = models.JSONField(default=list, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    criteria = models.JSONField(default=list, blank=True)
    risk = models.JSONField(default=dict, blank=True)
    working_revision = models.ForeignKey(
        "package_flow.PackageRevision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_revision = models.ForeignKey(
        "package_flow.PackageRevision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Monotonic version used for optimistic concurrency on profile edits.
    version = models.PositiveIntegerField(default=1)
    flags = models.JSONField(default=list, blank=True)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = "pf_package_profiles"


class PackageRevision(IssueScopedModel):
    """Immutable content snapshot (schema package-revision 1.1.0).

    Snapshots may historically copy native title etc. They are never edited
    after creation; ``save`` refuses updates.
    """

    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    intent = models.TextField(blank=True, default="")
    outcome = models.TextField(blank=True, default="")
    non_goals = models.JSONField(default=list, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    criteria = models.JSONField(default=list, blank=True)
    decisions = models.JSONField(default=list, blank=True)
    artifacts = models.JSONField(default=list, blank=True)
    # Native source versions that fed this revision (description hash, page versions ...).
    source_versions = models.JSONField(default=dict, blank=True)
    profile_kind = models.CharField(max_length=16, default="light")
    package_type = models.CharField(max_length=16, default="code")
    content_hash = models.CharField(max_length=64, db_index=True)
    based_on = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    origin = models.CharField(max_length=32, default="platform")  # platform | openspec_import | ai_proposal

    class Meta:
        db_table = "pf_package_revisions"
        ordering = ("issue", "number")
        constraints = [models.UniqueConstraint(fields=["issue", "number"], name="pf_revision_unique_number")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("PackageRevision is immutable")
        super().save(*args, **kwargs)


class ExecutionApproval(IssueScopedModel):
    """Server-issued execution authorization (schema execution-authorization 1.1.0).

    Only created by a verified human principal with ``package.approve_execution``.
    Native state/draft changes never create one (FR-B05, INV-03).
    """

    revision = models.ForeignKey(PackageRevision, on_delete=models.PROTECT, related_name="approvals")
    revision_hash = models.CharField(max_length=64)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    policy_version = models.CharField(max_length=64)
    repository_scope = models.JSONField(default=list)
    allowed_actions = models.JSONField(default=list)
    runner_profile = models.ForeignKey(
        "package_flow.RunnerProfile", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    limits = models.JSONField(default=dict)
    # Human-defined checks [{name, command: [argv], trusted}] the runner may execute (run_allowed_checks).
    # REST approval shape + run manifest only; not part of the 1.1.0 JSON-schema contract.
    checks = models.JSONField(default=list, blank=True)
    # Hash of the native issue state (description etc.) at approval time (FR-B06).
    native_source_hash = models.CharField(max_length=64, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    revoke_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pf_execution_approvals"
        ordering = ("-approved_at",)


class ChangeRecord(IssueScopedModel):
    """Small change under an approved package; no sub-issue per tool call (FR-W06)."""

    class Kind(models.TextChoices):
        TECHNICAL_TASK = "technical_task", "Technical task"
        CHANGE = "change", "Change"
        OPENSPEC_CHANGE = "openspec_change", "OpenSpec change"

    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.CHANGE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    revision = models.ForeignKey(PackageRevision, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    status = models.CharField(max_length=16, default="open")  # open | done | dropped
    links = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "pf_change_records"
        ordering = ("created_at",)


class IdempotencyRecord(BaseModel):
    """Stores responses for ``Idempotency-Key`` writes (PRD §12.3, INV-07)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, related_name="+")
    scope = models.CharField(max_length=128)
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict)

    class Meta:
        db_table = "pf_idempotency_records"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "actor", "scope", "key"], name="pf_idempotency_unique")
        ]


class AuditEntry(BaseModel):
    """Append-only audit of critical actions (PRD §15.1, FR-I07)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, null=True, related_name="+")
    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    actor_kind = models.CharField(max_length=16, default="human")  # human | agent | system
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    correlation_id = models.UUIDField(null=True)
    detail = models.JSONField(default=dict)

    class Meta:
        db_table = "pf_audit_entries"
        ordering = ("-created_at",)
