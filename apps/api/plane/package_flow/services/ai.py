# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI features of the product, built on the central AI core (``package_flow.ai``).

Every feature follows the same pipeline:

1. collect the explicit selection, implicit context and retrieved sources,
2. check every source against requester *and* audience (``assemble_context``),
3. call the configured provider with timeout, budget and usage metering,
4. return labelled statements; anything that would change data becomes a
   pending ``AIProposal`` that only a human can accept.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from plane.db.models import Issue

from ..ai import retrieval
from ..ai.config import load_config
from ..ai.context import assemble_context, projects_audience
from ..ai.provider import get_provider
from ..ai.usage import meta_for
from ..models import AIProposal, Decision, ExecutionRun, PackageProfile
from .packages import _clean_criteria

REPORT_ISSUE_LIMIT = 15
REPORT_DECISION_LIMIT = 10


def status():
    """What the UI may know about the configured AI (never the key)."""
    config = load_config()
    data = config.public()
    data["mode"] = "llm" if config.is_configured else "rule_based"
    data["features"] = {
        "ask": True,
        "proposals": True,
        "report": True,
        "assist": config.is_configured,
        "streaming": config.is_configured,
        "semantic_search": config.supports_embeddings,
    }
    return data


def _selection_with_retrieval(user, workspace, question, project_ids, selection, *, limit=6):
    selection = list(selection or [])
    retrieved = retrieval.retrieve(user, workspace, question, project_ids=project_ids, limit=limit, exclude=selection)
    return selection + retrieved, retrieved


# -- proposals: concretize / interpret / report / answer on a package ---------------------------


def request_proposal(user, project, *, task, issue=None, selection=None, instruction="", use_retrieval=True):
    selection = list(selection or [])
    if issue is not None:
        selection.insert(0, {"type": "issue", "id": str(issue.id)})
    retrieved = []
    query = " ".join(filter(None, [instruction, issue.name if issue is not None else ""]))
    if use_retrieval and query:
        selection, retrieved = _selection_with_retrieval(user, project.workspace, query, [project.id], selection)
    ctx = assemble_context(
        requester=user,
        workspace_id=project.workspace_id,
        audience_ids=projects_audience([project.id]),
        selection=selection,
    )
    result = get_provider().complete(
        task,
        [{"role": "user", "content": instruction or ""}] + ctx.provider_messages(),
        meta=meta_for(workspace_id=project.workspace_id, user=user, project_id=project.id, feature=f"proposal_{task}"),
    )
    patch, base_version = {}, ""
    profile = PackageProfile.objects.filter(issue=issue).first() if issue is not None else None
    if result.ok and result.patch and profile is not None:
        patch = dict(result.patch)
        if "criteria" in patch:
            # New criteria are appended to the existing ones, with stable ids.
            patch["criteria"] = _clean_criteria(list(profile.criteria or []) + patch["criteria"], profile.criteria)
        base_version = str(profile.version)
    proposal = AIProposal.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        issue=issue,
        kind=AIProposal.Kind.DRAFT_EDIT if task == "concretize" else AIProposal.Kind.ANSWER,
        requested_by=user,
        content={
            "task": task,
            "instruction": instruction,
            "result": result.as_dict(),
            "statements": [{"text": s.text, "status": s.status, "sources": s.sources} for s in result.statements],
            "patch": patch,
            "context": ctx.as_dict(),
            "retrieved": retrieved,
        },
        selection={"items": selection},
        sources=[a["ref"] for a in ctx.allowed],
        base_version=base_version,
    )
    return proposal, result


# -- workspace Q&A ("Ask AI") --------------------------------------------------------------------


def ask(user, workspace, question, *, project_ids=None, selection=None):
    """Private answer for the requester: context limited to what *they* can read."""
    selection, retrieved = _selection_with_retrieval(user, workspace, question, project_ids, selection, limit=8)
    ctx = assemble_context(requester=user, workspace_id=workspace.id, audience_ids=[user.id], selection=selection)
    result = get_provider().complete(
        "answer",
        [{"role": "user", "content": question}] + ctx.provider_messages(),
        meta=meta_for(workspace_id=workspace.id, user=user, feature="ask"),
    )
    return {
        "question": question,
        "result": result.as_dict(),
        "context": ctx.as_dict(),
        "retrieved": retrieved,
    }


# -- project status report --------------------------------------------------------------------------


def _project_snapshot(project):
    """Aggregated, member-readable facts about the project (no private content)."""
    now = timezone.now()
    issues = Issue.objects.filter(project=project, deleted_at__isnull=True, archived_at__isnull=True)
    groups = {row["state__group"] or "none": row["n"] for row in issues.values("state__group").annotate(n=Count("id"))}
    overdue = issues.filter(target_date__lt=now.date()).exclude(state__group__in=["completed", "cancelled"]).count()
    week = now - timedelta(days=7)
    runs = ExecutionRun.objects.filter(project=project, created_at__gte=now - timedelta(days=30))
    run_status = {row["status"]: row["n"] for row in runs.values("status").annotate(n=Count("id"))}
    lines = [
        f"Project {project.identifier} — {project.name}",
        "Work items by state group: " + ", ".join(f"{k}={v}" for k, v in sorted(groups.items())),
        f"Overdue open work items: {overdue}",
        f"Work items updated in the last 7 days: {issues.filter(updated_at__gte=week).count()}",
        f"Completed in the last 7 days: {issues.filter(completed_at__gte=week).count()}",
        "Execution runs (30 days) by status: "
        + (", ".join(f"{k}={v}" for k, v in sorted(run_status.items())) or "none"),
        "Package drafts without approved revision: "
        + str(PackageProfile.objects.filter(project=project, approved_revision__isnull=True).count()),
    ]
    return "\n".join(lines)


def report_selection(project):
    recent = (
        Issue.objects.filter(project=project, deleted_at__isnull=True, archived_at__isnull=True)
        .filter(Q(package_profile__isnull=False) | Q(priority__in=["urgent", "high"]))
        .order_by("-updated_at")[:REPORT_ISSUE_LIMIT]
    )
    decisions = Decision.objects.filter(project=project, status=Decision.Status.CONFIRMED).order_by("-confirmed_at")[
        :REPORT_DECISION_LIMIT
    ]
    return [{"type": "issue", "id": str(i.id)} for i in recent] + [
        {"type": "decision", "id": str(d.id)} for d in decisions
    ]


def project_report(user, project, *, instruction=""):
    ctx = assemble_context(
        requester=user,
        workspace_id=project.workspace_id,
        audience_ids=projects_audience([project.id]),
        selection=report_selection(project),
    )
    snapshot = {
        "role": "context",
        "content": _project_snapshot(project),
        "source": {"type": "project", "id": str(project.id)},
    }
    request = instruction or "Write the current project status report."
    result = get_provider().complete(
        "report",
        [{"role": "user", "content": request}, snapshot] + ctx.provider_messages(),
        meta=meta_for(workspace_id=project.workspace_id, user=user, project_id=project.id, feature="project_report"),
    )
    proposal = AIProposal.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        kind=AIProposal.Kind.ANSWER,
        requested_by=user,
        content={
            "task": "report",
            "instruction": request,
            "result": result.as_dict(),
            "statements": [{"text": s.text, "status": s.status, "sources": s.sources} for s in result.statements],
            "patch": {},
            "context": ctx.as_dict(),
            "snapshot": snapshot["content"],
        },
        selection={"items": report_selection(project)},
        sources=[a["ref"] for a in ctx.allowed],
    )
    return proposal, result


# -- editor writing help -----------------------------------------------------------------------------


def assist(user, workspace, *, instruction, text="", project_id=None, feature="editor_assist"):
    return get_provider().generate_text(
        instruction,
        text,
        meta=meta_for(workspace_id=workspace.id, user=user, project_id=project_id, feature=feature),
    )


def assist_stream(user, workspace, *, instruction, text="", project_id=None, feature="editor_assist_stream"):
    return get_provider().stream_text(
        instruction,
        text,
        meta=meta_for(workspace_id=workspace.id, user=user, project_id=project_id, feature=feature),
    )
