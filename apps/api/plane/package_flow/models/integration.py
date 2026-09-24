# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Integration, repository, review, evidence and delivery models.

Requirement refs: FR-G01, FR-G08, FR-G09, FR-G10, FR-R01..FR-R06, FR-I02..FR-I06,
FR-B10, FR-B11, INV-05, INV-07, INV-08.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from plane.db.models.base import BaseModel

from .base import ExtensionBaseModel, IssueScopedModel


class Provider(models.TextChoices):
    GITLAB = "gitlab", "GitLab"
    JIRA = "jira", "Jira"
    LINEAR = "linear", "Linear"
    AZURE_DEVOPS = "azure_devops", "Azure DevOps"
    GENERIC_GIT = "generic_git", "Generic Git"
    GITHUB = "github", "GitHub"


class IntegrationConnection(ExtensionBaseModel):
    """A provider *instance* connection for a workspace (FR-I02, FR-I05)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DEGRADED = "degraded", "Degraded"
        OFFLINE = "offline", "Offline"
        DISABLED = "disabled", "Disabled"

    provider = models.CharField(max_length=32, choices=Provider.choices)
    instance_url = models.URLField(max_length=500)
    instance_type = models.CharField(max_length=32, default="cloud")  # cloud | self_managed | server
    edition = models.CharField(max_length=64, blank=True, default="")
    display_name = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    capabilities = models.JSONField(default=dict, blank=True)
    # Webhook secret is stored hashed/encrypted-at-rest by the service; never returned.
    webhook_secret = models.CharField(max_length=255, blank=True, default="")
    credential_ref = models.CharField(max_length=255, blank=True, default="")
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    backlog_count = models.PositiveIntegerField(default=0)
    sync_cursor = models.JSONField(default=dict, blank=True)
    field_ownership = models.JSONField(default=dict, blank=True)  # {"priority": "external", ...}

    class Meta:
        db_table = "pf_integration_connections"


class RepositoryBinding(ExtensionBaseModel):
    """Provider instance + external repo id bound to a native Plane project (FR-G01)."""

    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="repositories")
    external_id = models.CharField(max_length=255)
    path_with_namespace = models.CharField(max_length=500)
    default_branch = models.CharField(max_length=255, default="main")
    branch_rules = models.JSONField(default=dict, blank=True)
    capabilities = models.JSONField(default=dict, blank=True)
    role = models.CharField(max_length=64, blank=True, default="")  # e.g. backend / frontend
    specs_branch = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    observed_commit = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "pf_repository_bindings"
        constraints = [
            # Identity is instance + external id, never the repo name (FR-G01).
            models.UniqueConstraint(
                fields=["project", "connection", "external_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_repo_binding_unique",
            )
        ]


class ExternalLink(IssueScopedModel):
    """Maps a native Issue to any number of external objects (PRD §7.1 ExternalLink)."""

    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="links")
    object_type = models.CharField(max_length=64)  # issue | merge_request | branch | commit | pipeline
    external_id = models.CharField(max_length=255)
    external_key = models.CharField(max_length=255, blank=True, default="")
    url = models.URLField(max_length=1000, blank=True, default="")
    represents_package = models.BooleanField(default=False)
    field_ownership = models.JSONField(default=dict, blank=True)
    observed_fields = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_state = models.CharField(max_length=16, default="ok")  # ok | conflict | stale | disconnected

    class Meta:
        db_table = "pf_external_links"
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "object_type", "external_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_external_link_unique",
            )
        ]


class SyncConflict(IssueScopedModel):
    """Concurrent edit conflict naming both values, sources and times (PRD §12.3)."""

    link = models.ForeignKey(ExternalLink, on_delete=models.CASCADE, related_name="conflicts", null=True)
    field = models.CharField(max_length=64)
    platform_value = models.JSONField(null=True)
    external_value = models.JSONField(null=True)
    platform_changed_at = models.DateTimeField(null=True)
    external_changed_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=16, default="open")  # open | resolved
    resolution = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "pf_sync_conflicts"


class InboundEvent(BaseModel):
    """Durably accepted provider webhook (FR-I04). Ack only after this row exists."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"
        DUPLICATE = "duplicate", "Duplicate"

    connection = models.ForeignKey(IntegrationConnection, on_delete=models.CASCADE, related_name="inbound_events")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    external_event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=128)
    occurred_at = models.DateTimeField(null=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    attempts = models.PositiveIntegerField(default=0)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pf_inbound_events"
        constraints = [
            # connection instance + external event id is the dedup key (MIGRATION §4).
            models.UniqueConstraint(fields=["connection", "external_event_id"], name="pf_inbound_event_dedup")
        ]


class MergeRequestLink(IssueScopedModel):
    """Merge/pull request correlated to a package (FR-G08, FR-G09)."""

    repository_binding = models.ForeignKey(RepositoryBinding, on_delete=models.CASCADE, related_name="merge_requests")
    external_id = models.CharField(max_length=255)
    title = models.CharField(max_length=500, blank=True, default="")
    url = models.URLField(max_length=1000, blank=True, default="")
    source_branch = models.CharField(max_length=255)
    target_branch = models.CharField(max_length=255)
    head_sha = models.CharField(max_length=64, blank=True, default="")
    target_sha = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=16, default="open")  # open | merged | closed
    merged_commit_sha = models.CharField(max_length=64, blank=True, default="")
    merge_method = models.CharField(max_length=16, blank=True, default="")  # merge | squash | rebase
    commits = models.JSONField(default=list, blank=True)
    run = models.ForeignKey("package_flow.ExecutionRun", on_delete=models.SET_NULL, null=True, related_name="+")
    last_event_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pf_merge_request_links"
        constraints = [
            models.UniqueConstraint(
                fields=["repository_binding", "external_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_mr_link_unique",
            )
        ]


class Evidence(IssueScopedModel):
    """Evidence with source, commit/artifact ref, time and trust class (FR-R02)."""

    class Trust(models.TextChoices):
        LOCAL_SELF_REPORT = "local_self_report", "Local self report"
        RUNNER_REPORTED = "runner_reported", "Runner reported"
        PROVIDER_CI = "provider_ci", "Provider-confirmed CI"
        HUMAN = "human", "Human confirmation"

    class Result(models.TextChoices):
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        NOT_RUN = "not_run", "Not run"
        UNKNOWN = "unknown", "Unknown"

    kind = models.CharField(max_length=32)  # test | lint | build | review_note | document
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=128)
    trust = models.CharField(max_length=32, choices=Trust.choices)
    result = models.CharField(max_length=16, choices=Result.choices, default=Result.UNKNOWN)
    repository_binding = models.ForeignKey(RepositoryBinding, on_delete=models.SET_NULL, null=True, related_name="+")
    commit_sha = models.CharField(max_length=64, blank=True, default="")
    artifact_ref = models.CharField(max_length=500, blank=True, default="")
    criterion_ids = models.JSONField(default=list, blank=True)
    run = models.ForeignKey("package_flow.ExecutionRun", on_delete=models.SET_NULL, null=True, related_name="+")
    occurred_at = models.DateTimeField()
    url = models.URLField(max_length=1000, blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_evidence"
        ordering = ("-occurred_at",)


class ReviewApproval(IssueScopedModel):
    """Human review bound to exact head/revision/policy (FR-R03, FR-R04, INV-05)."""

    class Kind(models.TextChoices):
        CODE = "code", "Technical code review"
        OUTCOME = "outcome", "Business outcome acceptance"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    revision = models.ForeignKey("package_flow.PackageRevision", on_delete=models.PROTECT, related_name="+")
    merge_request = models.ForeignKey(MergeRequestLink, on_delete=models.CASCADE, null=True, related_name="reviews")
    head_sha = models.CharField(max_length=64, blank=True, default="")
    target_sha = models.CharField(max_length=64, blank=True, default="")
    policy_version = models.CharField(max_length=64)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=16, default="approved")  # approved | changes_requested
    comment = models.TextField(blank=True, default="")
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidated_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "pf_review_approvals"
        ordering = ("-created_at",)


class Delivery(IssueScopedModel):
    """Delivery chain entry per repository/environment (FR-R05, FR-R06).

    History is append-only; a rollback is a new row, never a deletion.
    """

    class Stage(models.TextChoices):
        INTEGRATED = "integrated", "Integrated"
        ARTIFACT_BUILT = "artifact_built", "Artifact built"
        DEPLOYED = "deployed", "Deployed"
        RELEASED = "released", "Released"
        ROLLED_BACK = "rolled_back", "Rolled back"

    repository_binding = models.ForeignKey(RepositoryBinding, on_delete=models.SET_NULL, null=True, related_name="+")
    stage = models.CharField(max_length=16, choices=Stage.choices)
    commit_sha = models.CharField(max_length=64, blank=True, default="")
    artifact_ref = models.CharField(max_length=500, blank=True, default="")
    environment = models.CharField(max_length=128, blank=True, default="")
    source = models.CharField(max_length=128)
    trust = models.CharField(max_length=32, default="provider")
    occurred_at = models.DateTimeField()
    reverts = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_deliveries"
        ordering = ("occurred_at",)


class SpecSyncState(IssueScopedModel):
    """OpenSpec roundtrip state per package/repository (FR-W08, FR-G02, PRD §12.4)."""

    repository_binding = models.ForeignKey(RepositoryBinding, on_delete=models.CASCADE, null=True, related_name="+")
    spec_path = models.CharField(max_length=500)
    base_commit = models.CharField(max_length=64, blank=True, default="")
    base_content = models.TextField(blank=True, default="")
    platform_content = models.TextField(blank=True, default="")
    git_content = models.TextField(blank=True, default="")
    published_revision = models.ForeignKey(
        "package_flow.PackageRevision", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    published_commit = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=16, default="clean")  # clean | ahead | behind | conflict
    conflict = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_spec_sync_states"
