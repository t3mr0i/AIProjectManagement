# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Decisions from conversations (FR-C03, FR-C04, J06, AC11, AC12, AC13).

* ``preview`` never books anything; ambiguous target/selection returns a
  clarifying question instead.
* ``confirm`` needs a verified human with ``decision.publish``. The source
  snapshot stores message id + version + body. The same ``idempotency_key``
  always yields the same decision (``pf_decision_idempotent``).
* Private DM sources are rejected (403 ``PRIVATE_SOURCE``) when the decision's
  audience is larger than the DM participants, unless the confirming person
  publishes an explicitly reviewed own summary — then only the summary is
  stored, no DM excerpt.
* Later edits create ``MessageVersion`` rows and never change the decision;
  listings expose ``source_changed_since_decision``. Deleted sources become a
  ``[source deleted]`` tombstone in the snapshot (FR-I08).
"""

import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.db.models import Issue

from ..ai.context import dm_participants, project_members
from ..errors import DomainError, NotFound, ValidationFailed
from ..models import AIProposal, Conversation, Decision, Message
from . import search
from .events import audit, emit

TOMBSTONE = "[source deleted]"
_ISSUE_REF = re.compile(r"\b([A-Z][A-Z0-9]{0,11})-(\d+)\b")


class PrivateSource(DomainError):
    status_code = 403
    code = "PRIVATE_SOURCE"


def _load_messages(user, workspace_id, message_ids, conversation=None):
    from .conversations import can_read

    ids = [str(m) for m in (message_ids or [])]
    msgs = list(
        Message.objects.select_related("conversation").filter(
            id__in=ids, workspace_id=workspace_id, author_kind="human"
        )
    )
    if len(msgs) != len(set(ids)):
        raise NotFound("Source message not found")
    for m in msgs:
        if conversation is not None and m.conversation_id != conversation.id:
            raise ValidationFailed("All source messages must belong to the selected conversation")
        if not can_read(user, m.conversation):
            raise NotFound("Source message not found")
    msgs.sort(key=lambda m: m.created_at)
    return msgs


def _mentioned_issues(project, texts):
    found = {}
    for text in texts:
        for ident, seq in _ISSUE_REF.findall(text or ""):
            if ident != project.identifier:
                continue
            issue = Issue.objects.filter(project=project, sequence_id=int(seq)).first()
            if issue is not None:
                found[str(issue.id)] = issue
    return list(found.values())


def _first_sentence(text, limit=120):
    text = " ".join((text or "").split())
    for sep in (". ", "! ", "? ", "\n"):
        if sep in text:
            text = text.split(sep)[0]
            break
    return text[:limit] or "Decision"


def _private_blocked(messages, project):
    """True if any DM source has fewer readers than the project audience."""
    audience = project_members(project.id)
    for m in messages:
        if m.conversation.kind == Conversation.Kind.DIRECT and not audience <= dm_participants(m.conversation_id):
            return True
    return False


def preview(user, project, *, conversation_id, message_ids, issue_id=None, instruction=""):
    from .conversations import get_readable

    conversation = get_readable(user, project.workspace, conversation_id)
    if not message_ids:
        return {
            "type": "clarification",
            "question": "Which messages contain the decision? Select at least one message.",
            "reason": "no_selection",
        }
    messages = _load_messages(user, project.workspace_id, message_ids, conversation)
    target = None
    if issue_id:
        target = Issue.objects.filter(id=issue_id, project=project).first()
        if target is None:
            raise NotFound("Work item not found")
    elif conversation.kind == Conversation.Kind.PACKAGE and conversation.issue_id:
        target = conversation.issue
    else:
        mentioned = _mentioned_issues(project, [m.body for m in messages] + [instruction or ""])
        if len(mentioned) > 1:
            return {
                "type": "clarification",
                "question": "Several packages are mentioned. Which package does this decision belong to?",
                "reason": "ambiguous_target",
                "options": [
                    {"issue_id": str(i.id), "identifier": f"{project.identifier}-{i.sequence_id}", "name": i.name}
                    for i in mentioned
                ],
            }
        if mentioned:
            target = mentioned[0]
    body = "\n".join(m.body for m in messages)
    title = _first_sentence(instruction) if instruction else _first_sentence(messages[-1].body)
    private = _private_blocked(messages, project)
    content = {
        "title": title,
        "text": messages[-1].body if len(messages) == 1 else body,
        "rationale": instruction or "",
        "issue_id": str(target.id) if target else None,
        "scope": "package" if target else "project",
        "source_message_ids": [str(m.id) for m in messages],
        "source_versions": {str(m.id): m.version for m in messages},
        "private_source": private,
        "statements": [
            {"text": title, "status": "proposed", "sources": [{"type": "message", "id": str(m.id)} for m in messages]}
        ],
    }
    proposal = AIProposal.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        issue=target,
        kind=AIProposal.Kind.DECISION_PREVIEW,
        requested_by=user,
        content=content,
        sources=[{"type": "message", "id": str(m.id), "version": m.version} for m in messages],
    )
    return {
        "type": "preview",
        "preview_id": str(proposal.id),
        **content,
        "requires_reviewed_summary": private,
        "target": {"issue_id": content["issue_id"], "project_id": str(project.id)},
    }


def _snapshot(messages):
    now = timezone.now().isoformat()
    return [
        {
            "type": "message",
            "message_id": str(m.id),
            "conversation_id": str(m.conversation_id),
            "version": m.version,
            "body": m.body,
            "author_id": str(m.author_id) if m.author_id else None,
            "captured_at": now,
        }
        for m in messages
    ]


def confirm(user, project, data):
    """Create (or return the already created) confirmed decision. Returns ``(decision, created)``."""
    key = str(data.get("idempotency_key") or "").strip()[:255]
    if key:
        existing = Decision.objects.filter(workspace_id=project.workspace_id, idempotency_key=key).first()
        if existing is not None:
            if existing.project_id != project.id:
                raise NotFound("Decision not found")
            return existing, False

    fields = {}
    proposal = None
    if data.get("preview_id"):
        proposal = AIProposal.objects.filter(
            id=data["preview_id"], project=project, kind=AIProposal.Kind.DECISION_PREVIEW
        ).first()
        if proposal is None:
            raise NotFound("Preview not found")
        fields = dict(proposal.content)
    for k in ("title", "text", "rationale", "issue_id", "source_message_ids", "scope"):
        if data.get(k) not in (None, ""):
            fields[k] = data[k]
    kind = data.get("kind") or "decision"
    if kind not in ("decision", "open_question"):
        raise ValidationFailed("Unknown decision kind")
    title = (fields.get("title") or "").strip()
    text = (fields.get("text") or "").strip()
    if not title and text:
        title = _first_sentence(text)
    if not title or not text:
        raise ValidationFailed("title and text are required")

    issue = None
    if fields.get("issue_id"):
        issue = Issue.objects.filter(id=fields["issue_id"], project=project).first()
        if issue is None:
            raise NotFound("Work item not found")

    messages = _load_messages(user, project.workspace_id, fields.get("source_message_ids") or [])
    snapshot = _snapshot(messages)
    source_conversation = messages[0].conversation if messages else None
    if messages and _private_blocked(messages, project):
        summary = (data.get("summary") or "").strip()
        if not (data.get("publish_reviewed_summary") is True and summary):
            raise PrivateSource(
                "The source is a private conversation with a smaller audience than this project. "
                "Publish an explicitly reviewed summary instead.",
                detail={"requires_reviewed_summary": True},
            )
        # Only the reviewed summary is stored — no DM excerpt, no DM reference (AC12, PRD §14.2).
        text = summary
        snapshot = [
            {
                "type": "reviewed_summary",
                "body": summary,
                "reviewed_by": str(user.id),
                "captured_at": timezone.now().isoformat(),
            }
        ]
        source_conversation = None

    now = timezone.now()
    try:
        with transaction.atomic():
            decision = Decision.objects.create(
                workspace_id=project.workspace_id,
                project=project,
                issue=issue,
                title=title[:255],
                text=text,
                rationale=fields.get("rationale") or "",
                scope=fields.get("scope") or ("package" if issue else "project"),
                status=Decision.Status.CONFIRMED if kind == "decision" else Decision.Status.PROPOSED,
                kind=kind,
                confirmed_by=user if kind == "decision" else None,
                confirmed_at=now if kind == "decision" else None,
                source_snapshot=snapshot,
                source_conversation=source_conversation,
                audience="project",
                idempotency_key=key,
                owner=user,
            )
            if proposal is not None:
                AIProposal.objects.filter(pk=proposal.pk).update(
                    status=AIProposal.Status.ACCEPTED, decided_by=user, decided_at=now
                )
            search.index_decision(decision)
            if kind == "decision":
                emit(
                    workspace_id=project.workspace_id,
                    project_id=project.id,
                    issue_id=issue.id if issue else None,
                    event_type="decision.published",
                    aggregate_type="decision",
                    aggregate_id=decision.id,
                    actor_kind="human",
                    actor_id=user.id,
                    deduplication_key=f"decision.published:{decision.id}",
                    payload={"decision_id": str(decision.id), "title": decision.title},
                    summary=f"Decision confirmed: {decision.title}",
                )
            else:
                emit(
                    workspace_id=project.workspace_id,
                    project_id=project.id,
                    issue_id=issue.id if issue else None,
                    event_type="question.raised",
                    aggregate_type="decision",
                    aggregate_id=decision.id,
                    actor_kind="human",
                    actor_id=user.id,
                    payload={"decision_id": str(decision.id)},
                    summary=f"Open question: {decision.title}",
                )
            audit(
                workspace_id=project.workspace_id,
                project_id=project.id,
                issue_id=issue.id if issue else None,
                action="decision.confirmed" if kind == "decision" else "decision.question_raised",
                target_type="decision",
                target_id=decision.id,
                actor=user,
                detail={"sources": [s.get("message_id") for s in snapshot if s.get("message_id")]},
            )
    except IntegrityError:
        # Concurrent redelivery with the same key: exactly one row wins (AC11).
        existing = Decision.objects.filter(workspace_id=project.workspace_id, idempotency_key=key).first()
        if existing is None:
            raise
        return existing, False
    return decision, True


def source_state(decision):
    """(changed, deleted) of the referenced message versions (FR-C04)."""
    changed = deleted = False
    ids = [s["message_id"] for s in decision.source_snapshot or [] if s.get("type") == "message"]
    current = {str(m.id): m.version for m in Message.objects.filter(id__in=ids)}
    for s in decision.source_snapshot or []:
        if s.get("type") != "message":
            continue
        if s.get("deleted") or s["message_id"] not in current:
            deleted = True
        elif current[s["message_id"]] > int(s.get("version") or 1):
            changed = True
    return changed, deleted


def serialize(decision, *, include_snapshot=True):
    changed, deleted = source_state(decision)
    data = {
        "id": str(decision.id),
        "project_id": str(decision.project_id) if decision.project_id else None,
        "issue_id": str(decision.issue_id) if decision.issue_id else None,
        "title": decision.title,
        "text": decision.text,
        "rationale": decision.rationale,
        "scope": decision.scope,
        "status": decision.status,
        "kind": decision.kind,
        "confirmed_by": str(decision.confirmed_by_id) if decision.confirmed_by_id else None,
        "confirmed_at": decision.confirmed_at,
        "idempotency_key": decision.idempotency_key,
        "source_changed_since_decision": changed,
        "source_deleted": deleted,
        "created_at": decision.created_at,
    }
    if include_snapshot:
        data["source_snapshot"] = decision.source_snapshot
    return data


def list_for(project, *, issue_id=None, status=None, kind=None):
    qs = Decision.objects.filter(project=project)
    if issue_id:
        qs = qs.filter(issue_id=issue_id)
    if status:
        qs = qs.filter(status=status)
    if kind:
        qs = qs.filter(kind=kind)
    return list(qs.order_by("-created_at"))


def tombstone_message_sources(message_ids):
    """Replace snapshot excerpts of deleted messages; decisions keep their own text (FR-C04/FR-I08)."""
    ids = {str(m) for m in message_ids}
    touched = 0
    for mid in ids:
        for decision in Decision.all_objects.filter(source_snapshot__contains=[{"message_id": mid}]):
            snap = []
            for s in decision.source_snapshot:
                if s.get("message_id") in ids:
                    s = {**s, "body": TOMBSTONE, "deleted": True}
                snap.append(s)
            Decision.all_objects.filter(pk=decision.pk).update(source_snapshot=snap)
            touched += 1
    return touched
