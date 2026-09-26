# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI core data: usage metering and the semantic retrieval index.

Both are derived data. Embeddings are hard-deleted with their source (like
``SearchDocument``) so no hidden copy of confidential text survives (FR-I08).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from .base import ExtensionBaseModel


class AIUsageRecord(ExtensionBaseModel):
    """One AI call: who, what feature, which provider/model, real token usage and outcome."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    task = models.CharField(max_length=32)  # concretize | interpret | report | answer | assist | embed
    feature = models.CharField(max_length=64, blank=True, default="")  # e.g. chat_mention, editor_assist
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=32)
    error_code = models.CharField(max_length=64, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    estimated = models.BooleanField(default=False)  # True when the provider reported no usage
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "pf_ai_usage"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["workspace", "created_at"], name="pf_ai_usage_ws_created")]


class AIEmbedding(ExtensionBaseModel):
    """Vector of one indexed source for semantic retrieval (ACL is re-checked at query time)."""

    object_type = models.CharField(max_length=32)  # issue | decision | page | message | upload
    object_id = models.UUIDField()
    model = models.CharField(max_length=128)
    content_hash = models.CharField(max_length=64)
    vector = models.JSONField(default=list)

    class Meta:
        db_table = "pf_ai_embeddings"
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "object_id"],
                condition=Q(deleted_at__isnull=True),
                name="pf_ai_embedding_unique",
            )
        ]
        indexes = [models.Index(fields=["workspace", "object_type"], name="pf_ai_embedding_ws_type")]
