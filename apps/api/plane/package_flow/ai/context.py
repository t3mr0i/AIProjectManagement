# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI context assembly with audience check (PRD §14.2, FR-C02, FR-C05, AC12, AC26).

A source is only handed to the AI if **every** member of the target audience
may read it — the requester's own rights are not enough. Rules:

* project items (issues, decisions, pages, uploads, channel/thread messages):
  active native project membership of every audience member;
* DM messages: every audience member must be an active DM participant, so
  private content never flows into a project channel;
* uploads: only after a clean security scan (quarantined/pending never);
* deleted sources are excluded; sources the requester cannot read are reported
  as ``unavailable`` without title (no existence oracle).

The result is visible to the user (``visible``) so the context area is
transparent (FR-C02).
"""

import re
from dataclasses import dataclass, field
from typing import List

from plane.db.models import Issue, Page, ProjectMember, ProjectPage

from ..models import (
    Conversation,
    ConversationParticipant,
    Decision,
    Message,
    MessageVersion,
    UploadRecord,
)

MAX_SOURCE_CHARS = 2000
SOURCE_TYPES = ("message", "issue", "page", "decision", "upload")

REASON_UNAVAILABLE = "unavailable"
REASON_PRIVATE = "private_source"
REASON_AUDIENCE = "audience_mismatch"
REASON_QUARANTINED = "quarantined"
REASON_SCAN_PENDING = "scan_pending"

_TAG = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html or "")).strip()


# -- audiences -----------------------------------------------------------------


def project_members(project_id) -> set:
    return {
        str(uid)
        for uid in ProjectMember.objects.filter(
            project_id=project_id, is_active=True, member__is_active=True, project__deleted_at__isnull=True
        ).values_list("member_id", flat=True)
    }


def dm_participants(conversation_id) -> set:
    return {
        str(uid)
        for uid in ConversationParticipant.objects.filter(
            conversation_id=conversation_id, is_active=True, member__is_active=True
        ).values_list("member_id", flat=True)
    }


def conversation_audience(conversation: Conversation) -> set:
    if conversation.kind == Conversation.Kind.DIRECT:
        return dm_participants(conversation.id)
    return project_members(conversation.project_id)


def projects_audience(project_ids) -> set:
    audience = set()
    for pid in project_ids or []:
        audience |= project_members(pid)
    return audience


# -- source resolution ---------------------------------------------------------


@dataclass
class _Resolved:
    ref: dict
    title: str
    text: str
    readers: set  # user ids allowed to read
    private: bool = False  # DM content / private page
    block_reason: str = ""  # e.g. quarantine; applies regardless of audience
    confirmed: bool = False
    stale: bool = False


class _Cache:
    def __init__(self):
        self.projects = {}
        self.dms = {}

    def project(self, pid):
        key = str(pid)
        if key not in self.projects:
            self.projects[key] = project_members(pid)
        return self.projects[key]

    def dm(self, cid):
        key = str(cid)
        if key not in self.dms:
            self.dms[key] = dm_participants(cid)
        return self.dms[key]


def _resolve(ref, workspace_id, cache) -> "_Resolved | None":
    kind = ref.get("type")
    oid = ref.get("id")
    if kind not in SOURCE_TYPES or not oid:
        return None
    try:
        if kind == "message":
            msg = (
                Message.objects.select_related("conversation")
                .filter(id=oid, workspace_id=workspace_id, conversation__deleted_at__isnull=True)
                .first()
            )
            if msg is None:
                return None
            conv = msg.conversation
            body, stale = msg.body, False
            wanted = ref.get("version")
            if wanted and int(wanted) != msg.version:
                stale = True
                old = MessageVersion.objects.filter(message=msg, version=int(wanted)).first()
                body = old.body if old else msg.body
            if conv.kind == Conversation.Kind.DIRECT:
                readers, private = cache.dm(conv.id), True
            else:
                if conv.issue_id and not Issue.objects.filter(id=conv.issue_id).exists():
                    return None
                readers, private = cache.project(conv.project_id), False
            return _Resolved(
                ref={"type": "message", "id": str(msg.id), "version": msg.version, "conversation_id": str(conv.id)},
                title=f"Message in {conv.get_kind_display().lower()}",
                text=body,
                readers=readers,
                private=private,
                stale=stale,
            )
        if kind == "issue":
            issue = Issue.objects.filter(id=oid, workspace_id=workspace_id, project__deleted_at__isnull=True).first()
            if issue is None:
                return None
            text = f"{issue.name}\n{issue.description_stripped or strip_html(issue.description_html)}"
            profile = getattr(issue, "package_profile", None)
            if profile is not None and profile.deleted_at is None:
                text += f"\nOutcome: {profile.outcome}\nIntent: {profile.intent}"
            return _Resolved(
                ref={"type": "issue", "id": str(issue.id), "project_id": str(issue.project_id)},
                title=issue.name,
                text=text,
                readers=cache.project(issue.project_id),
            )
        if kind == "decision":
            dec = Decision.objects.filter(id=oid, workspace_id=workspace_id).first()
            if dec is None or dec.project_id is None:
                return None
            return _Resolved(
                ref={"type": "decision", "id": str(dec.id), "confirmed": dec.status == Decision.Status.CONFIRMED},
                title=dec.title,
                text=f"{dec.title}: {dec.text}\n{dec.rationale}",
                readers=cache.project(dec.project_id),
                confirmed=dec.status == Decision.Status.CONFIRMED,
            )
        if kind == "page":
            page = Page.objects.filter(id=oid, workspace_id=workspace_id, archived_at__isnull=True).first()
            if page is None:
                return None
            project_ids = list(
                ProjectPage.objects.filter(page=page, project__deleted_at__isnull=True).values_list(
                    "project_id", flat=True
                )
            )
            readers = set()
            for pid in project_ids:
                readers |= cache.project(pid)
            private = page.access == 1
            if private:
                readers = readers & {str(page.owned_by_id)}
            return _Resolved(
                ref={"type": "page", "id": str(page.id)},
                title=page.name or "Untitled page",
                text=f"{page.name}\n{page.description_stripped or strip_html(page.description_html)}",
                readers=readers,
                private=private,
            )
        if kind == "upload":
            lookup = {"asset_id": oid} if ref.get("by") == "asset" else {"id": oid}
            rec = UploadRecord.objects.select_related("asset").filter(workspace_id=workspace_id, **lookup).first()
            if rec is None or rec.asset.is_deleted or rec.project_id is None:
                return None
            reason = ""
            if rec.scan_status == UploadRecord.ScanStatus.QUARANTINED:
                reason = REASON_QUARANTINED
            elif rec.scan_status != UploadRecord.ScanStatus.CLEAN:
                reason = REASON_SCAN_PENDING
            name = (rec.asset.attributes or {}).get("name") or "Upload"
            return _Resolved(
                ref={"type": "upload", "id": str(rec.id)},
                title=name,
                # Content of unclean uploads is never read (AC26).
                text="" if reason else f"{name}\n{rec.extracted_text}",
                readers=cache.project(rec.project_id),
                block_reason=reason,
            )
    except (ValueError, TypeError):
        return None
    return None


# -- assembly ------------------------------------------------------------------


@dataclass
class ContextResult:
    allowed: List[dict] = field(default_factory=list)
    blocked: List[dict] = field(default_factory=list)
    visible: List[dict] = field(default_factory=list)
    audience_size: int = 0

    def as_dict(self, include_text=False):
        allowed = self.allowed if include_text else [{k: v for k, v in a.items() if k != "text"} for a in self.allowed]
        return {
            "allowed": allowed,
            "blocked": self.blocked,
            "visible": self.visible,
            "audience_size": self.audience_size,
        }

    def provider_messages(self) -> List[dict]:
        """Context as untrusted data messages for :class:`AIProvider` (never instructions)."""
        return [
            {"role": "context", "content": a["text"][:MAX_SOURCE_CHARS], "source": a["ref"]} for a in self.allowed
        ]


def assemble_context(*, requester, workspace_id, audience_ids, selection) -> ContextResult:
    """Check each selected source against requester *and* the whole audience."""
    cache = _Cache()
    audience = {str(a) for a in (audience_ids or [])} | {str(requester.id)}
    result = ContextResult(audience_size=len(audience))
    seen = set()
    for raw in selection or []:
        ref = {"type": raw.get("type"), "id": str(raw.get("id", ""))}
        if raw.get("version") is not None:
            ref["version"] = raw.get("version")
        if raw.get("by"):
            ref["by"] = raw["by"]
        key = (ref["type"], ref["id"], str(ref.get("version", "")))
        if key in seen:
            continue
        seen.add(key)
        resolved = _resolve(ref, workspace_id, cache)
        public_ref = {"type": ref["type"], "id": ref["id"]}
        if resolved is None or str(requester.id) not in resolved.readers:
            result.blocked.append({"ref": public_ref, "reason": REASON_UNAVAILABLE})
            result.visible.append({"ref": public_ref, "title": None, "status": "blocked", "reason": REASON_UNAVAILABLE})
            continue
        reason = resolved.block_reason
        if not reason and not audience <= resolved.readers:
            reason = REASON_PRIVATE if resolved.private else REASON_AUDIENCE
        entry_ref = resolved.ref
        if reason:
            result.blocked.append({"ref": entry_ref, "reason": reason})
            result.visible.append({"ref": entry_ref, "title": resolved.title, "status": "blocked", "reason": reason})
            continue
        result.allowed.append(
            {
                "ref": entry_ref,
                "title": resolved.title,
                "text": resolved.text,
                "confirmed": resolved.confirmed,
                "stale": resolved.stale,
            }
        )
        result.visible.append(
            {"ref": entry_ref, "title": resolved.title, "status": "allowed", "stale": resolved.stale}
        )
    return result


def default_selection_for_conversation(conversation: Conversation, *, exclude_message_ids=(), limit=20) -> List[dict]:
    """Implicit context for @AI: recent thread messages, the package, confirmed project
    decisions and project uploads (uploads are listed so quarantine is visible, AC26)."""
    selection = []
    msgs = (
        Message.objects.filter(conversation=conversation, author_kind="human")
        .exclude(id__in=list(exclude_message_ids))
        .order_by("-created_at")[:limit]
    )
    selection += [{"type": "message", "id": str(m.id)} for m in msgs]
    if conversation.kind == Conversation.Kind.DIRECT or conversation.project_id is None:
        return selection
    if conversation.issue_id:
        selection.append({"type": "issue", "id": str(conversation.issue_id)})
    decisions = Decision.objects.filter(
        project_id=conversation.project_id, status=Decision.Status.CONFIRMED
    ).order_by("-confirmed_at")[:limit]
    selection += [{"type": "decision", "id": str(d.id)} for d in decisions]
    uploads = UploadRecord.objects.filter(project_id=conversation.project_id, asset__is_deleted=False)
    if conversation.issue_id:
        uploads = uploads.filter(issue_id__in=[conversation.issue_id]) | uploads.filter(issue__isnull=True)
    selection += [{"type": "upload", "id": str(u.id)} for u in uploads.order_by("-created_at")[:limit]]
    return selection
