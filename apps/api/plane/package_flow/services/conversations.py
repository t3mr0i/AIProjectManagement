# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project chat, package threads and direct messages (FR-C01, FR-C02, FR-C04, J08).

Access rules (evaluated on every request, so revocation is immediate, FR-I07):

* DM: only active explicit participants. Workspace admins get 404 (PRD §5.2).
* Project channel / package thread: active native project membership.
* A package thread is get-or-create per native Issue (unique constraint) and is
  reachable both from the package and the chat (FR-C01).

Reading never marks messages as read; only ``mark_read`` does (J08).
"""

import hashlib
import re

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from plane.db.models import Issue, Project, User, WorkspaceMember

from ..ai.context import assemble_context, conversation_audience, default_selection_for_conversation
from ..ai.provider import get_provider
from ..capabilities import accessible_project_ids, is_project_member
from ..errors import NotFound, PermissionDenied, ValidationFailed
from ..models import Conversation, ConversationParticipant, Message, MessageVersion
from . import notifications, search

AI_MENTION = re.compile(r"(?<![\w@])@ai\b", re.IGNORECASE)
USER_MENTION = re.compile(r"(?<![\w@])@([A-Za-z0-9_.\-]+)")
MAX_BODY = 20000


# -- access --------------------------------------------------------------------


def can_read(user, conversation) -> bool:
    if conversation.deleted_at is not None:
        return False
    if conversation.kind == Conversation.Kind.DIRECT:
        return ConversationParticipant.objects.filter(
            conversation=conversation, member=user, is_active=True
        ).exists() and WorkspaceMember.objects.filter(
            workspace_id=conversation.workspace_id, member=user, is_active=True
        ).exists()
    if conversation.project_id is None or not is_project_member(user, conversation.project_id):
        return False
    if conversation.issue_id and not Issue.objects.filter(id=conversation.issue_id).exists():
        return False
    return True


def get_readable(user, workspace, conversation_id) -> Conversation:
    conv = Conversation.objects.filter(id=conversation_id, workspace=workspace).first()
    if conv is None or not can_read(user, conv):
        # Same answer for "missing" and "not yours" — no existence oracle.
        raise NotFound("Conversation not found")
    return conv


def list_for(user, workspace):
    projects = accessible_project_ids(user, workspace.id)
    dm_ids = search.my_dm_conversation_ids(user, workspace.id)
    return list(
        Conversation.objects.filter(workspace=workspace, is_archived=False)
        .filter(Q(id__in=dm_ids) | (Q(project_id__in=projects) & ~Q(kind=Conversation.Kind.DIRECT)))
        .exclude(issue__deleted_at__isnull=False)
        .order_by("-updated_at")
    )


# -- create --------------------------------------------------------------------


def _dm_key(user_ids):
    return hashlib.sha256(",".join(sorted(str(u) for u in user_ids)).encode()).hexdigest()


def create(user, workspace, *, kind, project_id=None, issue_id=None, participant_ids=None, title=""):
    """Returns ``(conversation, created)``."""
    if kind == Conversation.Kind.DIRECT:
        ids = {str(p) for p in (participant_ids or [])} | {str(user.id)}
        if len(ids) < 2:
            raise ValidationFailed("A direct message needs at least one other participant")
        members = set(
            str(m)
            for m in WorkspaceMember.objects.filter(
                workspace=workspace, member_id__in=list(ids), is_active=True, member__is_active=True
            ).values_list("member_id", flat=True)
        )
        if members != ids:
            raise ValidationFailed("All participants must be active workspace members")
        key = _dm_key(ids)
        existing = Conversation.objects.filter(workspace=workspace, kind=kind, dm_key=key).first()
        if existing:
            return existing, False
        try:
            with transaction.atomic():
                conv = Conversation.objects.create(workspace=workspace, kind=kind, dm_key=key, title=title or "")
                for pid in ids:
                    ConversationParticipant.objects.create(conversation=conv, member_id=pid)
        except IntegrityError:
            return Conversation.objects.get(workspace=workspace, kind=kind, dm_key=key), False
        return conv, True

    if kind not in (Conversation.Kind.PROJECT, Conversation.Kind.PACKAGE):
        raise ValidationFailed("Unknown conversation kind")
    project = Project.objects.filter(id=project_id, workspace=workspace, deleted_at__isnull=True).first()
    if project is None or not is_project_member(user, project.id):
        raise NotFound("Project not found")

    if kind == Conversation.Kind.PACKAGE:
        issue = Issue.objects.filter(id=issue_id, project=project).first() if issue_id else None
        if issue is None:
            raise NotFound("Work item not found")
        return package_thread(issue)

    title = (title or "").strip() or "General"
    existing = Conversation.objects.filter(project=project, kind=kind, title=title).first()
    if existing:
        return existing, False
    return Conversation.objects.create(workspace=workspace, project=project, kind=kind, title=title), True


def package_thread(issue):
    """Get-or-create the single thread of a package (FR-C01)."""
    existing = Conversation.objects.filter(issue=issue, kind=Conversation.Kind.PACKAGE).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            conv = Conversation.objects.create(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue=issue,
                kind=Conversation.Kind.PACKAGE,
                title=issue.name[:255],
            )
    except IntegrityError:
        return Conversation.objects.get(issue=issue, kind=Conversation.Kind.PACKAGE), False
    return conv, True


# -- messages ------------------------------------------------------------------


def parse_mentions(conversation, body):
    """``@AI`` and ``@display_name`` of people who can read the conversation."""
    mentions = []
    if AI_MENTION.search(body or ""):
        mentions.append({"type": "ai"})
    names = {m.group(1).rstrip(".").lower() for m in USER_MENTION.finditer(body or "")} - {"ai"}
    if names:
        audience = conversation_audience(conversation)
        users = User.objects.filter(id__in=list(audience), is_active=True)
        for u in users:
            if (u.display_name or "").lower() in names:
                mentions.append({"type": "user", "id": str(u.id), "display_name": u.display_name})
    return mentions


def serialize_message(m):
    return {
        "id": str(m.id),
        "conversation_id": str(m.conversation_id),
        "author_id": str(m.author_id) if m.author_id else None,
        "author_kind": m.author_kind,
        "parent_id": str(m.parent_id) if m.parent_id else None,
        "body": m.body,
        "version": m.version,
        "mentions": m.mentions,
        "source_links": m.source_links,
        "ai_context": m.ai_context,
        "edited_at": m.edited_at,
        "created_at": m.created_at,
    }


def serialize_conversation(c, user=None):
    data = {
        "id": str(c.id),
        "kind": c.kind,
        "project_id": str(c.project_id) if c.project_id else None,
        "issue_id": str(c.issue_id) if c.issue_id else None,
        "title": c.title,
        "is_archived": c.is_archived,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }
    if c.kind == Conversation.Kind.DIRECT:
        data["participant_ids"] = [
            str(p)
            for p in ConversationParticipant.objects.filter(conversation=c, is_active=True).values_list(
                "member_id", flat=True
            )
        ]
    if user is not None:
        part = ConversationParticipant.objects.filter(conversation=c, member=user).first()
        last_read = part.last_read_at if part else None
        unread = Message.objects.filter(conversation=c).exclude(author=user)
        if last_read:
            unread = unread.filter(created_at__gt=last_read)
        data["last_read_at"] = last_read
        data["unread_count"] = unread.count()
    return data


def list_messages(conversation, *, after=None, limit=200):
    qs = Message.objects.filter(conversation=conversation).order_by("created_at")
    if after:
        qs = qs.filter(created_at__gt=after)
    return list(qs[:limit])


def post_message(user, conversation, *, body, parent_id=None, selection=None, source_links=None):
    body = (body or "").strip()
    if not body:
        raise ValidationFailed("Message body is required")
    if len(body) > MAX_BODY:
        raise ValidationFailed("Message body too long")
    parent = None
    if parent_id:
        parent = Message.objects.filter(id=parent_id, conversation=conversation).first()
        if parent is None:
            raise NotFound("Parent message not found")
    with transaction.atomic():
        mentions = parse_mentions(conversation, body)
        msg = Message.objects.create(
            conversation=conversation,
            workspace_id=conversation.workspace_id,
            author=user,
            author_kind="human",
            parent=parent,
            body=body,
            mentions=mentions,
            source_links=source_links or [],
        )
        Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
        search.index_message(msg)
        for m in mentions:
            if m["type"] == "user" and m["id"] != str(user.id):
                notifications.notify(
                    recipient_id=m["id"],
                    workspace_id=conversation.workspace_id,
                    project_id=conversation.project_id,
                    category="mention",
                    title=f"{user.display_name} mentioned you",
                    target={"conversation_id": str(conversation.id), "message_id": str(msg.id)},
                )
    ai_message = None
    if any(m["type"] == "ai" for m in mentions):
        ai_message = answer_with_ai(user, conversation, msg, selection=selection)
    return msg, ai_message


def answer_with_ai(user, conversation, trigger, *, selection=None, provider=None):
    """@AI answer: context checked against the conversation's audience (FR-C02, AC12, AC26)."""
    audience = conversation_audience(conversation)
    implicit = default_selection_for_conversation(conversation, exclude_message_ids=[trigger.id])
    explicit = list(selection or [])
    ctx = assemble_context(
        requester=user,
        workspace_id=conversation.workspace_id,
        audience_ids=audience,
        selection=explicit + implicit,
    )
    question = AI_MENTION.sub("", trigger.body).strip()
    provider = provider or get_provider()
    result = provider.complete("answer", [{"role": "user", "content": question}] + ctx.provider_messages())
    ai_context = {
        "status": result.status,
        "provider": result.provider,
        "sources_used": [a["ref"] for a in ctx.allowed],
        "blocked": ctx.blocked,
        "visible": ctx.visible,
        "explicit_selection": [{"type": s.get("type"), "id": str(s.get("id"))} for s in explicit],
        "statements": [{"text": s.text, "status": s.status, "sources": s.sources} for s in result.statements],
        "notes": result.notes,
        "error_code": result.error_code,
        "error": result.error,
        "requested_by": str(user.id),
    }
    msg = Message.objects.create(
        conversation=conversation,
        workspace_id=conversation.workspace_id,
        author=None,
        author_kind="ai",
        parent=trigger,
        body=result.text or result.error,
        ai_context=ai_context,
    )
    return msg


def get_message(conversation, message_id):
    msg = Message.objects.filter(id=message_id, conversation=conversation).first()
    if msg is None:
        raise NotFound("Message not found")
    return msg


def edit_message(user, conversation, message, *, body):
    """Keeps every prior version so decisions stay reproducible (FR-C04, AC13)."""
    if message.author_id != user.id or message.author_kind != "human":
        raise PermissionDenied("Only the author can edit a message")
    body = (body or "").strip()
    if not body:
        raise ValidationFailed("Message body is required")
    if body == message.body:
        return message
    with transaction.atomic():
        MessageVersion.objects.create(message=message, version=message.version, body=message.body)
        message.body = body
        message.version += 1
        message.edited_at = timezone.now()
        message.mentions = parse_mentions(conversation, body)
        message.save(update_fields=["body", "version", "edited_at", "mentions", "updated_at"])
        search.index_message(message)
    return message


def purge_message(message):
    """Hard-delete a message with its derived data (FR-C04, FR-I08).

    Search rows vanish, decision snapshots get a tombstone; the decisions keep
    their own confirmed text.
    """
    from .decisions import tombstone_message_sources

    with transaction.atomic():
        tombstone_message_sources([message.id])
        search.remove_document("message", message.id)
        MessageVersion.all_objects.filter(message=message).delete()
        Message.all_objects.filter(parent=message).update(parent=None)
        Message.all_objects.filter(pk=message.pk).delete()


def delete_message(user, conversation, message):
    if message.author_id != user.id:
        raise PermissionDenied("Only the author can delete a message")
    purge_message(message)


def mark_read(user, conversation, at=None):
    """Explicit read marker — never set implicitly by reads (J08)."""
    at = at or timezone.now()
    part = ConversationParticipant.objects.filter(conversation=conversation, member=user).first()
    if part is None:
        if conversation.kind == Conversation.Kind.DIRECT:
            raise NotFound("Conversation not found")
        part = ConversationParticipant.objects.create(conversation=conversation, member=user)
    part.last_read_at = at
    part.save(update_fields=["last_read_at", "updated_at"])
    return part
