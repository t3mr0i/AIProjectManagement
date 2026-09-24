# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Structured diagrams with separate layout and semantic diff (FR-E02, FR-E03, FR-E06, AC09, AC10).

Model:
  semantic = {"nodes": [{id, type, label, properties{}}], "edges": [{id, source, target, type, label?, properties{}}]}
  layout   = {node_id: {x, y, w, h}}

* Layout-only change -> new ``DiagramVersion(layout_only=True)``; no proposal,
  never a change request (AC09).
* Semantic change -> new version + pending ``AIProposal(kind=diagram_interpretation)``
  with interpretation, affected areas, possible impacts and uncertainty.
  Edges without type/label or with ambiguous direction become *questions*,
  not requirements (FR-E03).
* Accepting a proposal (human + ``package.edit``) only appends criteria/scope
  notes to the package working draft. It never creates a revision, an
  approval or a run (AC10).
"""

import uuid

from django.db import transaction
from django.utils import timezone

from ..errors import Conflict, HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import AIProposal, DiagramDocument, DiagramVersion, PackageProfile
from . import events

AMBIGUOUS_DIRECTIONS = {"both", "bidirectional", "unknown", "ambiguous", "?"}
LAYOUT_KEYS = ("x", "y", "w", "h")
MAX_NODES = 2000


# ---------------------------------------------------------------------------
# validation / normalization
# ---------------------------------------------------------------------------
def _props(value, where):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationFailed(f"{where}.properties must be an object", detail={"field": where})
    return value


def normalize_semantic(semantic) -> dict:
    if semantic is None:
        semantic = {}
    if not isinstance(semantic, dict):
        raise ValidationFailed("semantic must be an object", detail={"field": "semantic"})
    nodes_in, edges_in = semantic.get("nodes") or [], semantic.get("edges") or []
    if not isinstance(nodes_in, list) or not isinstance(edges_in, list):
        raise ValidationFailed("semantic.nodes and semantic.edges must be lists", detail={"field": "semantic"})
    if len(nodes_in) > MAX_NODES or len(edges_in) > MAX_NODES * 4:
        raise ValidationFailed("diagram too large", detail={"field": "semantic"})
    nodes, seen = [], set()
    for node in nodes_in:
        if not isinstance(node, dict) or not node.get("id"):
            raise ValidationFailed("every node needs a stable id", detail={"field": "semantic.nodes"})
        nid = str(node["id"])
        if nid in seen:
            raise ValidationFailed("duplicate node id", detail={"field": "semantic.nodes", "id": nid})
        seen.add(nid)
        nodes.append(
            {
                "id": nid,
                "type": str(node.get("type") or "component"),
                "label": str(node.get("label") or ""),
                "properties": _props(node.get("properties"), "node"),
            }
        )
    edges, edge_ids = [], set()
    for edge in edges_in:
        if not isinstance(edge, dict) or not edge.get("id"):
            raise ValidationFailed("every edge needs a stable id", detail={"field": "semantic.edges"})
        eid = str(edge["id"])
        if eid in edge_ids:
            raise ValidationFailed("duplicate edge id", detail={"field": "semantic.edges", "id": eid})
        edge_ids.add(eid)
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in seen or target not in seen:
            raise ValidationFailed("edge references an unknown node", detail={"field": "semantic.edges", "id": eid})
        edges.append(
            {
                "id": eid,
                "source": source,
                "target": target,
                "type": str(edge.get("type") or ""),
                "label": str(edge.get("label") or ""),
                "properties": _props(edge.get("properties"), "edge"),
            }
        )
    return {"nodes": nodes, "edges": edges}


def normalize_layout(layout, semantic) -> dict:
    if layout is None:
        layout = {}
    if not isinstance(layout, dict):
        raise ValidationFailed("layout must be an object {node_id: {x,y,w,h}}", detail={"field": "layout"})
    node_ids = {n["id"] for n in semantic["nodes"]}
    out = {}
    for node_id, box in layout.items():
        if node_id not in node_ids:
            continue  # stale layout for a removed node is dropped, never semantic
        if not isinstance(box, dict):
            raise ValidationFailed("layout entries must be objects", detail={"field": "layout", "id": node_id})
        entry = {}
        for key in LAYOUT_KEYS:
            if key in box and box[key] is not None:
                if not isinstance(box[key], (int, float)) or isinstance(box[key], bool):
                    raise ValidationFailed("layout values must be numbers", detail={"field": "layout", "id": node_id})
                entry[key] = box[key]
        out[str(node_id)] = entry
    return out


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
def _dict_diff(before: dict, after: dict) -> dict:
    changes = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return changes


def _element_diff(before: list, after: list, fields) -> dict:
    b = {e["id"]: e for e in before}
    a = {e["id"]: e for e in after}
    added = [a[i] for i in a if i not in b]
    removed = [b[i] for i in b if i not in a]
    changed = []
    for i in a:
        if i in b and a[i] != b[i]:
            entry = {
                "id": i,
                "fields": {},
                "properties": _dict_diff(b[i].get("properties", {}), a[i].get("properties", {})),
            }
            for f in fields:
                if b[i].get(f) != a[i].get(f):
                    entry["fields"][f] = {"before": b[i].get(f), "after": a[i].get(f)}
            changed.append(entry)
    return {"added": added, "removed": removed, "changed": changed}


def semantic_diff(before: dict, after: dict) -> dict:
    return {
        "nodes": _element_diff(before.get("nodes", []), after.get("nodes", []), ("type", "label")),
        "edges": _element_diff(before.get("edges", []), after.get("edges", []), ("source", "target", "type", "label")),
    }


def is_empty_semantic_diff(diff: dict) -> bool:
    return not any(diff[k][c] for k in ("nodes", "edges") for c in ("added", "removed", "changed"))


def layout_diff(before: dict, after: dict) -> dict:
    moved = {}
    for node_id in sorted(set(before) | set(after)):
        if before.get(node_id) != after.get(node_id):
            moved[node_id] = {"before": before.get(node_id), "after": after.get(node_id)}
    return {"changed": moved}


# ---------------------------------------------------------------------------
# interpretation (deterministic, reviewable; statements labelled per PRD §14.2)
# ---------------------------------------------------------------------------
def _is_ambiguous_edge(edge) -> str:
    if not edge.get("type") and not edge.get("label"):
        return "the connection has neither a type nor a label"
    direction = str((edge.get("properties") or {}).get("direction", "")).lower()
    if direction in AMBIGUOUS_DIRECTIONS:
        return "the direction of the connection is ambiguous"
    return ""


def interpret(diff: dict, semantic: dict) -> dict:
    labels = {n["id"]: (n["label"] or n["id"]) for n in semantic.get("nodes", [])}
    statements, questions, criteria, impacts, areas = [], [], [], [], []

    def area(node_id, label=None):
        name = label or labels.get(node_id, node_id)
        if name not in areas:
            areas.append(name)
        return name

    for node in diff["nodes"]["added"]:
        name = area(node["id"], node["label"] or node["id"])
        statements.append({"kind": "observed", "text": f"New {node['type']} '{name}' added."})
        impacts.append(f"'{name}' may need an owner, interfaces and acceptance criteria.")
    for node in diff["nodes"]["removed"]:
        name = area(node["id"], node["label"] or node["id"])
        statements.append({"kind": "observed", "text": f"{node['type']} '{name}' removed."})
        impacts.append(f"Requirements or tasks that reference '{name}' may become obsolete.")
    for change in diff["nodes"]["changed"]:
        name = area(change["id"])
        for key, value in {**change["fields"], **change["properties"]}.items():
            statements.append(
                {"kind": "observed", "text": f"'{name}': {key} changed from {value['before']!r} to {value['after']!r}."}
            )
        impacts.append(f"Behaviour or configuration of '{name}' may change.")
    for edge in diff["edges"]["added"] + [
        {**e, **{f: v["after"] for f, v in c["fields"].items()}}
        for c in diff["edges"]["changed"]
        for e in semantic.get("edges", [])
        if e["id"] == c["id"]
    ]:
        source, target = area(edge["source"]), area(edge["target"])
        reason = _is_ambiguous_edge(edge)
        if reason:
            questions.append(
                {
                    "edge_id": edge["id"],
                    "text": f"What does the connection between '{source}' and '{target}' mean, and in which "
                    f"direction does data or control flow? ({reason})",
                }
            )
            continue
        kind = edge.get("type") or edge.get("label")
        statements.append({"kind": "inferred", "text": f"'{source}' now {kind} '{target}'."})
        criteria.append(
            {
                "edge_id": edge["id"],
                "text": f"The {kind} interface from '{source}' to '{target}' is specified and verified.",
                "status": "proposed",
            }
        )
        impacts.append(f"Changes to '{target}' may now affect '{source}'.")
    for edge in diff["edges"]["removed"]:
        source, target = area(edge["source"]), area(edge["target"])
        statements.append({"kind": "observed", "text": f"Connection '{source}' -> '{target}' removed."})
        impacts.append(f"Integration between '{source}' and '{target}' may be dropped or replaced.")

    reasons = []
    if questions:
        reasons.append("Some connections are ambiguous and are asked as questions, not treated as requirements.")
    if diff["nodes"]["removed"] or diff["edges"]["removed"]:
        reasons.append("Removals may be intentional clean-up or accidental; please confirm.")
    level = "high" if questions else ("medium" if reasons or criteria else "low")
    reasons.append("Interpretation is derived from the structural diff only; no code context was used.")
    summary = "; ".join(s["text"] for s in statements[:5]) or "Structural change without clear requirement impact."
    return {
        "interpretation": summary,
        "statements": statements,
        "affected_areas": areas,
        "possible_impacts": impacts,
        "uncertainty": {"level": level, "reasons": reasons},
        "questions": questions,
        "suggested_criteria": criteria,
    }


# ---------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------
def serialize_diagram(diagram: DiagramDocument) -> dict:
    return {
        "id": str(diagram.id),
        "project_id": str(diagram.project_id),
        "workspace_id": str(diagram.workspace_id),
        "issue_id": str(diagram.issue_id) if diagram.issue_id else None,
        "page_id": str(diagram.page_id) if diagram.page_id else None,
        "name": diagram.name,
        "diagram_type": diagram.diagram_type,
        "semantic": diagram.semantic,
        "layout": diagram.layout,
        "version": diagram.version,
        "updated_at": diagram.updated_at.isoformat() if diagram.updated_at else None,
    }


def serialize_version(version: DiagramVersion) -> dict:
    return {
        "id": str(version.id),
        "version": version.version,
        "layout_only": version.layout_only,
        "semantic_diff": version.semantic_diff,
        "proposal_id": str(version.proposal_id) if version.proposal_id else None,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def serialize_proposal(proposal: AIProposal) -> dict:
    return {
        "id": str(proposal.id),
        "kind": proposal.kind,
        "status": proposal.status,
        "issue_id": str(proposal.issue_id) if proposal.issue_id else None,
        "content": proposal.content,
        "base_version": proposal.base_version,
        "decided_by": str(proposal.decided_by_id) if proposal.decided_by_id else None,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def create_diagram(project, principal, data: dict, issue=None) -> DiagramDocument:
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValidationFailed("name is required", detail={"field": "name"})
    semantic = normalize_semantic(data.get("semantic"))
    layout = normalize_layout(data.get("layout"), semantic)
    with transaction.atomic():
        diagram = DiagramDocument.objects.create(
            workspace_id=project.workspace_id,
            project=project,
            issue=issue,
            name=name[:255],
            diagram_type=str(data.get("diagram_type") or "architecture")[:32],
            semantic=semantic,
            layout=layout,
            version=1,
            created_by=principal.user,
        )
        DiagramVersion.objects.create(
            diagram=diagram,
            version=1,
            semantic=semantic,
            layout=layout,
            semantic_diff={},
            layout_only=False,
            created_by=principal.user,
        )
    return diagram


def update_diagram(diagram_id, project, principal, data: dict) -> dict:
    if "expected_version" not in data:
        raise ValidationFailed("expected_version is required", detail={"field": "expected_version"})
    with transaction.atomic():
        diagram = (
            DiagramDocument.objects.select_for_update()
            .filter(id=diagram_id, project=project, deleted_at__isnull=True)
            .first()
        )
        if diagram is None:
            raise NotFound("Diagram not found")
        try:
            expected = int(data.get("expected_version"))
        except (TypeError, ValueError):
            raise ValidationFailed("expected_version must be an integer", detail={"field": "expected_version"})
        if expected != diagram.version:
            raise Conflict(
                "Diagram changed concurrently",
                code="VERSION_CONFLICT",
                detail={"expected_version": expected, "current_version": diagram.version},
            )
        semantic = normalize_semantic(data["semantic"]) if "semantic" in data else diagram.semantic
        layout = normalize_layout(data.get("layout", diagram.layout), semantic)
        s_diff = semantic_diff(diagram.semantic or {"nodes": [], "edges": []}, semantic)
        l_diff = layout_diff(normalize_layout(diagram.layout, semantic), layout)
        semantic_changed = not is_empty_semantic_diff(s_diff)
        if not semantic_changed and not l_diff["changed"]:
            return {
                "changed": False,
                "layout_only": False,
                "semantic_diff": s_diff,
                "layout_diff": l_diff,
                "proposal_id": None,
                "diagram": serialize_diagram(diagram),
            }
        diagram.version += 1
        diagram.semantic = semantic
        diagram.layout = layout
        if "name" in data and str(data["name"]).strip():
            diagram.name = str(data["name"]).strip()[:255]
        diagram.updated_by = principal.user
        diagram.save()
        proposal = None
        if semantic_changed:
            # Supersede older open interpretations of this diagram.
            AIProposal.objects.filter(
                project=project,
                kind=AIProposal.Kind.DIAGRAM_INTERPRETATION,
                status=AIProposal.Status.PENDING,
                content__diagram_id=str(diagram.id),
            ).update(status=AIProposal.Status.STALE)
            content = interpret(s_diff, semantic)
            content.update(
                {
                    "diagram_id": str(diagram.id),
                    "diagram_version": diagram.version,
                    "semantic_diff": s_diff,
                    "requires_human_acceptance": True,
                    "creates_revision": False,
                }
            )
            proposal = AIProposal.objects.create(
                workspace_id=project.workspace_id,
                project=project,
                issue_id=diagram.issue_id,
                kind=AIProposal.Kind.DIAGRAM_INTERPRETATION,
                status=AIProposal.Status.PENDING,
                requested_by=principal.user,
                content=content,
                selection={"diagram_id": str(diagram.id), "version": diagram.version},
                sources=[{"type": "diagram", "id": str(diagram.id), "version": diagram.version}],
                base_version=str(diagram.version),
                created_by=principal.user,
            )
        version = DiagramVersion.objects.create(
            diagram=diagram,
            version=diagram.version,
            semantic=semantic,
            layout=layout,
            semantic_diff=s_diff if semantic_changed else {},
            layout_only=not semantic_changed,
            proposal=proposal,
            created_by=principal.user,
        )
        events.emit(
            workspace_id=project.workspace_id,
            project_id=project.id,
            issue_id=diagram.issue_id,
            event_type="diagram.changed",
            aggregate_type="diagram",
            aggregate_id=diagram.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            payload={
                "version": diagram.version,
                "layoutOnly": not semantic_changed,
                "proposalId": str(proposal.id) if proposal else None,
            },
            summary=f"Diagram '{diagram.name}' " + ("semantic change" if semantic_changed else "layout change"),
        )
    return {
        "changed": True,
        "layout_only": not semantic_changed,
        "semantic_diff": s_diff,
        "layout_diff": l_diff,
        "proposal_id": str(proposal.id) if proposal else None,
        "proposal": serialize_proposal(proposal) if proposal else None,
        "version": serialize_version(version),
        "diagram": serialize_diagram(diagram),
    }


def _load_proposal(diagram_id, proposal_id, project):
    proposal = (
        AIProposal.objects.select_for_update()
        .filter(
            id=proposal_id,
            project=project,
            kind=AIProposal.Kind.DIAGRAM_INTERPRETATION,
            content__diagram_id=str(diagram_id),
            deleted_at__isnull=True,
        )
        .first()
    )
    if proposal is None:
        raise NotFound("Proposal not found")
    if proposal.status != AIProposal.Status.PENDING:
        raise Conflict(
            f"Proposal is {proposal.status}", code="PROPOSAL_NOT_PENDING", detail={"status": proposal.status}
        )
    return proposal


def apply_proposal_to_draft(proposal, user, selected_edge_ids=None) -> dict:
    """Append accepted suggestions to the package working draft only (never revision/approval/run).

    Also the hook used by the generic ``P/proposals/{id}/accept`` endpoint, which
    handles the proposal status itself.
    """
    content = proposal.content or {}
    issue_id = proposal.issue_id
    if issue_id is None:
        raise ValidationFailed(
            "Diagram is not linked to a work package",
            code="NO_PACKAGE",
            detail={"diagram_id": content.get("diagram_id")},
        )
    profile = PackageProfile.objects.select_for_update().filter(issue_id=issue_id, deleted_at__isnull=True).first()
    if profile is None:
        raise NotFound("Work item has no package profile", code="NO_PROFILE")
    suggestions = [
        c
        for c in content.get("suggested_criteria", [])
        if selected_edge_ids is None or c.get("edge_id") in selected_edge_ids
    ]
    criteria = list(profile.criteria or [])
    existing_ids = {c.get("id") for c in criteria if isinstance(c, dict)}
    added = []
    for suggestion in suggestions:
        cid = f"D-{uuid.uuid4().hex[:8]}"
        while cid in existing_ids:
            cid = f"D-{uuid.uuid4().hex[:8]}"
        existing_ids.add(cid)
        criterion = {
            "id": cid,
            "text": suggestion["text"],
            "required": True,
            "source": {
                "type": "diagram_proposal",
                "proposal_id": str(proposal.id),
                "diagram_id": content.get("diagram_id"),
                "diagram_version": content.get("diagram_version"),
                "edge_id": suggestion.get("edge_id"),
            },
        }
        criteria.append(criterion)
        added.append(criterion)
    scope = dict(profile.scope or {})
    notes = list(scope.get("diagram_notes") or [])
    notes.append(
        {
            "proposal_id": str(proposal.id),
            "diagram_id": content.get("diagram_id"),
            "diagram_version": content.get("diagram_version"),
            "interpretation": content.get("interpretation", ""),
            "open_questions": [q["text"] for q in content.get("questions", [])],
            "accepted_by": str(user.id),
        }
    )
    scope["diagram_notes"] = notes
    profile.criteria = criteria
    profile.scope = scope
    profile.version = (profile.version or 0) + 1
    profile.save(update_fields=["criteria", "scope", "version", "updated_at"])
    events.audit(
        workspace_id=proposal.workspace_id,
        project_id=proposal.project_id,
        issue_id=issue_id,
        actor=user,
        actor_kind="human",
        action="diagram.proposal.accepted",
        target_type="ai_proposal",
        target_id=proposal.id,
        detail={"criteria_added": [c["id"] for c in added]},
    )
    return {
        "criteria_added": added,
        "profile_version": profile.version,
        # Draft only: a revision must still be created and approved elsewhere (AC10).
        "revision_created": False,
        "execution_approved": False,
    }


def accept_proposal(proposal, user) -> dict:
    """Hook for the generic proposal endpoint (collaboration workstream)."""
    return apply_proposal_to_draft(proposal, user)


def accept_diagram_proposal(diagram, proposal_id, principal, data=None) -> dict:
    """Human acceptance appends criteria/scope notes to the working draft only (AC10)."""
    if not principal.is_human:
        raise HumanPrincipalRequired("Only a human can accept a diagram interpretation")
    data = data or {}
    with transaction.atomic():
        proposal = _load_proposal(diagram.id, proposal_id, diagram.project)
        if diagram.issue_id is None:
            raise ValidationFailed(
                "Diagram is not linked to a work package", code="NO_PACKAGE", detail={"diagram_id": str(diagram.id)}
            )
        if proposal.issue_id is None:
            proposal.issue_id = diagram.issue_id
        applied = apply_proposal_to_draft(proposal, principal.user, data.get("criteria_edge_ids"))
        proposal.status = AIProposal.Status.ACCEPTED
        proposal.decided_by = principal.user
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=["issue", "status", "decided_by", "decided_at", "updated_at"])
    return {"proposal": serialize_proposal(proposal), **applied}


def reject_proposal(diagram, proposal_id, principal) -> dict:
    """Rejected interpretation leaves the shared draft unchanged (FR-E06)."""
    with transaction.atomic():
        proposal = _load_proposal(diagram.id, proposal_id, diagram.project)
        proposal.status = AIProposal.Status.REJECTED
        proposal.decided_by = principal.user
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return {"proposal": serialize_proposal(proposal)}
