# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""ACL-aware search (FR-P06, PRD §15.2, FR-I08, AC14).

Index rows (``SearchDocument``) are derived data: they are hard-deleted with
their source so no hidden copy survives. Queries are always filtered by the
requester's *current* native project memberships and DM participation;
quarantined uploads never match. Responses carry no total count and never
include titles of inaccessible sources.

Native Issues and Pages are searched directly via the ORM filtered by project
membership (no second copy of native content).

Ranking uses Postgres full-text search (``SearchVector``/``SearchRank``, title
weighted above body, ``simple`` config so German and English both work);
``icontains`` stays as fallback for substrings and non-Postgres databases.
Ranking happens strictly *after* the ACL filter, so it can never reveal
hidden rows.
"""

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.db.models import FloatField, Q, Value
from django.utils import timezone

from plane.db.models import Issue, Page

from ..capabilities import accessible_project_ids
from ..models import Conversation, ConversationParticipant, SearchDocument, UploadRecord

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
ALL_TYPES = ("package", "issue", "page", "decision", "message", "upload")


def index_document(
    *,
    workspace_id,
    object_type,
    object_id,
    title,
    body="",
    project_id=None,
    issue_id=None,
    conversation_id=None,
    updated_at=None,
):
    doc = SearchDocument.objects.filter(object_type=object_type, object_id=object_id).first()
    values = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "issue_id": issue_id,
        "conversation_id": conversation_id,
        "title": (title or "")[:500],
        "body": body or "",
        "source_updated_at": updated_at or timezone.now(),
    }
    if doc is None:
        doc = SearchDocument(object_type=object_type, object_id=object_id, **values)
    else:
        for k, v in values.items():
            setattr(doc, k, v)
    doc.save()
    return doc


def remove_document(object_type, object_id) -> int:
    """Hard delete (not soft) — deleted confidential data must not stay searchable (FR-I08)."""
    deleted, _ = SearchDocument.all_objects.filter(object_type=object_type, object_id=object_id).delete()
    return deleted


def index_message(message):
    conv = message.conversation
    return index_document(
        workspace_id=message.workspace_id,
        object_type="message",
        object_id=message.id,
        title=(conv.title or f"{conv.get_kind_display()} message")[:120],
        body=message.body,
        project_id=conv.project_id,
        issue_id=conv.issue_id,
        conversation_id=conv.id,
        updated_at=message.edited_at or message.created_at,
    )


def index_decision(decision):
    return index_document(
        workspace_id=decision.workspace_id,
        object_type="decision",
        object_id=decision.id,
        title=decision.title,
        body=f"{decision.text}\n{decision.rationale}",
        project_id=decision.project_id,
        issue_id=decision.issue_id,
        updated_at=decision.confirmed_at or decision.created_at,
    )


def _snippet(text, q, width=160):
    text = " ".join((text or "").split())
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[:width]
    start = max(0, idx - width // 3)
    return ("…" if start else "") + text[start : start + width]


def _ranked(qs, q, title_field, body_field):
    """ACL-filtered queryset -> matches annotated with ``rank`` (full-text + substring fallback)."""
    substring = Q(**{f"{title_field}__icontains": q}) | Q(**{f"{body_field}__icontains": q})
    if connection.vendor != "postgresql":
        return qs.filter(substring).annotate(rank=Value(0.0, output_field=FloatField()))
    vector = SearchVector(title_field, weight="A", config="simple") + SearchVector(
        body_field, weight="B", config="simple"
    )
    query = SearchQuery(q, search_type="websearch", config="simple")
    return qs.annotate(fts=vector, rank=SearchRank(vector, query)).filter(Q(fts=query) | substring)


def my_dm_conversation_ids(user, workspace_id):
    return list(
        ConversationParticipant.objects.filter(
            member=user,
            is_active=True,
            conversation__workspace_id=workspace_id,
            conversation__kind=Conversation.Kind.DIRECT,
            conversation__deleted_at__isnull=True,
        ).values_list("conversation_id", flat=True)
    )


def search(user, workspace, q, types=None, limit=DEFAULT_LIMIT):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    types = [t for t in (types or ALL_TYPES) if t in ALL_TYPES]
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    projects = accessible_project_ids(user, workspace.id)
    dm_ids = my_dm_conversation_ids(user, workspace.id)
    results = []

    index_types = [t for t in types if t in ("decision", "message", "upload")]
    if index_types:
        acl = (Q(project_id__in=projects) & (Q(conversation__isnull=True) | ~Q(conversation__kind="direct"))) | Q(
            conversation_id__in=dm_ids
        )
        quarantined = (
            UploadRecord.objects.filter(workspace_id=workspace.id)
            .exclude(scan_status=UploadRecord.ScanStatus.CLEAN)
            .values_list("id", flat=True)
        )
        docs = (
            SearchDocument.objects.filter(workspace_id=workspace.id, object_type__in=index_types)
            .filter(acl)
            .exclude(object_type="upload", object_id__in=quarantined)
            .exclude(issue__deleted_at__isnull=False)
        )
        docs = _ranked(docs, q, "title", "body").order_by("-rank", "-source_updated_at")[:limit]
        for d in docs:
            results.append(
                {
                    "type": d.object_type,
                    "id": str(d.object_id),
                    "title": d.title,
                    "snippet": _snippet(d.body, q),
                    "project_id": str(d.project_id) if d.project_id else None,
                    "issue_id": str(d.issue_id) if d.issue_id else None,
                    "conversation_id": str(d.conversation_id) if d.conversation_id else None,
                    "source": "package_flow",
                    "updated_at": d.source_updated_at,
                    "rank": float(d.rank or 0),
                }
            )

    if "issue" in types or "package" in types:
        issues = Issue.objects.filter(
            workspace_id=workspace.id, project_id__in=projects, project__deleted_at__isnull=True
        ).select_related("project")
        issues = _ranked(issues, q, "name", "description_stripped").order_by("-rank", "-updated_at")[:limit]
        for i in issues:
            has_profile = hasattr(i, "package_profile")
            results.append(
                {
                    "type": "package" if has_profile else "issue",
                    "id": str(i.id),
                    "title": i.name,
                    "snippet": _snippet(i.description_stripped or "", q),
                    "project_id": str(i.project_id),
                    "issue_id": str(i.id),
                    "identifier": f"{i.project.identifier}-{i.sequence_id}",
                    "source": "plane",
                    "updated_at": i.updated_at,
                    "rank": float(i.rank or 0),
                }
            )

    if "page" in types:
        page_ids = (
            Page.objects.filter(
                workspace_id=workspace.id,
                project_pages__project_id__in=projects,
                project_pages__deleted_at__isnull=True,
                archived_at__isnull=True,
            )
            .filter(Q(access=0) | Q(owned_by=user))
            .values("id")
        )
        pages = _ranked(Page.objects.filter(id__in=page_ids), q, "name", "description_stripped").order_by(
            "-rank", "-updated_at"
        )[:limit]
        for p in pages:
            pp = p.project_pages.filter(project_id__in=projects).first()
            results.append(
                {
                    "type": "page",
                    "id": str(p.id),
                    "title": p.name,
                    "snippet": _snippet(p.description_stripped or "", q),
                    "project_id": str(pp.project_id) if pp else None,
                    "source": "plane",
                    "updated_at": p.updated_at,
                    "rank": float(p.rank or 0),
                }
            )

    results.sort(key=lambda r: (r["rank"], r["updated_at"] or timezone.now()), reverse=True)
    return results[:limit]
