# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI usage metering: every AI call is recorded with provider, model, real token usage and outcome."""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from ..models import AIUsageRecord


def meta_for(*, workspace_id, user=None, project_id=None, feature=""):
    """``meta`` argument for :class:`AIProvider` calls."""
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "user_id": getattr(user, "id", None),
        "feature": feature,
    }


def record_usage(meta, *, task, provider, model, status, usage, duration_ms, error_code=""):
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    estimated = not input_tokens and not output_tokens
    if estimated:
        input_tokens = int(usage.get("input_tokens_estimate") or 0)
    return AIUsageRecord.objects.create(
        workspace_id=meta["workspace_id"],
        project_id=meta.get("project_id") or None,
        user_id=meta.get("user_id") or None,
        task=task,
        feature=(meta.get("feature") or "")[:64],
        provider=(provider or "")[:32],
        model=(model or "")[:128],
        status=(status or "")[:32],
        error_code=(error_code or "")[:64],
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        estimated=estimated,
        duration_ms=max(0, int(duration_ms or 0)),
    )


def summary(workspace_id, *, days=30):
    """Aggregates for the workspace AI usage view."""
    days = max(1, min(int(days or 30), 365))
    since = timezone.now() - timedelta(days=days)
    qs = AIUsageRecord.objects.filter(workspace_id=workspace_id, created_at__gte=since)
    totals = qs.aggregate(calls=Count("id"), input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"))

    def grouped(field):
        rows = (
            qs.values(field)
            .annotate(calls=Count("id"), input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"))
            .order_by("-calls")
        )
        return [
            {
                "key": r[field] or "",
                "calls": r["calls"],
                "input_tokens": r["input_tokens"] or 0,
                "output_tokens": r["output_tokens"] or 0,
            }
            for r in rows
        ]

    return {
        "days": days,
        "calls": totals["calls"] or 0,
        "input_tokens": totals["input_tokens"] or 0,
        "output_tokens": totals["output_tokens"] or 0,
        "errors": qs.exclude(status="ok").count(),
        "by_feature": grouped("feature"),
        "by_task": grouped("task"),
        "by_model": grouped("model"),
    }
