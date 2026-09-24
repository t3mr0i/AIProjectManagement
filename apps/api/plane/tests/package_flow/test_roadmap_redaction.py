# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Graph redaction: confidential projects never leak through roadmap/dependency graphs (AC25, PRD §15.2)."""

import json

import pytest

from plane.package_flow.models import Capability


def _dep(client, world, pred, succ, **extra):
    r = client.post(
        f"{world.ws_base()}/dependencies/", {"predecessor": pred, "successor": succ, **extra}, format="json"
    )
    assert r.status_code == 201, r.content
    return r.json()


def _setup(world, human_client):
    viewer = world.member(role=15)
    visible = world.project(name="Visible", members=[(viewer, 15)])
    secret = world.project(name="Confidential Merger", identifier="SECRT")
    for p in (visible, secret):
        world.enable(p)
        world.grant(world.owner, Capability.PROJECT_PLAN, p)
    owner = human_client(world.owner)
    ms = owner.post(
        f"{world.base(secret)}/milestones/",
        {"name": "Secret Milestone Zeta", "target_at": "2026-12-01T00:00:00Z", "date_confidence": "confirmed"},
        format="json",
    ).json()
    mv = owner.post(
        f"{world.base(visible)}/milestones/",
        {"name": "Visible Launch", "target_at": "2026-11-01T00:00:00Z", "date_confidence": "confirmed"},
        format="json",
    ).json()
    hidden_issue = world.issue(secret, name="Hidden Acquisition Task")
    visible_issue = world.issue(visible, name="Visible Task")
    hidden_issue2 = world.issue(secret, name="Hidden Downstream Task")
    return viewer, visible, secret, ms, mv, hidden_issue, visible_issue, hidden_issue2, owner


@pytest.mark.unit
class TestRedaction:
    def test_ac25_confidential_project_not_in_graph(self, world, human_client):
        viewer, visible, secret, ms, mv, hidden_issue, visible_issue, hidden_issue2, owner = _setup(world, human_client)
        # hidden -> visible without anonymous-blocker policy: omitted entirely.
        _dep(
            owner, world, {"type": "issue", "id": str(hidden_issue.id)}, {"type": "issue", "id": str(visible_issue.id)}
        )
        # visible -> hidden (hidden successor): omitted even with policy.
        _dep(
            owner,
            world,
            {"type": "issue", "id": str(visible_issue.id)},
            {"type": "issue", "id": str(hidden_issue2.id)},
            allow_anonymous_blocker=True,
        )
        client = human_client(viewer)
        for url in (f"{world.ws_base()}/roadmap/", f"{world.ws_base()}/dependencies/"):
            r = client.get(url)
            assert r.status_code == 200, r.content
            dumped = json.dumps(r.json())
            for secret_value in (
                secret.name,
                str(secret.id),
                "SECRT",
                "Hidden Acquisition Task",
                str(hidden_issue.id),
                "Hidden Downstream Task",
                str(hidden_issue2.id),
                "Secret Milestone Zeta",
                ms["id"],
            ):
                assert secret_value not in dumped, (url, secret_value)
            body = r.json()
            edges = body["edges"] if "edges" in body else body["dependencies"]
            assert edges == []
        # Explicit filter on the hidden project yields nothing.
        r = client.get(f"{world.ws_base()}/roadmap/?project_ids={secret.id}")
        assert r.json()["projects"] == [] and r.json()["milestones"] == []

        # The owner (member of both) sees the full graph.
        full = owner.get(f"{world.ws_base()}/roadmap/").json()
        assert len(full["dependencies"]) == 2

    def test_anonymous_blocker_when_policy_allows(self, world, human_client):
        viewer, visible, secret, ms, mv, *_rest, owner = _setup(world, human_client)
        _dep(
            owner,
            world,
            {"type": "milestone", "id": ms["id"]},
            {"type": "milestone", "id": mv["id"]},
            allow_anonymous_blocker=True,
        )
        r = human_client(viewer).get(f"{world.ws_base()}/roadmap/")
        body = r.json()
        dumped = json.dumps(body)
        assert "Secret Milestone Zeta" not in dumped and ms["id"] not in dumped and str(secret.id) not in dumped
        assert len(body["dependencies"]) == 1
        edge = body["dependencies"][0]
        blocker = next(n for n in body["nodes"] if n["key"] == edge["source_key"])
        assert blocker == {"key": blocker["key"], "type": "external_blocker", "label": "External prerequisite open"}
        # The automatic risk (hidden predecessor is late) shows only the anonymous blocker.
        risks = human_client(viewer).get(f"{world.base(visible)}/risks/").json()
        auto = [x for x in risks if x["origin"] == "automatic"]
        assert len(auto) == 1
        assert auto[0]["cause"]["predecessor"] == {"type": "external_blocker", "label": "External prerequisite open"}
        assert ms["id"] not in json.dumps(risks)

    def test_risk_hidden_without_policy(self, world, human_client):
        viewer, visible, secret, ms, mv, *_rest, owner = _setup(world, human_client)
        _dep(owner, world, {"type": "milestone", "id": ms["id"]}, {"type": "milestone", "id": mv["id"]})
        risks = human_client(viewer).get(f"{world.base(visible)}/risks/").json()
        assert [x for x in risks if x["origin"] == "automatic"] == []
        owner_risks = owner.get(f"{world.base(visible)}/risks/").json()
        assert owner_risks[0]["cause"]["predecessor"]["label"] == "Secret Milestone Zeta"

    def test_viewer_cannot_create_dependency_to_hidden_node(self, world, human_client):
        viewer, visible, secret, ms, mv, hidden_issue, visible_issue, *_rest = _setup(world, human_client)
        world.grant(viewer, Capability.PROJECT_PLAN, visible)
        r = human_client(viewer).post(
            f"{world.ws_base()}/dependencies/",
            {
                "predecessor": {"type": "issue", "id": str(hidden_issue.id)},
                "successor": {"type": "issue", "id": str(visible_issue.id)},
            },
            format="json",
        )
        assert r.status_code == 404

    def test_team_listing_hides_confidential_projects(self, world, human_client):
        viewer, visible, secret, *_rest, owner = _setup(world, human_client)
        r = owner.post(
            f"{world.ws_base()}/teams/",
            {"name": "Mixed", "project_ids": [str(visible.id), str(secret.id)]},
            format="json",
        )
        assert r.status_code == 201, r.content
        teams = human_client(viewer).get(f"{world.ws_base()}/teams/").json()
        assert teams[0]["project_ids"] == [str(visible.id)]
