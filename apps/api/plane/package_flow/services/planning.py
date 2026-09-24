# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Cross-project planning on top of native Plane planning (I11; FR-M01..M06, FR-C06, AC24, AC25).

Native Cycles/Modules/Issue dates stay the planning basis and are only read.
This service adds milestones, typed/confirmed dependencies, a redacted
roadmap graph, what-if scenarios, traceable risks and ICS export.

Redaction (PRD §15.2, AC25): the read boundary is the native project
membership (``accessible_project_ids``). A graph node in a project the viewer
cannot read is removed together with its edge. Only when the dependency has
``allow_anonymous_blocker`` and the hidden node is the *prerequisite*, the edge
is kept and the node is replaced by an anonymous ``external_blocker`` without
name, id or project.
"""

import datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from plane.db.models import Cycle, CycleIssue, Issue, Module, Project, ProjectMember, WorkspaceMember
from plane.db.models.workspace import Team

from ..capabilities import (
    accessible_project_ids,
    has_capability,
    require_capability,
    require_extension_enabled,
    workspace_role,
)
from ..errors import Conflict, HumanPrincipalRequired, NotFound, PermissionDenied, ValidationFailed
from ..models import (
    CalendarEvent,
    Capability,
    Milestone,
    PackageProfile,
    PlanningDependency,
    PlanScenario,
    Risk,
    TeamScope,
)
from . import events

UTC = dt.timezone.utc
NO_RELIABLE_DATE = "No reliable date"
EXTERNAL_BLOCKER_LABEL = "External prerequisite open"
DATE_CONFIDENCE = ("confirmed", "estimated", "unknown")
MILESTONE_STATUS = ("planned", "at_risk", "done", "cancelled")
NODE_TYPES = {c.value for c in PlanningDependency.NodeType}


# ---------------------------------------------------------------------------
# time helpers (FR-C06)
# ---------------------------------------------------------------------------
def _zone(name):
    try:
        return ZoneInfo(str(name or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationFailed("unknown timezone", detail={"field": "timezone", "value": name})


def parse_instant(value, tz_name="UTC", field="target_at"):
    """Parse ISO datetime; naive values are interpreted in ``tz_name``. Returns aware UTC or None."""
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
        if parsed is None:
            day = parse_date(str(value))
            if day is None:
                raise ValidationFailed(f"{field} must be an ISO 8601 datetime", detail={"field": field})
            parsed = dt.datetime.combine(day, dt.time(0, 0))
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=_zone(tz_name))
    return parsed.astimezone(UTC)


def iso_utc(value):
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def in_zone(value, tz_name):
    if value is None:
        return None
    return value.astimezone(_zone(tz_name)).isoformat()


def _date_end_utc(day):
    """Native issue target dates are calendar days; treat as end of day UTC for comparisons."""
    if day is None:
        return None
    return dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=UTC)


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------
def _require_plan(user, workspace_id, project_ids):
    for project_id in sorted({str(p) for p in project_ids if p}):
        require_capability(user, workspace_id, project_id, Capability.PROJECT_PLAN)
        require_extension_enabled(workspace_id, project_id)


def _require_human(principal, action):
    if not principal.is_human:
        raise HumanPrincipalRequired(f"{action} requires a human principal")


# ---------------------------------------------------------------------------
# node resolution
# ---------------------------------------------------------------------------
def _issue_label(issue):
    return f"{issue.project.identifier}-{issue.sequence_id} {issue.name}"


def resolve_nodes(workspace_id, keys):
    """Resolve ``[(type, id)]`` to node dicts keyed by ``(type, str(id))``. Missing nodes are absent."""
    by_type = defaultdict(set)
    for node_type, node_id in keys:
        by_type[node_type].add(str(node_id))
    nodes = {}
    if by_type.get("issue"):
        for issue in Issue.all_objects.filter(
            id__in=by_type["issue"], workspace_id=workspace_id, deleted_at__isnull=True
        ).select_related("project"):
            nodes[("issue", str(issue.id))] = {
                "type": "issue",
                "id": str(issue.id),
                "project_id": str(issue.project_id),
                "label": _issue_label(issue),
                "start": issue.start_date.isoformat() if issue.start_date else None,
                "target": issue.target_date.isoformat() if issue.target_date else None,
                "target_instant": _date_end_utc(issue.target_date),
            }
    if by_type.get("milestone"):
        for m in Milestone.objects.filter(
            id__in=by_type["milestone"], workspace_id=workspace_id, deleted_at__isnull=True
        ):
            reliable = m.target_at is not None and m.date_confidence != "unknown"
            nodes[("milestone", str(m.id))] = {
                "type": "milestone",
                "id": str(m.id),
                "project_id": str(m.project_id) if m.project_id else None,
                "label": m.name,
                "start": None,
                "target": iso_utc(m.target_at) if reliable else None,
                "target_instant": m.target_at,
                "date_confidence": m.date_confidence,
            }
    if by_type.get("project"):
        for p in Project.objects.filter(id__in=by_type["project"], workspace_id=workspace_id, deleted_at__isnull=True):
            nodes[("project", str(p.id))] = {
                "type": "project",
                "id": str(p.id),
                "project_id": str(p.id),
                "label": p.name,
                "start": None,
                "target": None,
                "target_instant": None,
            }
    return nodes


def _public_node(node):
    return {k: v for k, v in node.items() if k != "target_instant"}


def _node_key(node):
    return f"{node['type']}:{node['id']}"


def _anonymous_blocker(index):
    return {"key": f"external:{index}", "type": "external_blocker", "label": EXTERNAL_BLOCKER_LABEL}


# ---------------------------------------------------------------------------
# dependencies (FR-M02, FR-M04, AC24)
# ---------------------------------------------------------------------------
def _confirmed_hard_graph(workspace_id, exclude_id=None):
    graph = defaultdict(list)
    qs = PlanningDependency.objects.filter(
        workspace_id=workspace_id,
        deleted_at__isnull=True,
        strength=PlanningDependency.Strength.HARD,
        confirmation=PlanningDependency.Confirmation.CONFIRMED,
    )
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    for dep in qs.values("predecessor_type", "predecessor_id", "successor_type", "successor_id"):
        graph[(dep["predecessor_type"], str(dep["predecessor_id"]))].append(
            (dep["successor_type"], str(dep["successor_id"]))
        )
    return graph


def find_cycle(workspace_id, predecessor, successor, exclude_id=None):
    """Return the node path of the cycle that ``predecessor -> successor`` would close, or None.

    Iterative DFS over confirmed hard dependencies from ``successor`` to ``predecessor``.
    """
    if predecessor == successor:
        return [predecessor, successor]
    graph = _confirmed_hard_graph(workspace_id, exclude_id)
    stack = [(successor, [successor])]
    visited = set()
    while stack:
        node, path = stack.pop()
        if node == predecessor:
            return [predecessor] + path
        if node in visited:
            continue
        visited.add(node)
        for nxt in graph.get(node, []):
            if nxt not in visited:
                stack.append((nxt, path + [nxt]))
    return None


def _cycle_error(workspace_id, user, path):
    readable = {str(p) for p in accessible_project_ids(user, workspace_id)}
    nodes = resolve_nodes(workspace_id, path)
    labels = []
    for key in path:
        node = nodes.get((key[0], str(key[1])))
        if node is None or (node["project_id"] and node["project_id"] not in readable):
            labels.append(EXTERNAL_BLOCKER_LABEL)  # never leak hidden names through the error
        else:
            labels.append(node["label"])
    readable_path = " -> ".join(labels)
    return ValidationFailed(
        f"Hard dependency cycle: {readable_path}. A hard dependency must not (indirectly) depend on itself.",
        code="DEPENDENCY_CYCLE",
        detail={"path": labels, "readable_path": readable_path},
    )


def _parse_node(data, side):
    raw = data.get(side)
    if isinstance(raw, dict):
        node_type, node_id = raw.get("type"), raw.get("id")
    else:
        node_type, node_id = data.get(f"{side}_type"), data.get(f"{side}_id")
    if node_type not in NODE_TYPES or not node_id:
        raise ValidationFailed(f"{side} needs type (issue|milestone|project) and id", detail={"field": side})
    return (node_type, str(node_id))


def serialize_dependency(dep, nodes=None, readable=None):
    body = {
        "id": str(dep.id),
        "predecessor": {
            "type": dep.predecessor_type,
            "id": str(dep.predecessor_id),
            "project_id": str(dep.predecessor_project_id) if dep.predecessor_project_id else None,
        },
        "successor": {
            "type": dep.successor_type,
            "id": str(dep.successor_id),
            "project_id": str(dep.successor_project_id) if dep.successor_project_id else None,
        },
        "strength": dep.strength,
        "confirmation": dep.confirmation,
        "source": dep.source,
        "blocking": dep.strength == "hard" and dep.confirmation == "confirmed",
        "style": _edge_style(dep),
        "allow_anonymous_blocker": dep.allow_anonymous_blocker,
        "note": dep.note,
        "confirmed_by": str(dep.confirmed_by_id) if dep.confirmed_by_id else None,
    }
    if nodes is not None:
        for side in ("predecessor", "successor"):
            node = nodes.get((body[side]["type"], body[side]["id"]))
            if node:
                body[side]["label"] = node["label"]
    return body


def _edge_style(dep):
    if dep.confirmation == PlanningDependency.Confirmation.SUGGESTED:
        # AI / unconfirmed dependencies are rendered differently and never block (FR-M02).
        return "suggested"
    if dep.strength == PlanningDependency.Strength.SOFT:
        return "soft"
    return "hard"


def create_dependency(workspace, principal, data):
    user = principal.user
    predecessor, successor = _parse_node(data, "predecessor"), _parse_node(data, "successor")
    if predecessor == successor:
        raise ValidationFailed(
            "A node cannot depend on itself", code="DEPENDENCY_CYCLE", detail={"path": ["self", "self"]}
        )
    nodes = resolve_nodes(workspace.id, [predecessor, successor])
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    for key in (predecessor, successor):
        node = nodes.get(key)
        if node is None or node["project_id"] not in readable:
            raise NotFound("Dependency node not found")
    _require_plan(user, workspace.id, [nodes[predecessor]["project_id"], nodes[successor]["project_id"]])
    strength = data.get("strength") or PlanningDependency.Strength.HARD
    if strength not in PlanningDependency.Strength.values:
        raise ValidationFailed("strength must be hard or soft", detail={"field": "strength"})
    if principal.is_human:
        source = data.get("source") or "human"
        if source not in ("human", "import", "native_relation"):
            source = "human"
        confirmation = data.get("confirmation") or PlanningDependency.Confirmation.CONFIRMED
        if confirmation not in (PlanningDependency.Confirmation.CONFIRMED, PlanningDependency.Confirmation.SUGGESTED):
            raise ValidationFailed("confirmation must be confirmed or suggested", detail={"field": "confirmation"})
    else:
        # Agents/AI can only suggest; suggestions never block (FR-M02).
        source, confirmation = "ai", PlanningDependency.Confirmation.SUGGESTED
    with transaction.atomic():
        if strength == "hard" and confirmation == "confirmed":
            path = find_cycle(workspace.id, predecessor, successor)
            if path:
                raise _cycle_error(workspace.id, user, path)
        try:
            with transaction.atomic():
                dep = PlanningDependency.objects.create(
                    workspace=workspace,
                    predecessor_type=predecessor[0],
                    predecessor_id=predecessor[1],
                    predecessor_project_id=nodes[predecessor]["project_id"],
                    successor_type=successor[0],
                    successor_id=successor[1],
                    successor_project_id=nodes[successor]["project_id"],
                    strength=strength,
                    confirmation=confirmation,
                    source=source,
                    confirmed_by=user if confirmation == "confirmed" else None,
                    allow_anonymous_blocker=bool(data.get("allow_anonymous_blocker", False)),
                    note=str(data.get("note") or "")[:5000],
                    created_by=user,
                )
        except IntegrityError:
            raise Conflict("Dependency already exists", code="DEPENDENCY_EXISTS")
        _dependency_changed(workspace.id, principal, dep, "created")
    return serialize_dependency(dep, nodes)


def _load_dependency(workspace, user, dep_id):
    dep = PlanningDependency.objects.filter(id=dep_id, workspace=workspace, deleted_at__isnull=True).first()
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    if dep is None or not _dep_fully_readable(dep, readable):
        raise NotFound("Dependency not found")
    return dep


def _dep_fully_readable(dep, readable):
    return str(dep.predecessor_project_id) in readable and str(dep.successor_project_id) in readable


def confirm_dependency(workspace, principal, dep_id, *, reject=False):
    _require_human(principal, "Confirming a dependency")
    user = principal.user
    with transaction.atomic():
        dep = _load_dependency(workspace, user, dep_id)
        dep = PlanningDependency.objects.select_for_update().get(pk=dep.pk)
        _require_plan(user, workspace.id, [dep.predecessor_project_id, dep.successor_project_id])
        if reject:
            dep.confirmation = PlanningDependency.Confirmation.REJECTED
        else:
            if dep.strength == PlanningDependency.Strength.HARD:
                path = find_cycle(
                    workspace.id,
                    (dep.predecessor_type, str(dep.predecessor_id)),
                    (dep.successor_type, str(dep.successor_id)),
                    exclude_id=dep.id,
                )
                if path:
                    raise _cycle_error(workspace.id, user, path)
            dep.confirmation = PlanningDependency.Confirmation.CONFIRMED
            dep.confirmed_by = user
        dep.updated_by = user
        dep.save()
        _dependency_changed(workspace.id, principal, dep, "rejected" if reject else "confirmed")
    nodes = resolve_nodes(
        workspace.id, [(dep.predecessor_type, dep.predecessor_id), (dep.successor_type, dep.successor_id)]
    )
    return serialize_dependency(dep, nodes)


def delete_dependency(workspace, principal, dep_id):
    user = principal.user
    with transaction.atomic():
        dep = _load_dependency(workspace, user, dep_id)
        _require_plan(user, workspace.id, [dep.predecessor_project_id, dep.successor_project_id])
        dep.delete()
        _dependency_changed(workspace.id, principal, dep, "deleted")


def _dependency_changed(workspace_id, principal, dep, action):
    events.emit(
        workspace_id=workspace_id,
        project_id=dep.successor_project_id,
        event_type="dependency.changed",
        aggregate_type="dependency",
        aggregate_id=dep.id,
        actor_kind=principal.kind,
        actor_id=principal.id,
        payload={"action": action, "strength": dep.strength, "confirmation": dep.confirmation, "source": dep.source},
        summary=f"Dependency {action}",
    )
    refresh_automatic_risks(workspace_id)


def list_dependencies(workspace, user, project_ids=None):
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    qs = PlanningDependency.objects.filter(workspace=workspace, deleted_at__isnull=True).exclude(
        confirmation=PlanningDependency.Confirmation.REJECTED
    )
    deps = list(qs)
    return build_graph(workspace.id, deps, readable, scope=set(project_ids) if project_ids else readable)


def build_graph(workspace_id, deps, readable, scope):
    """Redacted node/edge graph (AC25). ``scope`` = projects whose deps are requested."""
    keys = set()
    for dep in deps:
        keys.add((dep.predecessor_type, str(dep.predecessor_id)))
        keys.add((dep.successor_type, str(dep.successor_id)))
    nodes = resolve_nodes(workspace_id, keys)
    out_nodes, out_edges, anon = {}, [], 0
    for dep in deps:
        pred = nodes.get((dep.predecessor_type, str(dep.predecessor_id)))
        succ = nodes.get((dep.successor_type, str(dep.successor_id)))
        if pred is None or succ is None:
            continue
        pred_ok, succ_ok = pred["project_id"] in readable, succ["project_id"] in readable
        if not (pred["project_id"] in scope or succ["project_id"] in scope):
            continue
        if pred_ok and succ_ok:
            out_nodes[_node_key(pred)] = {"key": _node_key(pred), **_public_node(pred)}
            out_nodes[_node_key(succ)] = {"key": _node_key(succ), **_public_node(succ)}
            edge = serialize_dependency(dep, nodes)
            edge.update({"source_key": _node_key(pred), "target_key": _node_key(succ)})
            out_edges.append(edge)
        elif succ_ok and not pred_ok and dep.allow_anonymous_blocker:
            anon += 1
            blocker = _anonymous_blocker(anon)
            out_nodes[blocker["key"]] = blocker
            out_nodes[_node_key(succ)] = {"key": _node_key(succ), **_public_node(succ)}
            out_edges.append(
                {
                    "id": f"external-edge:{anon}",
                    "source_key": blocker["key"],
                    "target_key": _node_key(succ),
                    "strength": dep.strength,
                    "confirmation": dep.confirmation,
                    "blocking": dep.strength == "hard" and dep.confirmation == "confirmed",
                    "style": "external",
                }
            )
        # Any other hidden endpoint: node and edge are omitted entirely.
    return {"nodes": list(out_nodes.values()), "edges": out_edges}


# ---------------------------------------------------------------------------
# milestones (FR-C06, FR-M04)
# ---------------------------------------------------------------------------
def serialize_milestone(m, display_tz=None):
    reliable = m.target_at is not None and m.date_confidence != "unknown"
    body = {
        "id": str(m.id),
        "project_id": str(m.project_id),
        "name": m.name,
        "description": m.description,
        "target_at": iso_utc(m.target_at),
        "timezone": m.timezone,
        "target_local": in_zone(m.target_at, m.timezone),
        "owner_id": str(m.owner_id) if m.owner_id else None,
        "status": m.status,
        "issues": m.issues,
        "date_confidence": m.date_confidence,
        "reliable_date": reliable,
        "date_label": None if reliable else NO_RELIABLE_DATE,
    }
    if display_tz:
        body["display_timezone"] = display_tz
        body["target_display"] = in_zone(m.target_at, display_tz)
    return body


def _milestone_fields(project, data, instance=None):
    values = {}
    tz_name = data.get("timezone", instance.timezone if instance else "UTC") or "UTC"
    _zone(tz_name)
    if instance is None or "timezone" in data:
        values["timezone"] = tz_name
    if instance is None or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationFailed("name is required", detail={"field": "name"})
        values["name"] = name[:255]
    if "description" in data:
        values["description"] = str(data.get("description") or "")
    if instance is None or "target_at" in data:
        values["target_at"] = parse_instant(data.get("target_at"), tz_name)
    if instance is None or "date_confidence" in data:
        confidence = data.get("date_confidence") or ("estimated" if values.get("target_at") else "unknown")
        if confidence not in DATE_CONFIDENCE:
            raise ValidationFailed(
                "date_confidence must be confirmed|estimated|unknown", detail={"field": "date_confidence"}
            )
        values["date_confidence"] = confidence
    if "status" in data:
        if data["status"] not in MILESTONE_STATUS:
            raise ValidationFailed("invalid status", detail={"field": "status"})
        values["status"] = data["status"]
    if "owner_id" in data:
        owner_id = data.get("owner_id")
        if owner_id and not ProjectMember.objects.filter(project=project, member_id=owner_id, is_active=True).exists():
            raise ValidationFailed("owner must be a project member", detail={"field": "owner_id"})
        values["owner_id"] = owner_id or None
    if "issues" in data:
        issue_ids = data.get("issues") or []
        if not isinstance(issue_ids, list):
            raise ValidationFailed("issues must be a list", detail={"field": "issues"})
        found = set(
            str(i)
            for i in Issue.all_objects.filter(id__in=issue_ids, project=project, deleted_at__isnull=True).values_list(
                "id", flat=True
            )
        )
        if len(found) != len({str(i) for i in issue_ids}):
            raise ValidationFailed("issues must belong to the project", detail={"field": "issues"})
        values["issues"] = sorted(found)
    return values


def create_milestone(project, principal, data):
    values = _milestone_fields(project, data)
    with transaction.atomic():
        m = Milestone.objects.create(
            workspace_id=project.workspace_id, project=project, created_by=principal.user, **values
        )
        _milestone_changed(project, principal, m, "created")
    return m


def update_milestone(project, principal, milestone_id, data):
    with transaction.atomic():
        m = (
            Milestone.objects.select_for_update()
            .filter(id=milestone_id, project=project, deleted_at__isnull=True)
            .first()
        )
        if m is None:
            raise NotFound("Milestone not found")
        for key, value in _milestone_fields(project, data, m).items():
            setattr(m, key, value)
        m.updated_by = principal.user
        m.save()
        _milestone_changed(project, principal, m, "updated")
    return m


def delete_milestone(project, principal, milestone_id):
    with transaction.atomic():
        m = Milestone.objects.filter(id=milestone_id, project=project, deleted_at__isnull=True).first()
        if m is None:
            raise NotFound("Milestone not found")
        m.delete()
        _milestone_changed(project, principal, m, "deleted")


def _milestone_changed(project, principal, m, action):
    events.emit(
        workspace_id=project.workspace_id,
        project_id=project.id,
        event_type="milestone.changed",
        aggregate_type="milestone",
        aggregate_id=m.id,
        actor_kind=principal.kind,
        actor_id=principal.id,
        payload={"action": action, "targetAt": iso_utc(m.target_at), "timezone": m.timezone},
        summary=f"Milestone '{m.name}' {action}",
    )
    refresh_automatic_risks(project.workspace_id)


# ---------------------------------------------------------------------------
# risks (FR-M06)
# ---------------------------------------------------------------------------
def refresh_automatic_risks(workspace_id):
    """Create/resolve automatic 'milestone at risk' risks from confirmed hard deps.

    A risk exists while a confirmed hard predecessor is due after the successor
    milestone's target. ``cause`` links the late predecessor (never a bare score).
    """
    deps = list(
        PlanningDependency.objects.filter(
            workspace_id=workspace_id,
            deleted_at__isnull=True,
            strength=PlanningDependency.Strength.HARD,
            confirmation=PlanningDependency.Confirmation.CONFIRMED,
            successor_type=PlanningDependency.NodeType.MILESTONE,
        )
    )
    keys = set()
    for dep in deps:
        keys.add((dep.predecessor_type, str(dep.predecessor_id)))
        keys.add((dep.successor_type, str(dep.successor_id)))
    nodes = resolve_nodes(workspace_id, keys)
    at_risk = {}
    for dep in deps:
        pred = nodes.get((dep.predecessor_type, str(dep.predecessor_id)))
        succ = nodes.get((dep.successor_type, str(dep.successor_id)))
        if not pred or not succ or not succ["target_instant"] or not pred["target_instant"]:
            continue
        if pred["target_instant"] > succ["target_instant"]:
            at_risk[str(dep.id)] = (dep, pred, succ)
    open_auto = {
        r.cause.get("dependency_id"): r
        for r in Risk.objects.filter(
            workspace_id=workspace_id, origin="automatic", status="open", deleted_at__isnull=True
        )
    }
    for dep_id, (dep, pred, succ) in at_risk.items():
        cause = {
            "type": "late_predecessor",
            "dependency_id": dep_id,
            "predecessor": {
                "type": pred["type"],
                "id": pred["id"],
                "project_id": pred["project_id"],
                "target_at": iso_utc(pred["target_instant"]),
            },
            "successor": {
                "type": "milestone",
                "id": succ["id"],
                "project_id": succ["project_id"],
                "target_at": iso_utc(succ["target_instant"]),
            },
        }
        risk = open_auto.pop(dep_id, None)
        if risk is None:
            Risk.objects.create(
                workspace_id=workspace_id,
                project_id=succ["project_id"],
                title=f"Milestone at risk: {succ['label']}"[:255],
                description="A confirmed hard prerequisite is planned to finish after this milestone's target.",
                severity="high",
                status="open",
                origin="automatic",
                cause=cause,
            )
        elif risk.cause != cause:
            risk.cause = cause
            risk.save(update_fields=["cause", "updated_at"])
    for risk in open_auto.values():
        risk.status = "resolved"
        risk.save(update_fields=["status", "updated_at"])


def serialize_risk(risk, user, readable=None):
    """Returns None when the risk's cause must stay hidden from this viewer (PRD §15.2)."""
    body = {
        "id": str(risk.id),
        "project_id": str(risk.project_id) if risk.project_id else None,
        "title": risk.title,
        "description": risk.description,
        "owner_id": str(risk.owner_id) if risk.owner_id else None,
        "severity": risk.severity,
        "status": risk.status,
        "origin": risk.origin,
        "cause": dict(risk.cause or {}),
    }
    pred = body["cause"].get("predecessor")
    if pred:
        if readable is None:
            readable = {str(p) for p in accessible_project_ids(user, risk.workspace_id)}
        if pred.get("project_id") in readable:
            node = resolve_nodes(risk.workspace_id, [(pred["type"], pred["id"])]).get((pred["type"], pred["id"]))
            pred = {
                **pred,
                "label": node["label"] if node else None,
                "link": {"type": pred["type"], "id": pred["id"], "project_id": pred["project_id"]},
            }
            body["cause"]["predecessor"] = pred
        else:
            dep = PlanningDependency.objects.filter(id=body["cause"].get("dependency_id")).first()
            if dep is None or not dep.allow_anonymous_blocker:
                return None
            body["cause"] = {
                "type": "late_predecessor",
                "predecessor": {"type": "external_blocker", "label": EXTERNAL_BLOCKER_LABEL},
            }
    return body


def list_risks(project, user):
    readable = {str(p) for p in accessible_project_ids(user, project.workspace_id)}
    out = []
    for risk in Risk.objects.filter(project=project, deleted_at__isnull=True).order_by("-created_at"):
        body = serialize_risk(risk, user, readable)
        if body is not None:
            out.append(body)
    return out


def create_risk(project, principal, data):
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValidationFailed("title is required", detail={"field": "title"})
    owner_id = data.get("owner_id")
    if owner_id and not ProjectMember.objects.filter(project=project, member_id=owner_id, is_active=True).exists():
        raise ValidationFailed("owner must be a project member", detail={"field": "owner_id"})
    cause = data.get("cause") or {}
    if not isinstance(cause, dict):
        raise ValidationFailed("cause must be an object", detail={"field": "cause"})
    return Risk.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        title=title[:255],
        description=str(data.get("description") or ""),
        owner_id=owner_id or None,
        severity=str(data.get("severity") or "medium")[:16],
        status="open",
        origin="human",
        cause=cause,
        created_by=principal.user,
    )


def update_risk(project, principal, risk_id, data):
    risk = Risk.objects.filter(id=risk_id, project=project, deleted_at__isnull=True).first()
    if risk is None:
        raise NotFound("Risk not found")
    for key in ("title", "description", "severity", "status"):
        if key in data:
            setattr(risk, key, str(data[key] or "")[: 255 if key == "title" else 5000])
    if "owner_id" in data:
        owner_id = data.get("owner_id")
        if owner_id and not ProjectMember.objects.filter(project=project, member_id=owner_id, is_active=True).exists():
            raise ValidationFailed("owner must be a project member", detail={"field": "owner_id"})
        risk.owner_id = owner_id or None
    risk.updated_by = principal.user
    risk.save()
    return risk


# ---------------------------------------------------------------------------
# scenarios (FR-M03)
# ---------------------------------------------------------------------------
def _normalize_changes(workspace, user, changes):
    if not isinstance(changes, list) or not changes:
        raise ValidationFailed("changes must be a non-empty list", detail={"field": "changes"})
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    out = []
    for change in changes:
        if not isinstance(change, dict) or change.get("type") != "milestone" or not change.get("id"):
            raise ValidationFailed("only milestone date changes are supported", detail={"field": "changes"})
        m = Milestone.objects.filter(id=change["id"], workspace=workspace, deleted_at__isnull=True).first()
        if m is None or str(m.project_id) not in readable:
            raise NotFound("Milestone not found")
        target = parse_instant(change.get("target_at"), m.timezone)
        entry = {"type": "milestone", "id": str(m.id), "project_id": str(m.project_id), "target_at": iso_utc(target)}
        if change.get("date_confidence"):
            if change["date_confidence"] not in DATE_CONFIDENCE:
                raise ValidationFailed("invalid date_confidence", detail={"field": "changes"})
            entry["date_confidence"] = change["date_confidence"]
        out.append(entry)
    return out


def create_scenario(workspace, principal, data):
    name = str(data.get("name") or "").strip() or "Scenario"
    changes = _normalize_changes(workspace, principal.user, data.get("changes"))
    return PlanScenario.objects.create(
        workspace=workspace, name=name[:255], changes=changes, status="draft", created_by=principal.user
    )


def serialize_scenario(s):
    return {
        "id": str(s.id),
        "name": s.name,
        "changes": s.changes,
        "status": s.status,
        "applied_by": str(s.applied_by_id) if s.applied_by_id else None,
        "created_by": str(s.created_by_id) if s.created_by_id else None,
    }


def load_scenario(workspace, user, scenario_id):
    s = PlanScenario.objects.filter(id=scenario_id, workspace=workspace, deleted_at__isnull=True).first()
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    if s is None or any(c.get("project_id") not in readable for c in s.changes):
        raise NotFound("Scenario not found")
    return s


def scenario_impact(workspace, user, scenario):
    """Direct + transitive successors via confirmed deps. Read-only: nothing is modified."""
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    graph = defaultdict(list)
    for dep in PlanningDependency.objects.filter(
        workspace=workspace, deleted_at__isnull=True, confirmation=PlanningDependency.Confirmation.CONFIRMED
    ):
        graph[(dep.predecessor_type, str(dep.predecessor_id))].append(
            ((dep.successor_type, str(dep.successor_id)), dep)
        )
    all_keys = {k for k in graph} | {s for edges in graph.values() for s, _ in edges}
    all_keys |= {("milestone", c["id"]) for c in scenario.changes}
    nodes = resolve_nodes(workspace.id, all_keys)
    changes_out, affected = [], {}
    for change in scenario.changes:
        start = ("milestone", change["id"])
        node = nodes.get(start)
        new_target = parse_instant(change["target_at"]) if change.get("target_at") else None
        changes_out.append(
            {
                **change,
                "label": node["label"] if node else None,
                "current_target_at": iso_utc(node["target_instant"]) if node else None,
                "new_target_at": iso_utc(new_target),
            }
        )
        queue = [(start, 0, [node["label"] if node else start[1]])]
        seen = {start}
        while queue:
            current, depth, via = queue.pop(0)
            for succ_key, dep in graph.get(current, []):
                if succ_key in seen:
                    continue
                seen.add(succ_key)
                succ = nodes.get(succ_key)
                if succ is None or succ["project_id"] not in readable:
                    continue  # hidden successors (and anything behind them) are not revealed
                key = _node_key(succ)
                late = bool(
                    depth == 0 and new_target and succ["target_instant"] and new_target > succ["target_instant"]
                )
                entry = affected.get(key)
                if entry is None or entry["depth"] > depth + 1:
                    affected[key] = {
                        "key": key,
                        **_public_node(succ),
                        "current_target": succ["target"],
                        "current_start": succ["start"],
                        "depth": depth + 1,
                        "direct": depth == 0,
                        "via": via + [succ["label"]],
                        "dependency_strength": dep.strength,
                        "would_be_affected": True,
                        "would_be_late": late or (entry or {}).get("would_be_late", False),
                    }
                queue.append((succ_key, depth + 1, via + [succ["label"]]))
    return {
        "scenario": serialize_scenario(scenario),
        "changes": changes_out,
        "affected": sorted(affected.values(), key=lambda a: (a["depth"], a["label"])),
        "modifies_plan": False,
    }


def apply_scenario(workspace, principal, scenario_id):
    """Apply only the milestone changes explicitly in the scenario; successors are not rewritten."""
    _require_human(principal, "Applying a scenario")
    user = principal.user
    with transaction.atomic():
        scenario = load_scenario(workspace, user, scenario_id)
        scenario = PlanScenario.objects.select_for_update().get(pk=scenario.pk)
        if scenario.status != "draft":
            raise Conflict(f"Scenario is {scenario.status}", code="SCENARIO_NOT_DRAFT")
        _require_plan(user, workspace.id, [c["project_id"] for c in scenario.changes])
        applied = []
        for change in scenario.changes:
            m = Milestone.objects.select_for_update().get(id=change["id"])
            before = iso_utc(m.target_at)
            m.target_at = parse_instant(change["target_at"]) if change.get("target_at") else None
            if change.get("date_confidence"):
                m.date_confidence = change["date_confidence"]
            m.updated_by = user
            m.save()
            applied.append({"id": str(m.id), "before": before, "after": iso_utc(m.target_at)})
            events.emit(
                workspace_id=workspace.id,
                project_id=m.project_id,
                event_type="milestone.changed",
                aggregate_type="milestone",
                aggregate_id=m.id,
                actor_kind=principal.kind,
                actor_id=principal.id,
                payload={
                    "action": "scenario_applied",
                    "scenarioId": str(scenario.id),
                    "before": before,
                    "after": iso_utc(m.target_at),
                },
                summary=f"Milestone '{m.name}' moved by scenario '{scenario.name}'",
            )
        scenario.status = "applied"
        scenario.applied_by = user
        scenario.save(update_fields=["status", "applied_by", "updated_at"])
        refresh_automatic_risks(workspace.id)
    return {"scenario": serialize_scenario(scenario), "applied": applied, "successors_changed": []}


# ---------------------------------------------------------------------------
# calendar (FR-C06): export only, no bidirectional sync
# ---------------------------------------------------------------------------
def serialize_event(e, display_tz=None):
    body = {
        "id": str(e.id),
        "project_id": str(e.project_id),
        "title": e.title,
        "description": e.description,
        "starts_at": iso_utc(e.starts_at),
        "ends_at": iso_utc(e.ends_at),
        "timezone": e.timezone,
        "starts_local": in_zone(e.starts_at, e.timezone),
        "owner_id": str(e.owner_id) if e.owner_id else None,
        "issue_id": str(e.issue_id) if e.issue_id else None,
    }
    if display_tz:
        body["starts_display"] = in_zone(e.starts_at, display_tz)
    return body


def create_event(project, principal, data):
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValidationFailed("title is required", detail={"field": "title"})
    tz_name = data.get("timezone") or "UTC"
    _zone(tz_name)
    starts = parse_instant(data.get("starts_at"), tz_name, "starts_at")
    if starts is None:
        raise ValidationFailed("starts_at is required", detail={"field": "starts_at"})
    ends = parse_instant(data.get("ends_at"), tz_name, "ends_at")
    if ends is not None and ends < starts:
        raise ValidationFailed("ends_at must be after starts_at", detail={"field": "ends_at"})
    owner_id = data.get("owner_id") or principal.user.id
    if not ProjectMember.objects.filter(project=project, member_id=owner_id, is_active=True).exists():
        raise ValidationFailed("owner must be a project member", detail={"field": "owner_id"})
    issue_id = data.get("issue_id")
    if issue_id and not Issue.all_objects.filter(id=issue_id, project=project, deleted_at__isnull=True).exists():
        raise NotFound("Work item not found")
    return CalendarEvent.objects.create(
        workspace_id=project.workspace_id,
        project=project,
        title=title[:255],
        description=str(data.get("description") or ""),
        starts_at=starts,
        ends_at=ends,
        timezone=tz_name,
        owner_id=owner_id,
        issue_id=issue_id or None,
        created_by=principal.user,
    )


def _ics_escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_fold(line):
    """Fold lines longer than 75 octets (RFC 5545 §3.1)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        b = char.encode("utf-8")
        limit = 75 if not parts else 74
        if len(current) + len(b) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _ics_time(value):
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def render_ics(project):
    now = _ics_time(timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Project Hub//Plane package-flow//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(project.name)}",
    ]
    for m in Milestone.objects.filter(project=project, deleted_at__isnull=True, target_at__isnull=False):
        summary = f"Milestone: {m.name}"
        if m.date_confidence == "unknown":
            summary += f" ({NO_RELIABLE_DATE})"
        lines += [
            "BEGIN:VEVENT",
            f"UID:milestone-{m.id}@project-hub",
            f"DTSTAMP:{now}",
            f"DTSTART:{_ics_time(m.target_at)}",
            f"DTEND:{_ics_time(m.target_at)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(m.description)}",
            f"X-PROJECT-HUB-TIMEZONE:{_ics_escape(m.timezone)}",
            "END:VEVENT",
        ]
    for e in CalendarEvent.objects.filter(project=project, deleted_at__isnull=True):
        lines += [
            "BEGIN:VEVENT",
            f"UID:event-{e.id}@project-hub",
            f"DTSTAMP:{now}",
            f"DTSTART:{_ics_time(e.starts_at)}",
            f"DTEND:{_ics_time(e.ends_at or e.starts_at)}",
            f"SUMMARY:{_ics_escape(e.title)}",
            f"DESCRIPTION:{_ics_escape(e.description)}",
            f"X-PROJECT-HUB-TIMEZONE:{_ics_escape(e.timezone)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"


# ---------------------------------------------------------------------------
# teams (FR-M01)
# ---------------------------------------------------------------------------
def _can_manage_teams(user, workspace_id):
    return workspace_role(user, workspace_id) == 20 or has_capability(user, workspace_id, None, Capability.PROJECT_PLAN)


def serialize_team(team, readable):
    scope = TeamScope.objects.filter(team=team, deleted_at__isnull=True).first()
    return {
        "id": str(team.id),
        "name": team.name,
        "description": team.description,
        # Hidden projects are not listed (no existence oracle).
        "project_ids": [p for p in (scope.projects if scope else []) if p in readable],
        "member_ids": list(scope.members) if scope else [],
    }


def list_teams(workspace, user):
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    return [serialize_team(t, readable) for t in Team.objects.filter(workspace=workspace).order_by("name")]


def upsert_team(workspace, principal, data, team_id=None):
    user = principal.user
    if not _can_manage_teams(user, workspace.id):
        raise PermissionDenied("Missing capability 'project.plan'", detail={"capability": "project.plan"})
    require_extension_enabled(workspace.id)
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    project_ids = [str(p) for p in data.get("project_ids") or []]
    if any(p not in readable for p in project_ids):
        raise NotFound("Project not found")
    member_ids = [str(m) for m in data.get("member_ids") or []]
    if member_ids and WorkspaceMember.objects.filter(
        workspace=workspace, member_id__in=member_ids, is_active=True
    ).count() != len(set(member_ids)):
        raise ValidationFailed("members must belong to the workspace", detail={"field": "member_ids"})
    with transaction.atomic():
        team_id = team_id or data.get("team_id")
        if team_id:
            team = Team.objects.filter(id=team_id, workspace=workspace).first()
            if team is None:
                raise NotFound("Team not found")
            if data.get("name"):
                team.name = str(data["name"])[:255]
                team.save()
        else:
            name = str(data.get("name") or "").strip()
            if not name:
                raise ValidationFailed("name is required", detail={"field": "name"})
            if Team.objects.filter(workspace=workspace, name=name).exists():
                raise Conflict("Team name already exists", code="TEAM_EXISTS")
            team = Team.objects.create(
                workspace=workspace, name=name[:255], description=str(data.get("description") or ""), created_by=user
            )
        scope, _ = TeamScope.objects.get_or_create(team=team, defaults={"workspace": workspace})
        if "project_ids" in data:
            # Keep hidden projects that the editor cannot see.
            hidden = [p for p in scope.projects if p not in readable]
            scope.projects = sorted(set(hidden + project_ids))
        if "member_ids" in data:
            scope.members = sorted(set(member_ids))
        scope.save()
    return serialize_team(team, readable)


# ---------------------------------------------------------------------------
# roadmap (FR-M01, FR-M04, FR-M05, AC25)
# ---------------------------------------------------------------------------
def _cycle_status(cycle, now):
    if cycle.start_date is None or cycle.end_date is None:
        return "draft"
    if cycle.start_date <= now <= cycle.end_date:
        return "current"
    return "upcoming" if cycle.start_date > now else "completed"


def roadmap(workspace, user, *, project_ids=None, team_id=None, date_from=None, date_to=None, display_tz=None):
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    visible = set(readable)
    if project_ids:
        visible &= {str(p) for p in project_ids}
    teams_by_project = defaultdict(list)
    for scope in TeamScope.objects.filter(workspace=workspace, deleted_at__isnull=True):
        for p in scope.projects:
            teams_by_project[str(p)].append(str(scope.team_id))
    if team_id:
        scope = TeamScope.objects.filter(team_id=team_id, workspace=workspace, deleted_at__isnull=True).first()
        if scope is None and not Team.objects.filter(id=team_id, workspace=workspace).exists():
            raise NotFound("Team not found")
        visible &= {str(p) for p in (scope.projects if scope else [])}
    start = parse_instant(date_from, "UTC", "from") if date_from else None
    end = parse_instant(date_to, "UTC", "to") if date_to else None
    if display_tz:
        _zone(display_tz)

    projects = [
        {"id": str(p.id), "name": p.name, "identifier": p.identifier, "team_ids": teams_by_project.get(str(p.id), [])}
        for p in Project.objects.filter(id__in=visible, workspace=workspace, deleted_at__isnull=True).order_by("name")
    ]
    ids = [p["id"] for p in projects]

    milestones = []
    for m in Milestone.objects.filter(project_id__in=ids, deleted_at__isnull=True):
        if m.target_at is not None and m.date_confidence != "unknown":
            if (start and m.target_at < start) or (end and m.target_at > end):
                continue
        milestones.append(serialize_milestone(m, display_tz))

    packages = []
    profiles = PackageProfile.objects.filter(
        project_id__in=ids, deleted_at__isnull=True, issue__deleted_at__isnull=True
    ).select_related("issue", "issue__project", "issue__state")
    for profile in profiles:
        issue = profile.issue
        if start and issue.target_date and _date_end_utc(issue.target_date) < start:
            continue
        if end and issue.start_date and dt.datetime.combine(issue.start_date, dt.time(0), tzinfo=UTC) > end:
            continue
        packages.append(
            {
                "id": str(issue.id),
                "work_item_id": str(issue.id),
                "project_id": str(issue.project_id),
                "label": _issue_label(issue),
                "name": issue.name,
                "state_group": issue.state.group if issue.state_id else None,
                "start_date": issue.start_date.isoformat() if issue.start_date else None,
                "target_date": issue.target_date.isoformat() if issue.target_date else None,
                "start_label": None if issue.start_date else "unknown",
                "target_label": None if issue.target_date else "unknown",
                "reliable_date": bool(issue.target_date),
            }
        )

    now = timezone.now()
    cycles = [
        {
            "id": str(c.id),
            "project_id": str(c.project_id),
            "name": c.name,
            "start_date": iso_utc(c.start_date),
            "end_date": iso_utc(c.end_date),
            "status": _cycle_status(c, now),
            "read_only": True,
        }
        for c in Cycle.objects.filter(project_id__in=ids, deleted_at__isnull=True, archived_at__isnull=True)
    ]
    modules = [
        {
            "id": str(mod.id),
            "project_id": str(mod.project_id),
            "name": mod.name,
            "status": mod.status,
            "start_date": mod.start_date.isoformat() if mod.start_date else None,
            "target_date": mod.target_date.isoformat() if mod.target_date else None,
            "read_only": True,
        }
        for mod in Module.objects.filter(project_id__in=ids, deleted_at__isnull=True, archived_at__isnull=True)
    ]
    deps = list(
        PlanningDependency.objects.filter(workspace=workspace, deleted_at__isnull=True)
        .exclude(confirmation=PlanningDependency.Confirmation.REJECTED)
        .filter(Q(predecessor_project_id__in=ids) | Q(successor_project_id__in=ids))
    )
    graph = build_graph(workspace.id, deps, readable, scope=set(ids))
    return {
        "projects": projects,
        "milestones": milestones,
        "packages": packages,
        "cycles": cycles,
        "modules": modules,
        "dependencies": graph["edges"],
        "nodes": graph["nodes"],
        "filters": {"project_ids": project_ids or [], "team_id": team_id, "from": date_from, "to": date_to},
    }


def cycles_context(project):
    """Native cycles as optional Scrum context (FR-M05). Cycles never block delivery."""
    now = timezone.now()
    package_issue_ids = PackageProfile.objects.filter(project=project, deleted_at__isnull=True).values("issue_id")
    counts = dict(
        CycleIssue.objects.filter(cycle__project=project, issue_id__in=package_issue_ids, deleted_at__isnull=True)
        .values_list("cycle_id")
        .annotate(n=Count("id"))
    )
    return {
        "cycles": [
            {
                "id": str(c.id),
                "name": c.name,
                "start_date": iso_utc(c.start_date),
                "end_date": iso_utc(c.end_date),
                "status": _cycle_status(c, now),
                "package_count": counts.get(c.id, 0),
                "read_only": True,
            }
            for c in Cycle.objects.filter(project=project, deleted_at__isnull=True, archived_at__isnull=True).order_by(
                "start_date"
            )
        ],
        "story_points_required": False,
        "delivery_blocked_until_cycle_end": False,
        "note": "Packages can be delivered at any time; cycles are optional planning context.",
    }
