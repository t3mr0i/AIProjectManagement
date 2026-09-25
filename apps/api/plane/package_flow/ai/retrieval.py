# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Retrieval-augmented context: find the sources that matter for a question.

* With an embedding-capable provider, sources are ranked by cosine similarity
  of their stored vectors (``AIEmbedding``) to the question.
* Always blended with ACL-aware full-text search, so retrieval also works with
  Anthropic (no embeddings API) or the offline provider.

Retrieval only *suggests* references. Every reference still goes through
:func:`assemble_context`, which enforces requester and audience rights —
retrieval can never widen what the AI may read (FR-C02, AC12). Private DM
messages are never embedded.
"""

import hashlib
import logging
import math

from plane.db.models import Issue, Page

from ..capabilities import accessible_project_ids
from ..models import AIEmbedding, Conversation, Decision, Message, UploadRecord
from .context import strip_html
from .provider import AIProvider, get_provider, keywords

logger = logging.getLogger("plane.package_flow.ai")

MAX_EMBED_CHARS = 6000
EMBED_BATCH = 32
MIN_SIMILARITY = 0.25
MAX_CANDIDATES = 5000
TYPE_MAP = {
    "package": "issue",
    "issue": "issue",
    "decision": "decision",
    "message": "message",
    "upload": "upload",
    "page": "page",
}


# -- source text --------------------------------------------------------------------------


def _issue_text(issue):
    text = f"{issue.name}\n{issue.description_stripped or strip_html(issue.description_html)}"
    profile = getattr(issue, "package_profile", None)
    if profile is not None and profile.deleted_at is None:
        crit = "; ".join(str(c.get("text", "")) for c in profile.criteria or [] if isinstance(c, dict))
        text += f"\nOutcome: {profile.outcome}\nIntent: {profile.intent}\nCriteria: {crit}"
    return text


def iter_sources(workspace_id, *, since=None, project_ids=None):
    """Yield ``(object_type, id, project_id, text)`` for every embeddable source."""

    def scoped(qs, field="updated_at", project_field="project_id"):
        qs = qs.filter(workspace_id=workspace_id)
        if since is not None:
            qs = qs.filter(**{f"{field}__gte": since})
        if project_ids is not None:
            qs = qs.filter(**{f"{project_field}__in": list(project_ids)})
        return qs

    for issue in scoped(Issue.objects.filter(project__deleted_at__isnull=True)).select_related("package_profile"):
        yield "issue", issue.id, issue.project_id, _issue_text(issue)
    for dec in scoped(Decision.objects.filter(project__isnull=False)):
        yield "decision", dec.id, dec.project_id, f"{dec.title}: {dec.text}\n{dec.rationale}"
    pages = scoped(
        Page.objects.filter(archived_at__isnull=True, access=0, project_pages__deleted_at__isnull=True),
        project_field="project_pages__project_id",
    ).distinct()
    for page in pages:
        pp = page.project_pages.filter(deleted_at__isnull=True).first()
        if pp:
            text = f"{page.name}\n{page.description_stripped or strip_html(page.description_html)}"
            yield "page", page.id, pp.project_id, text
    messages = scoped(
        Message.objects.filter(author_kind="human", conversation__deleted_at__isnull=True)
        .exclude(conversation__kind=Conversation.Kind.DIRECT)
        .select_related("conversation"),
        project_field="conversation__project_id",
    )
    for msg in messages:
        if msg.conversation.project_id:
            yield "message", msg.id, msg.conversation.project_id, msg.body
    uploads = scoped(
        UploadRecord.objects.filter(scan_status=UploadRecord.ScanStatus.CLEAN, project__isnull=False)
        .exclude(extracted_text="")
        .select_related("asset")
    )
    for rec in uploads:
        name = (rec.asset.attributes or {}).get("name") or "Upload"
        yield "upload", rec.id, rec.project_id, f"{name}\n{rec.extracted_text}"


# -- indexing ------------------------------------------------------------------------------


def _hash(model, text):
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8", "ignore")).hexdigest()


def index_sources(workspace_id, sources, provider: AIProvider = None) -> dict:
    """Embed changed sources. Unchanged content (same hash and model) is skipped."""
    provider = provider or get_provider()
    model = getattr(provider, "embedding_model", "")
    stats = {"indexed": 0, "skipped": 0, "failed": 0}
    if not model:
        return stats
    pending = []
    for object_type, object_id, project_id, text in sources:
        text = (text or "").strip()[:MAX_EMBED_CHARS]
        if not text:
            continue
        digest = _hash(model, text)
        existing = AIEmbedding.objects.filter(object_type=object_type, object_id=object_id).first()
        if existing and existing.content_hash == digest:
            stats["skipped"] += 1
            continue
        pending.append((existing, object_type, object_id, project_id, text, digest))
    for start in range(0, len(pending), EMBED_BATCH):
        batch = pending[start : start + EMBED_BATCH]
        try:
            vectors = provider.embed([row[4] for row in batch]) or []
        except Exception:
            logger.exception("Embedding batch failed")
            stats["failed"] += len(batch)
            continue
        for (existing, object_type, object_id, project_id, _text, digest), vector in zip(batch, vectors):
            row = existing or AIEmbedding(object_type=object_type, object_id=object_id)
            row.workspace_id = workspace_id
            row.project_id = project_id
            row.model = model
            row.content_hash = digest
            row.vector = [round(float(v), 6) for v in vector]
            row.save()
            stats["indexed"] += 1
    return stats


def refresh_workspace(workspace_id, *, since=None, provider=None) -> dict:
    stats = index_sources(workspace_id, iter_sources(workspace_id, since=since), provider=provider)
    stats["pruned"] = prune_workspace(workspace_id)
    return stats


def prune_workspace(workspace_id) -> int:
    """Hard-delete vectors whose source is gone or no longer embeddable (FR-I08)."""
    removed = 0
    checks = {
        "issue": Issue.objects.filter(project__deleted_at__isnull=True),
        "decision": Decision.objects.all(),
        "page": Page.objects.filter(archived_at__isnull=True, access=0),
        "message": Message.objects.filter(conversation__deleted_at__isnull=True).exclude(
            conversation__kind=Conversation.Kind.DIRECT
        ),
        "upload": UploadRecord.objects.filter(scan_status=UploadRecord.ScanStatus.CLEAN),
    }
    for object_type, qs in checks.items():
        ids = AIEmbedding.all_objects.filter(workspace_id=workspace_id, object_type=object_type).values_list(
            "object_id", flat=True
        )
        alive = set(qs.filter(id__in=list(ids)).values_list("id", flat=True))
        gone = [i for i in ids if i not in alive]
        if gone:
            removed += AIEmbedding.all_objects.filter(object_type=object_type, object_id__in=gone).delete()[0]
    return removed


def remove(object_type, object_id) -> int:
    return AIEmbedding.all_objects.filter(object_type=object_type, object_id=object_id).delete()[0]


# -- retrieval -----------------------------------------------------------------------------


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_refs(workspace_id, project_ids, query, *, provider, limit):
    model = getattr(provider, "embedding_model", "")
    if not model or not project_ids:
        return []
    rows = list(
        AIEmbedding.objects.filter(workspace_id=workspace_id, project_id__in=list(project_ids), model=model)
        .order_by("-updated_at")
        .values_list("object_type", "object_id", "vector")[:MAX_CANDIDATES]
    )
    if not rows:
        return []
    try:
        vectors = provider.embed([query[:MAX_EMBED_CHARS]]) or []
    except Exception:
        logger.exception("Query embedding failed; falling back to full-text search")
        return []
    if not vectors:
        return []
    qv = vectors[0]
    scored = sorted(((_cosine(qv, v), t, i) for t, i, v in rows), reverse=True)
    return [
        {"type": t, "id": str(i), "score": round(score, 4)} for score, t, i in scored[:limit] if score >= MIN_SIMILARITY
    ]


def keyword_refs(user, workspace, project_ids, query, *, limit):
    from ..services import search as search_service

    allowed = {str(p) for p in project_ids}
    # Natural-language questions: match any significant keyword, not the whole sentence.
    terms = sorted(keywords(query), key=len, reverse=True)[:8]
    if not terms:
        return []
    refs = []
    for hit in search_service.search(user, workspace, " or ".join(terms), limit=limit * 2):
        kind = TYPE_MAP.get(hit.get("type"))
        if not kind or (hit.get("project_id") and hit["project_id"] not in allowed):
            continue
        if hit.get("conversation_id") and kind == "message":
            conv = Conversation.objects.filter(id=hit["conversation_id"]).only("kind").first()
            if conv is None or conv.kind == Conversation.Kind.DIRECT:
                continue  # private DMs never become retrieval context
        refs.append({"type": kind, "id": hit["id"]})
    return refs[:limit]


def retrieve(user, workspace, query, *, project_ids=None, limit=8, exclude=(), provider=None):
    """Selection refs relevant to ``query`` within projects the user can read (ACL re-checked later)."""
    query = (query or "").strip()
    if len(query) < 3:
        return []
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    projects = readable if project_ids is None else readable & {str(p) for p in project_ids}
    if not projects:
        return []
    provider = provider or get_provider()
    skip = {(e.get("type"), str(e.get("id"))) for e in exclude}
    out, seen = [], set(skip)
    for ref in semantic_refs(workspace.id, projects, query, provider=provider, limit=limit) + keyword_refs(
        user, workspace, projects, query, limit=limit
    ):
        key = (ref["type"], str(ref["id"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": ref["type"], "id": str(ref["id"]), "retrieved": True})
        if len(out) >= limit:
            break
    return out
