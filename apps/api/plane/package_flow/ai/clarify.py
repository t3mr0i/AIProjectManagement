# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Moderate clarification (FR-W03, PRD §14.3, skill ``package-clarify``, AC28).

Rules:

* Inspect existing context first: package profile, native description,
  confirmed project decisions and project pages.
* At most **one** question per round, prioritized: outcome, non-goals,
  acceptance, ownership, consequences, then open points found in the
  description (``TBD``/``?``/``offen``).
* Questions already answered by an existing field or a confirmed decision /
  page are skipped and the answering source is cited (AC28).
* Each question carries a recommendation labelled ``proposed``.
* After three questions a savable checkpoint is returned (no forced
  approval); the user may stop or continue at any time.
* Answers are stored as turns and turned into a pending ``draft_edit``
  ``AIProposal`` — never applied automatically.
"""

import re

from django.db import transaction
from django.utils import timezone

from plane.db.models import IssueAssignee, Page, ProjectPage

from ..models import AIProposal, ClarificationSession, Decision, PackageProfile
from .context import strip_html
from .provider import keywords

CHECKPOINT_AFTER = 3

TOPICS = (
    {
        "topic": "outcome",
        "question": "What concrete outcome should exist when this package is done?",
        "field": "outcome",
        "keywords": {"outcome", "ergebnis", "goal", "ziel"},
        "why": "Without a verifiable outcome the package cannot be reviewed.",
    },
    {
        "topic": "non_goals",
        "question": "What is explicitly out of scope (non-goals)?",
        "field": "non_goals",
        "keywords": {"non-goal", "non-goals", "nichtziel", "nichtziele", "out-of-scope", "scope"},
        "why": "Non-goals prevent scope creep during execution.",
    },
    {
        "topic": "acceptance",
        "question": "How will we verify it works (acceptance criteria)?",
        "field": "criteria",
        "keywords": {"acceptance", "akzeptanz", "abnahme", "criteria", "kriterien"},
        "why": "Acceptance criteria make review and delivery checkable.",
    },
    {
        "topic": "ownership",
        "question": "Who owns this package and accepts the result?",
        "field": "owner",
        "keywords": {"owner", "verantwortlich", "responsible", "zuständig"},
        "why": "A responsible person is needed for review and decisions.",
    },
    {
        "topic": "consequences",
        "question": "Which relevant consequences or risks should reviewers know about?",
        "field": "risk",
        "keywords": {"risk", "risiko", "consequence", "folgen", "impact"},
        "why": "Known consequences shape review depth and rollout.",
    },
)

_OPEN_POINT = re.compile(r"([^.\n]*\b(?:TBD|TODO|offen|unklar|unclear|open question)\b[^.\n]*|[^.\n?]*\?)",
                         re.IGNORECASE)
_TOPIC_NOISE = {"tbd", "todo", "offen", "unklar", "unclear", "open", "question", "which", "should", "use", "welche",
                "welches", "soll", "wir", "need", "decide"}


def _recommendation(topic, issue, context_text):
    name = issue.name
    rec = {
        "outcome": f"'{name}' is available to its intended users and can be demonstrated end-to-end.",
        "non_goals": "No changes outside the described feature; no data migration or redesign of adjacent areas.",
        "acceptance": f"Given the described situation, when a user uses '{name}', then the expected result is "
                      "visible and covered by an automated test.",
        "ownership": "The current assignee owns the package; the project lead accepts the outcome.",
        "consequences": "Low risk if limited to the described scope; note any user-visible behaviour change.",
    }.get(topic)
    if rec is None:
        rec = "Record the answer as a confirmed decision so it is not asked again."
    return {"text": rec, "status": "proposed"}


def _context(issue):
    """Existing sources, inspected before asking (PRD §14.3)."""
    profile = PackageProfile.objects.filter(issue=issue).first()
    description = issue.description_stripped or strip_html(issue.description_html)
    decisions = Decision.objects.filter(project_id=issue.project_id, status=Decision.Status.CONFIRMED)
    decisions = list(decisions.order_by("-confirmed_at")[:100])
    page_ids = ProjectPage.objects.filter(project_id=issue.project_id, deleted_at__isnull=True).values_list(
        "page_id", flat=True
    )
    pages = list(Page.objects.filter(id__in=list(page_ids), access=0, archived_at__isnull=True)[:50])
    return profile, description, decisions, pages


def _answered_by(topic_keywords, decisions, pages, min_overlap=1):
    for d in decisions:
        if len(topic_keywords & keywords(f"{d.title} {d.text}")) >= min_overlap:
            return {"type": "decision", "id": str(d.id), "title": d.title, "status": "confirmed"}
    for p in pages:
        text = f"{p.name} {p.description_stripped or strip_html(p.description_html)}"
        if len(topic_keywords & keywords(text)) >= min_overlap:
            return {"type": "page", "id": str(p.id), "title": p.name, "status": "observed"}
    return None


def _field_filled(topic, profile, issue):
    if topic == "ownership":
        return IssueAssignee.objects.filter(issue=issue, deleted_at__isnull=True).exists()
    if profile is None:
        return False
    value = {
        "outcome": profile.outcome,
        "non_goals": profile.non_goals,
        "acceptance": profile.criteria,
        "consequences": profile.risk,
    }.get(topic)
    return bool(value)


def open_points(description):
    points = []
    for m in _OPEN_POINT.finditer(description or ""):
        text = " ".join(m.group(0).split()).strip(" -:*")
        kw = keywords(text) - _TOPIC_NOISE
        if text and kw:
            points.append({"text": text, "keywords": kw})
    return points


def candidate_questions(issue):
    """All questions in priority order, with skip reasons for answered ones."""
    profile, description, decisions, pages = _context(issue)
    desc_kw = keywords(description)
    out = []
    for t in TOPICS:
        entry = {"topic": t["topic"], "question": t["question"], "why": t["why"], "field": t["field"]}
        if _field_filled(t["topic"], profile, issue):
            entry["answered_by"] = {"type": "field", "field": t["field"], "status": "observed"}
        elif t["topic"] != "ownership" and desc_kw & t["keywords"]:
            entry["answered_by"] = {"type": "issue", "id": str(issue.id), "status": "observed"}
        else:
            src = _answered_by(t["keywords"], decisions, pages)
            if src:
                entry["answered_by"] = src
        out.append(entry)
    for idx, point in enumerate(open_points(description)):
        entry = {
            "topic": f"open_point:{idx}",
            "question": f"Open point in the description: \"{point['text']}\" — what should apply?",
            "why": "The description marks this as open.",
            "field": "open_points",
        }
        # Known answer (e.g. a confirmed decision about the export format) -> do not ask again (AC28).
        src = _answered_by(point["keywords"], decisions, pages, min_overlap=min(2, len(point["keywords"])))
        if src:
            entry["answered_by"] = src
        out.append(entry)
    return out


# -- session -------------------------------------------------------------------------


def _active_session(issue, user):
    session = (
        ClarificationSession.objects.filter(issue=issue, status__in=["active", "checkpoint"])
        .order_by("-created_at")
        .first()
    )
    if session is None:
        session = ClarificationSession.objects.create(
            workspace_id=issue.workspace_id, project_id=issue.project_id, issue=issue, started_by=user, turns=[]
        )
    return session


def _pending_question(session):
    for turn in reversed(session.turns or []):
        if turn.get("role") == "user":
            return None
        if turn.get("role") == "ai" and turn.get("type") == "question":
            return turn
    return None


def _asked_topics(session):
    return {t.get("topic") for t in session.turns or [] if t.get("role") == "ai" and t.get("type") == "question"}


def _since_checkpoint(session):
    n = 0
    for turn in reversed(session.turns or []):
        if turn.get("type") in ("checkpoint", "continue"):
            break
        if turn.get("role") == "ai" and turn.get("type") == "question":
            n += 1
    return n


def _draft_proposal(session, issue, user):
    """Collect answers into one pending draft-edit proposal (never auto-applied)."""
    patch, sources = {}, []
    for turn in session.turns or []:
        if turn.get("role") != "user" or not turn.get("answer"):
            continue
        topic, answer = turn.get("topic", ""), turn["answer"]
        if topic == "outcome":
            patch["outcome"] = answer
        elif topic == "non_goals":
            patch["non_goals"] = [a.strip() for a in re.split(r"[\n;]", answer) if a.strip()]
        elif topic == "acceptance":
            patch["criteria"] = [{"text": a.strip()} for a in re.split(r"[\n;]", answer) if a.strip()]
        elif topic == "ownership":
            patch.setdefault("scope", {})["owner_note"] = answer
        elif topic == "consequences":
            patch["risk"] = {"notes": answer}
        else:
            patch.setdefault("scope", {}).setdefault("resolved_open_points", []).append(
                {"question": turn.get("question", ""), "answer": answer}
            )
        sources.append({"type": "clarification_turn", "session_id": str(session.id), "topic": topic})
    if not patch:
        return None
    profile = PackageProfile.objects.filter(issue=issue).first()
    base_version = str(profile.version) if profile else ""
    proposal = AIProposal.objects.filter(
        issue=issue,
        kind=AIProposal.Kind.DRAFT_EDIT,
        status=AIProposal.Status.PENDING,
        selection__clarification_session=str(session.id),
    ).first()
    content = {
        "patch": patch,
        "statements": [
            {"text": f"{k}: {v}", "status": "confirmed" if k != "scope" else "proposed", "sources": sources}
            for k, v in patch.items()
        ],
        "note": "Draft edit from clarification answers. Applying it requires a human accept; "
                "it is not an execution approval.",
    }
    if proposal is None:
        proposal = AIProposal.objects.create(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue=issue,
            kind=AIProposal.Kind.DRAFT_EDIT,
            requested_by=user,
            content=content,
            selection={"clarification_session": str(session.id)},
            sources=sources,
            base_version=base_version,
        )
    else:
        proposal.content = content
        proposal.sources = sources
        proposal.base_version = base_version
        proposal.save(update_fields=["content", "sources", "base_version", "updated_at"])
    return proposal


def _checkpoint_payload(session, issue, user, remaining, reason):
    proposal = _draft_proposal(session, issue, user)
    return {
        "type": "checkpoint",
        "reason": reason,
        "session_id": str(session.id),
        "questions_asked": session.questions_asked,
        "draft_proposal_id": str(proposal.id) if proposal else None,
        "draft": proposal.content if proposal else None,
        "open_topics": [q["topic"] for q in remaining],
        "can_continue": bool(remaining),
        # Saving an intermediate state is not an approval (FR-W03).
        "approval_required": False,
        "applied": False,
    }


def step(issue, user, *, answer=None, stop=False, cont=False):
    """One clarification round. Returns question | checkpoint | complete payload."""
    with transaction.atomic():
        session = _active_session(issue, user)
        session = ClarificationSession.objects.select_for_update().get(pk=session.pk)
        turns = list(session.turns or [])
        now = timezone.now().isoformat()
        pending = _pending_question(session)

        if answer is not None and str(answer).strip():
            if pending is None:
                from ..errors import Conflict

                raise Conflict("No open clarification question to answer", code="NO_OPEN_QUESTION")
            turns.append({"role": "user", "type": "answer", "topic": pending["topic"],
                          "question": pending["question"], "answer": str(answer).strip(), "at": now,
                          "user_id": str(user.id)})
            session.turns = turns
            pending = None
            # Every answer immediately feeds the pending draft-edit proposal (never applied).
            _draft_proposal(session, issue, user)

        candidates = candidate_questions(issue)
        asked = _asked_topics(session)
        remaining = [q for q in candidates if "answered_by" not in q and q["topic"] not in asked]
        skipped = [
            {"topic": q["topic"], "answered_by": q["answered_by"]} for q in candidates if "answered_by" in q
        ]

        if stop:
            session.status = "closed"
            turns.append({"role": "user", "type": "stop", "at": now})
            session.turns = turns
            session.save(update_fields=["status", "turns", "updated_at"])
            payload = _checkpoint_payload(session, issue, user, remaining, "stopped_by_user")
            payload["skipped"] = skipped
            return payload

        if cont:
            turns.append({"role": "user", "type": "continue", "at": now})
            session.turns = turns
            session.status = "active"

        if pending is not None:
            session.save(update_fields=["turns", "status", "updated_at"])
            return {"type": "question", "session_id": str(session.id), **_public_question(pending),
                    "skipped": skipped, "questions_asked": session.questions_asked}

        if session.status == "active" and _since_checkpoint(session) >= CHECKPOINT_AFTER:
            session.status = "checkpoint"
            turns.append({"role": "ai", "type": "checkpoint", "at": now})
            session.turns = turns
            session.save(update_fields=["status", "turns", "updated_at"])
            payload = _checkpoint_payload(session, issue, user, remaining, "after_three_questions")
            payload["skipped"] = skipped
            return payload

        if session.status == "checkpoint":
            session.save(update_fields=["turns", "updated_at"])
            payload = _checkpoint_payload(session, issue, user, remaining, "checkpoint")
            payload["skipped"] = skipped
            return payload

        if not remaining:
            session.status = "closed"
            session.save(update_fields=["status", "turns", "updated_at"])
            payload = _checkpoint_payload(session, issue, user, remaining, "nothing_left_to_ask")
            payload["type"] = "complete"
            payload["skipped"] = skipped
            return payload

        q = remaining[0]
        _, description, _, _ = _context(issue)
        turn = {
            "role": "ai",
            "type": "question",
            "topic": q["topic"],
            "question": q["question"],
            "why": q["why"],
            "recommendation": _recommendation(q["topic"], issue, description),
            "at": now,
        }
        turns.append(turn)
        session.turns = turns
        session.questions_asked += 1
        session.save(update_fields=["turns", "questions_asked", "status", "updated_at"])
        return {"type": "question", "session_id": str(session.id), **_public_question(turn),
                "skipped": skipped, "questions_asked": session.questions_asked}


def _public_question(turn):
    return {
        "topic": turn["topic"],
        "question": turn["question"],
        "why": turn.get("why", ""),
        "recommendation": turn.get("recommendation"),
    }
