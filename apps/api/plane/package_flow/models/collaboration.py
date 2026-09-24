# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Conversation, decision, AI-proposal, diagram and knowledge models.

Requirement refs: FR-C01..FR-C07, FR-E02..FR-E06, FR-W03, FR-W07, FR-P06,
FR-I08, FR-B09.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from plane.db.models.base import BaseModel

from .base import ExtensionBaseModel


class Conversation(ExtensionBaseModel):
    """Project chat, package thread or private DM with explicit participants.

    A package thread is bound to the native Issue so it is reachable both from
    the package and the chat without duplicating the conversation (FR-C01).
    """

    class Kind(models.TextChoices):
        PROJECT = "project", "Project channel"
        PACKAGE = "package", "Package thread"
        DIRECT = "direct", "Direct message"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    title = models.CharField(max_length=255, blank=True, default="")
    # Stable key for DMs (sorted user ids) to avoid duplicates.
    dm_key = models.CharField(max_length=128, blank=True, default="")
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "pf_conversations"
        constraints = [
            models.UniqueConstraint(
                fields=["issue"],
                condition=Q(kind="package", deleted_at__isnull=True),
                name="pf_one_thread_per_package",
            ),
            models.UniqueConstraint(
                fields=["workspace", "dm_key"],
                condition=Q(kind="direct", deleted_at__isnull=True),
                name="pf_one_dm_per_pair",
            ),
        ]


class ConversationParticipant(BaseModel):
    """Explicit participant; admins do not implicitly read DMs (PRD §5.2)."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    last_read_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "pf_conversation_participants"
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "member"],
                condition=Q(deleted_at__isnull=True),
                name="pf_participant_unique",
            )
        ]


class Message(BaseModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    author_kind = models.CharField(max_length=16, default="human")  # human | ai | system
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    body = models.TextField()
    version = models.PositiveIntegerField(default=1)
    mentions = models.JSONField(default=list, blank=True)
    source_links = models.JSONField(default=list, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    # For AI answers: which sources were used and the audience check result (FR-C02).
    ai_context = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pf_messages"
        ordering = ("created_at",)


class MessageVersion(BaseModel):
    """Every prior message body is kept so decisions can reference exact versions (FR-C04)."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    body = models.TextField()

    class Meta:
        db_table = "pf_message_versions"
        constraints = [models.UniqueConstraint(fields=["message", "version"], name="pf_message_version_unique")]


class Decision(ExtensionBaseModel):
    """Versioned confirmed decision with source snapshot (FR-C03, FR-C04)."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFIRMED = "confirmed", "Confirmed"
        SUPERSEDED = "superseded", "Superseded"
        WITHDRAWN = "withdrawn", "Withdrawn"

    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    title = models.CharField(max_length=255)
    text = models.TextField()
    rationale = models.TextField(blank=True, default="")
    scope = models.CharField(max_length=32, default="package")  # package | project | workspace
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Immutable snapshot of the selected message versions / sources.
    source_snapshot = models.JSONField(default=list, blank=True)
    source_conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, related_name="+")
    audience = models.CharField(max_length=16, default="project")  # project | participants
    supersedes = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    risk_level = models.CharField(max_length=16, blank=True, default="")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    kind = models.CharField(max_length=32, default="decision")  # decision | open_question

    class Meta:
        db_table = "pf_decisions"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"],
                condition=Q(deleted_at__isnull=True) & ~Q(idempotency_key=""),
                name="pf_decision_idempotent",
            )
        ]


class AIProposal(ExtensionBaseModel):
    """Reviewable AI output — never applied until a human accepts (FR-E06, FR-W03, FR-E03)."""

    class Kind(models.TextChoices):
        CLARIFICATION = "clarification", "Clarification question"
        DRAFT_EDIT = "draft_edit", "Draft edit"
        DIAGRAM_INTERPRETATION = "diagram_interpretation", "Diagram interpretation"
        DECISION_PREVIEW = "decision_preview", "Decision preview"
        PRIORITY_SUGGESTION = "priority_suggestion", "Priority suggestion"
        DEPENDENCY_SUGGESTION = "dependency_suggestion", "Dependency suggestion"
        ANSWER = "answer", "Answer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        STALE = "stale", "Stale"

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    # observed | confirmed | inferred | proposed per statement (PRD §14.2)
    content = models.JSONField(default=dict)
    selection = models.JSONField(default=dict, blank=True)
    sources = models.JSONField(default=list, blank=True)
    base_version = models.CharField(max_length=64, blank=True, default="")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pf_ai_proposals"
        ordering = ("-created_at",)


class ClarificationSession(ExtensionBaseModel):
    """Moderate Grill-Me-inspired clarification (FR-W03, PRD §14.3)."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=16, default="active")  # active | checkpoint | closed
    turns = models.JSONField(default=list, blank=True)
    questions_asked = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "pf_clarification_sessions"


class DiagramDocument(ExtensionBaseModel):
    """Structured diagram (nodes, edges, properties) with separate layout (FR-E02)."""

    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    page = models.ForeignKey("db.Page", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    name = models.CharField(max_length=255)
    diagram_type = models.CharField(max_length=32, default="architecture")
    semantic = models.JSONField(default=dict)  # {"nodes": [...], "edges": [...]}
    layout = models.JSONField(default=dict)  # {"nodeId": {"x":..,"y":..}}
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "pf_diagram_documents"


class DiagramVersion(BaseModel):
    diagram = models.ForeignKey(DiagramDocument, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    semantic = models.JSONField(default=dict)
    layout = models.JSONField(default=dict)
    semantic_diff = models.JSONField(default=dict, blank=True)
    layout_only = models.BooleanField(default=False)
    proposal = models.ForeignKey(AIProposal, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        db_table = "pf_diagram_versions"
        constraints = [models.UniqueConstraint(fields=["diagram", "version"], name="pf_diagram_version_unique")]


class UploadRecord(ExtensionBaseModel):
    """Security/format state for a native FileAsset (FR-C05, FR-E04). No second file store."""

    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        QUARANTINED = "quarantined", "Quarantined"
        FAILED = "failed", "Failed"

    class FormatSupport(models.TextChoices):
        NATIVE_EDIT = "native_edit", "Natively editable"
        COMMENT = "comment", "Commentable"
        PREVIEW = "preview", "Preview only"
        DOWNLOAD = "download", "Download only"

    asset = models.OneToOneField("db.FileAsset", on_delete=models.CASCADE, related_name="package_flow_upload")
    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    declared_mime = models.CharField(max_length=255, blank=True, default="")
    detected_mime = models.CharField(max_length=255, blank=True, default="")
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    scan_detail = models.CharField(max_length=500, blank=True, default="")
    format_support = models.CharField(max_length=16, choices=FormatSupport.choices, default=FormatSupport.DOWNLOAD)
    extracted_text = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pf_upload_records"


class SearchDocument(ExtensionBaseModel):
    """ACL-aware search index row; derived data deleted with its source (FR-P06, FR-I08)."""

    object_type = models.CharField(max_length=32)  # package | decision | page | message | event | upload
    object_id = models.UUIDField()
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    title = models.CharField(max_length=500)
    body = models.TextField(blank=True, default="")
    source_updated_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "pf_search_documents"
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "object_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_search_document_unique",
            )
        ]


class RetentionPolicy(ExtensionBaseModel):
    """Separate retention per category (PRD §15.3, FR-I08)."""

    category = models.CharField(max_length=32)  # messages | audit | run_logs | raw_events | ai_outputs | exports
    retain_days = models.PositiveIntegerField(null=True, blank=True)  # None = keep

    class Meta:
        db_table = "pf_retention_policies"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "category"],
                condition=Q(deleted_at__isnull=True),
                name="pf_retention_unique",
            )
        ]


class ExportJob(ExtensionBaseModel):
    """Structured, ACL-filtered export bundle (FR-I06). Subject to ``exports`` retention (FR-I08)."""

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    scope = models.JSONField(default=dict)  # {"project_ids": [...], "include": [...]}
    status = models.CharField(max_length=16, default="completed")  # completed | failed
    content = models.JSONField(default=dict, blank=True)
    contains_private = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "pf_export_jobs"
        ordering = ("-created_at",)
