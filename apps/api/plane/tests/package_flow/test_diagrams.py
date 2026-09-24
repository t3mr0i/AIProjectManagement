# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Structured diagrams: layout vs semantic diff and reviewable proposals (FR-E02, FR-E03, AC09, AC10, PF08)."""

import pytest

from plane.package_flow.models import (
    AIProposal,
    DiagramVersion,
    ExecutionApproval,
    ExecutionRun,
    PackageProfile,
    PackageRevision,
)

SEMANTIC = {
    "nodes": [
        {"id": "api", "type": "service", "label": "API", "properties": {"lang": "python"}},
        {"id": "db", "type": "database", "label": "Postgres", "properties": {}},
    ],
    "edges": [],
}
LAYOUT = {"api": {"x": 10, "y": 10, "w": 100, "h": 40}, "db": {"x": 300, "y": 10, "w": 100, "h": 40}}


def _setup(world, human_client):
    project = world.project()
    world.enable(project)
    issue = world.issue(project, name="Persist orders")
    PackageProfile.objects.create(issue=issue, criteria=[{"id": "C-1", "text": "Orders are stored"}])
    client = human_client(world.owner)
    r = client.post(
        f"{world.base(project)}/diagrams/",
        {"name": "Architecture", "issue_id": str(issue.id), "semantic": SEMANTIC, "layout": LAYOUT},
        format="json",
    )
    assert r.status_code == 201, r.content
    return project, issue, client, r.json()


def _put(client, world, project, diagram, **body):
    return client.put(f"{world.base(project)}/diagrams/{diagram['id']}/", body, format="json")


@pytest.mark.unit
class TestDiagrams:
    def test_ac09_layout_change_not_a_change_request(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        layout = {**LAYOUT, "api": {"x": 50, "y": 80, "w": 100, "h": 40}}
        r = _put(client, world, project, diagram, layout=layout, expected_version=1)
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["layout_only"] is True
        assert body["proposal_id"] is None
        assert body["layout_diff"]["changed"]["api"]["after"]["x"] == 50
        # Layout was saved as a new version, but no proposal / revision / run.
        assert DiagramVersion.objects.filter(diagram_id=diagram["id"], version=2, layout_only=True).exists()
        assert AIProposal.objects.filter(project=project).count() == 0
        assert PackageRevision.objects.filter(issue=issue).count() == 0
        assert body["diagram"]["layout"]["api"]["x"] == 50

    def test_pf08_roundtrip_and_layout_diff_keep_blocks(self, world, human_client):
        """Layout-only change keeps semantic blocks (nodes/properties) untouched."""
        project, issue, client, diagram = _setup(world, human_client)
        r = _put(client, world, project, diagram, layout={"api": {"x": 1, "y": 2}}, expected_version=1)
        assert r.json()["layout_only"] is True
        assert r.json()["diagram"]["semantic"] == SEMANTIC

    def test_version_conflict(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        assert _put(client, world, project, diagram, layout={}, expected_version=1).status_code == 200
        r = _put(client, world, project, diagram, layout={"db": {"x": 0}}, expected_version=1)
        assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"

    def test_ac10_semantic_change_creates_draft_proposal(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        semantic = {**SEMANTIC, "edges": [{"id": "e1", "source": "api", "target": "db", "type": "writes to"}]}
        r = _put(client, world, project, diagram, semantic=semantic, expected_version=1)
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["layout_only"] is False
        assert body["semantic_diff"]["edges"]["added"][0]["id"] == "e1"
        proposal = AIProposal.objects.get(id=body["proposal_id"])
        assert proposal.kind == AIProposal.Kind.DIAGRAM_INTERPRETATION
        assert proposal.status == AIProposal.Status.PENDING
        content = proposal.content
        assert "API" in content["interpretation"]
        assert content["affected_areas"] == ["API", "Postgres"]
        assert content["possible_impacts"]
        assert content["uncertainty"]["level"] in ("low", "medium", "high")
        assert content["suggested_criteria"][0]["edge_id"] == "e1"
        # Nothing became a revision, approval or run.
        profile = PackageProfile.objects.get(issue=issue)
        assert [c["id"] for c in profile.criteria] == ["C-1"]
        assert PackageRevision.objects.filter(issue=issue).count() == 0
        assert ExecutionApproval.objects.filter(issue=issue).count() == 0
        assert ExecutionRun.objects.filter(issue=issue).count() == 0

        # Agents cannot accept.
        _, token = world.runner(world.owner)
        from plane.tests.package_flow.conftest import runner_client_for

        url = f"{world.base(project)}/diagrams/{diagram['id']}/proposals/{proposal.id}/accept"
        r = runner_client_for(token).post(url, {}, format="json")
        assert r.status_code == 403

        # Human acceptance appends to the working draft only.
        r = client.post(url, {}, format="json")
        assert r.status_code == 200, r.content
        assert r.json()["revision_created"] is False and r.json()["execution_approved"] is False
        profile.refresh_from_db()
        assert len(profile.criteria) == 2
        assert profile.criteria[1]["source"]["proposal_id"] == str(proposal.id)
        assert profile.scope["diagram_notes"][0]["proposal_id"] == str(proposal.id)
        assert PackageRevision.objects.filter(issue=issue).count() == 0
        assert ExecutionApproval.objects.filter(issue=issue).count() == 0
        proposal.refresh_from_db()
        assert proposal.status == AIProposal.Status.ACCEPTED

    def test_fr_e03_ambiguous_edge_is_question(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        semantic = {**SEMANTIC, "edges": [{"id": "e1", "source": "api", "target": "db"}]}
        r = _put(client, world, project, diagram, semantic=semantic, expected_version=1)
        content = AIProposal.objects.get(id=r.json()["proposal_id"]).content
        assert content["suggested_criteria"] == []
        assert content["questions"][0]["edge_id"] == "e1"
        assert content["uncertainty"]["level"] == "high"
        # Accepting records the open question as a note, never as a requirement.
        url = f"{world.base(project)}/diagrams/{diagram['id']}/proposals/{r.json()['proposal_id']}/accept"
        client.post(url, {}, format="json")
        profile = PackageProfile.objects.get(issue=issue)
        assert [c["id"] for c in profile.criteria] == ["C-1"]
        assert profile.scope["diagram_notes"][0]["open_questions"]

    def test_rejected_proposal_changes_nothing(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        semantic = {
            **SEMANTIC,
            "nodes": SEMANTIC["nodes"][:1] + [{**SEMANTIC["nodes"][1], "properties": {"engine": "pg16"}}],
        }
        r = _put(client, world, project, diagram, semantic=semantic, expected_version=1)
        changed = r.json()["semantic_diff"]["nodes"]["changed"][0]
        assert changed["properties"]["engine"]["after"] == "pg16"
        url = f"{world.base(project)}/diagrams/{diagram['id']}/proposals/{r.json()['proposal_id']}/reject"
        assert client.post(url, {}, format="json").status_code == 200
        profile = PackageProfile.objects.get(issue=issue)
        assert profile.criteria == [{"id": "C-1", "text": "Orders are stored"}]
        assert profile.scope == {}

    def test_invalid_edge_rejected(self, world, human_client):
        project, issue, client, diagram = _setup(world, human_client)
        semantic = {**SEMANTIC, "edges": [{"id": "e1", "source": "api", "target": "nope"}]}
        r = _put(client, world, project, diagram, semantic=semantic, expected_version=1)
        assert r.status_code == 422
