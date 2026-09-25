# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Activity feed, "since my last visit" and project overview (FR-P02..FR-P04, J08, AC29).

* Feed = extension ``DomainEvent`` rows + native ``IssueActivity`` grouped by
  package (issue) and day.
* Compaction (FR-P03): technical events of one package and day (checks,
  progress, heartbeats, commits) collapse into one summary entry with a
  count; ``raw=True`` returns each raw event (still retrievable).
* "Since my last visit" uses the personal ``VisitMarker``; it is view state
  only and reading never marks messages read (J08).
* Next work (FR-P04): ordered by native priority, execution approval and
  confirmed dependencies. A package with an unmet confirmed hard dependency is
  never "immediately executable". The AI never sets priority; only
  explanation strings are returned.
"""

from collections import OrderedDict
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from plane.db.models import Issue, IssueActivity

from ..capabilities import accessible_project_ids
from ..models import (
    Decision,
    DomainEvent,
    ExecutionApproval,
    Milestone,
    PackageProfile,
    PlanningDependency,
    VisitMarker,
)

COMPACT_EVENTS = {"ci.check.observed", "run.progress", "run.heartbeat", "git.commit.observed"}
DEFAULT_WINDOW = timedelta(days=7)
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "none": 4, None: 4, "": 4}


# -- visit marker ----------------------------------------------------------------


def record_visit(user, project, at=None):
    at = at or timezone.now()
    marker = VisitMarker.objects.filter(workspace_id=project.workspace_id, project=project, member=user).first()
    if marker is None:
        marker = VisitMarker.objects.create(
            workspace_id=project.workspace_id, project=project, member=user, last_visited_at=at
        )
    else:
        marker.previous_visited_at = marker.last_visited_at
        marker.last_visited_at = at
        marker.save(update_fields=["previous_visited_at", "last_visited_at", "updated_at"])
    return marker


def last_visit_boundary(user, project):
    """Start of "since my last visit": the visit *before* the current one."""
    marker = VisitMarker.objects.filter(workspace_id=project.workspace_id, project=project, member=user).first()
    if marker is None:
        return timezone.now() - DEFAULT_WINDOW
    return marker.previous_visited_at or marker.last_visited_at


def resolve_window(user, project, since=None, until=None):
    until_dt = parse_datetime(until) if isinstance(until, str) and until else (until or timezone.now())
    if since == "last_visit":
        since_dt = last_visit_boundary(user, project)
    elif since == "today":
        now = timezone.localtime()
        since_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif isinstance(since, str) and since:
        since_dt = parse_datetime(since)
        if since_dt is None:
            raise ValueError("since must be ISO datetime, 'today' or 'last_visit'")
    else:
        since_dt = since or (timezone.now() - DEFAULT_WINDOW)
    if until_dt is None:
        raise ValueError("until must be ISO datetime")
    return since_dt, until_dt


# -- feed ------------------------------------------------------------------------


def _event_entry(e):
    return {
        "kind": "event",
        "id": str(e.id),
        "source": "package_flow",
        "event_type": e.event_type,
        "summary": e.summary or e.event_type,
        "reason": (e.payload or {}).get("reason", ""),
        "actor_kind": e.actor_kind,
        "actor_id": e.actor_id,
        "occurred_at": e.occurred_at,
        "is_fixture": e.is_fixture,
    }


def _native_entry(a):
    return {
        "kind": "native",
        "id": str(a.id),
        "source": "plane",
        "event_type": f"native.{a.verb}",
        "field": a.field,
        "summary": (a.comment or f"{a.verb} {a.field or ''}").strip(),
        "old_value": a.old_value,
        "new_value": a.new_value,
        "actor_id": str(a.actor_id) if a.actor_id else None,
        "occurred_at": a.created_at,
    }


def _compact(entries):
    """Collapse technical events per type into one summary line (FR-P03)."""
    out, buckets = [], OrderedDict()
    for entry in entries:
        if entry["kind"] == "event" and entry["event_type"] in COMPACT_EVENTS:
            buckets.setdefault(entry["event_type"], []).append(entry)
        else:
            out.append(entry)
    for event_type, items in buckets.items():
        if len(items) == 1:
            out.append(items[0])
            continue
        statuses = {}
        for item in items:
            key = item.get("status") or "observed"
            statuses[key] = statuses.get(key, 0) + 1
        label = {
            "ci.check.observed": "pipeline/check events",
            "run.progress": "progress updates",
            "run.heartbeat": "heartbeats",
            "git.commit.observed": "commits",
        }.get(event_type, event_type)
        detail = ", ".join(f"{v} {k}" for k, v in sorted(statuses.items()))
        out.append(
            {
                "kind": "summary",
                "event_type": event_type,
                "count": len(items),
                "summary": f"{len(items)} {label} ({detail})",
                "raw_ids": [i["id"] for i in items],
                "first_at": min(i["occurred_at"] for i in items),
                "occurred_at": max(i["occurred_at"] for i in items),
            }
        )
    out.sort(key=lambda x: x["occurred_at"], reverse=True)
    return out


def feed(user, project, *, since=None, until=None, raw=False, issue_id=None):
    since_dt, until_dt = resolve_window(user, project, since, until)
    live_issues = set(Issue.objects.filter(project=project).values_list("id", flat=True))
    events = DomainEvent.objects.filter(project=project, occurred_at__gt=since_dt, occurred_at__lte=until_dt)
    natives = IssueActivity.objects.filter(
        project=project, created_at__gt=since_dt, created_at__lte=until_dt, deleted_at__isnull=True
    ).exclude(verb="deleted")
    if issue_id:
        events = events.filter(issue_id=issue_id)
        natives = natives.filter(issue_id=issue_id)
    entries_by_issue = OrderedDict()
    for e in events.order_by("-occurred_at")[:2000]:
        if e.issue_id and e.issue_id not in live_issues:
            continue
        entry = _event_entry(e)
        status = (e.payload or {}).get("status") or (e.payload or {}).get("conclusion")
        if status:
            entry["status"] = str(status)
        entries_by_issue.setdefault(e.issue_id, []).append(entry)
    for a in natives.order_by("-created_at")[:2000]:
        if a.issue_id and a.issue_id not in live_issues:
            continue
        entries_by_issue.setdefault(a.issue_id, []).append(_native_entry(a))

    issues = {i.id: i for i in Issue.objects.filter(id__in=[k for k in entries_by_issue if k])}
    groups = []
    for iid, entries in entries_by_issue.items():
        days = OrderedDict()
        for entry in sorted(entries, key=lambda x: x["occurred_at"], reverse=True):
            day = timezone.localtime(entry["occurred_at"]).date().isoformat()
            days.setdefault(day, []).append(entry)
        issue = issues.get(iid)
        groups.append(
            {
                "issue_id": str(iid) if iid else None,
                "issue_name": issue.name if issue else None,
                "identifier": f"{project.identifier}-{issue.sequence_id}" if issue else None,
                "last_at": max(e["occurred_at"] for e in entries),
                "days": [{"date": d, "entries": items if raw else _compact(items)} for d, items in days.items()],
            }
        )
    groups.sort(key=lambda g: g["last_at"], reverse=True)

    decisions = Decision.objects.filter(project=project)
    confirmed = decisions.filter(
        status=Decision.Status.CONFIRMED, confirmed_at__gt=since_dt, confirmed_at__lte=until_dt
    )
    open_decisions = open_decision_qs(project)
    return {
        "since": since_dt,
        "until": until_dt,
        "raw": raw,
        "groups": groups,
        "decisions_confirmed": [_decision_brief(d) for d in confirmed],
        "open_decisions": [_decision_brief(d) for d in open_decisions],
    }


def raw_events(project, ids):
    return [_event_entry(e) for e in DomainEvent.objects.filter(project=project, id__in=ids)]


def _decision_brief(d):
    return {
        "id": str(d.id),
        "title": d.title,
        "kind": d.kind,
        "status": d.status,
        "issue_id": str(d.issue_id) if d.issue_id else None,
        "confirmed_at": d.confirmed_at,
        "created_at": d.created_at,
    }


def open_decision_qs(project):
    from django.db.models import Q

    return (
        Decision.objects.filter(project=project)
        .filter(
            Q(kind="open_question", status__in=[Decision.Status.PROPOSED, Decision.Status.CONFIRMED])
            | Q(status=Decision.Status.PROPOSED)
        )
        .exclude(status__in=[Decision.Status.WITHDRAWN, Decision.Status.SUPERSEDED])
    )


# -- overview / next work ----------------------------------------------------------

BUCKET_KEYWORDS = (
    ("shipped", ("shipped", "delivered", "released", "done", "completed", "accepted")),
    ("review", ("review",)),
    ("active", ("running", "active", "in_progress", "executing", "claimed", "waiting", "paused", "started", "build")),
    ("ready", ("ready", "approved")),
)


def _local_status(issue):
    group = getattr(issue.state, "group", None) if issue.state_id else None
    if group == "completed":
        return "shipped"
    now = timezone.now()
    approved = ExecutionApproval.objects.filter(issue=issue, revoked_at__isnull=True, expires_at__gt=now).exists()
    if group == "started":
        return "active"
    if approved:
        return "ready"
    return "draft"


def package_status(issue, facts=None):
    """Delegates to the package service; falls back to a minimal local computation."""
    try:
        from .packages import compute_package_status  # noqa: WPS433 (lazy: owned by another workstream)

        status = compute_package_status(issue, facts=facts) if facts is not None else compute_package_status(issue)
    except Exception:
        return _local_status(issue)
    if isinstance(status, dict):
        status = status.get("lifecycle") or status.get("status") or status.get("phase") or ""
    return str(status or "") or _local_status(issue)


def bucket_for(status):
    s = (status or "").lower()
    for bucket, words in BUCKET_KEYWORDS:
        if any(w in s for w in words):
            return bucket
    return "draft"


def _is_approved(issue):
    return ExecutionApproval.objects.filter(
        issue=issue, revoked_at__isnull=True, expires_at__gt=timezone.now()
    ).exists()


def unmet_dependencies(user, issue):
    """Confirmed hard predecessors that are not finished. Hidden ones stay anonymous (PRD §15.2)."""
    visible_projects = set(accessible_project_ids(user, issue.workspace_id))
    blockers = []
    deps = PlanningDependency.objects.filter(
        successor_type=PlanningDependency.NodeType.ISSUE,
        successor_id=issue.id,
        strength=PlanningDependency.Strength.HARD,
        confirmation=PlanningDependency.Confirmation.CONFIRMED,
    )
    for dep in deps:
        if dep.predecessor_type == PlanningDependency.NodeType.ISSUE:
            pred = Issue.all_objects.filter(id=dep.predecessor_id).select_related("state").first()
            if pred is None or pred.deleted_at is not None:
                continue
            done = pred.state_id is not None and pred.state.group == "completed"
            if done:
                continue
            if pred.project_id in visible_projects:
                blockers.append({"type": "issue", "id": str(pred.id), "name": pred.name})
            else:
                blockers.append(
                    {"type": "external", "name": "external prerequisite open"}
                    if dep.allow_anonymous_blocker
                    else {"type": "hidden"}
                )
        elif dep.predecessor_type == PlanningDependency.NodeType.MILESTONE:
            ms = Milestone.objects.filter(id=dep.predecessor_id).first()
            if ms is None or ms.status in ("done", "cancelled"):
                continue
            if ms.project_id in visible_projects:
                blockers.append({"type": "milestone", "id": str(ms.id), "name": ms.name})
            else:
                blockers.append(
                    {"type": "external", "name": "external prerequisite open"}
                    if dep.allow_anonymous_blocker
                    else {"type": "hidden"}
                )
    return blockers


def overview(user, project):
    profiles = list(
        PackageProfile.objects.filter(project=project, issue__deleted_at__isnull=True).select_related(
            "issue", "issue__state", "issue__project", "issue__package_profile"
        )
    )
    try:
        from .packages import batch_status_facts

        facts = batch_status_facts([p.issue for p in profiles])
    except Exception:  # noqa: BLE001 - fall back to per-issue computation
        facts = {}
    buckets = {"active": [], "ready": [], "review": [], "shipped": [], "draft": []}
    candidates = []
    for profile in profiles:
        issue = profile.issue
        status = package_status(issue, facts.get(issue.id))
        bucket = bucket_for(status)
        item = {
            "issue_id": str(issue.id),
            "identifier": f"{project.identifier}-{issue.sequence_id}",
            "name": issue.name,
            "status": status,
            "priority": issue.priority,
        }
        buckets[bucket].append(item)
        if bucket not in ("shipped", "active", "review"):
            candidates.append((issue, item))

    candidate_ids = [issue.id for issue, _ in candidates]
    now = timezone.now()
    approved_ids = set(
        ExecutionApproval.objects.filter(
            issue_id__in=candidate_ids, revoked_at__isnull=True, expires_at__gt=now
        ).values_list("issue_id", flat=True)
    )
    with_deps = set(
        PlanningDependency.objects.filter(
            successor_type=PlanningDependency.NodeType.ISSUE,
            successor_id__in=candidate_ids,
            strength=PlanningDependency.Strength.HARD,
            confirmation=PlanningDependency.Confirmation.CONFIRMED,
        ).values_list("successor_id", flat=True)
    )
    next_work = []
    for issue, item in candidates:
        approved = issue.id in approved_ids
        blockers = unmet_dependencies(user, issue) if issue.id in with_deps else []
        reasons = [f"Priority: {issue.priority or 'none'} (native Plane priority)"]
        reasons.append("Execution approved" if approved else "Execution not yet approved")
        if blockers:
            names = [b.get("name") for b in blockers if b.get("name")]
            reasons.append(
                "Blocked by confirmed dependency: " + ", ".join(names) if names else "Blocked by a confirmed dependency"
            )
        next_work.append(
            {
                **item,
                "approved": approved,
                "blocked": bool(blockers),
                "blockers": [b for b in blockers if b["type"] != "hidden"],
                "immediately_executable": approved and not blockers,
                "reasons": reasons,
            }
        )
    next_work.sort(
        key=lambda w: (w["blocked"], not w["approved"], PRIORITY_RANK.get(w["priority"], 4), w["identifier"])
    )
    return {
        "project_id": str(project.id),
        "packages": {k: v for k, v in buckets.items()},
        "open_decisions": [_decision_brief(d) for d in open_decision_qs(project)[:50]],
        "next_work": next_work,
        "priority_source": "native",
    }
