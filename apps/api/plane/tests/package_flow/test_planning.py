# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Cross-project planning (FR-M01..M06, FR-C06, AC24)."""

import datetime as dt

import pytest

from plane.db.models import Cycle, CycleIssue
from plane.package_flow.models import Capability, Milestone, PackageProfile, PlanningDependency, Risk


def _plan_world(world, n=2):
    projects = []
    for i in range(n):
        project = world.project(name=f"P{i}")
        world.enable(project)
        world.grant(world.owner, Capability.PROJECT_PLAN, project)
        projects.append(project)
    return projects


def _milestone(client, world, project, name, target_at, tz="UTC", **extra):
    r = client.post(
        f"{world.base(project)}/milestones/",
        {"name": name, "target_at": target_at, "timezone": tz, **extra},
        format="json",
    )
    assert r.status_code == 201, r.content
    return r.json()


def _dep(client, world, pred, succ, **extra):
    return client.post(
        f"{world.ws_base()}/dependencies/",
        {"predecessor": pred, "successor": succ, **extra},
        format="json",
    )


@pytest.mark.unit
class TestMilestones:
    def test_fr_c06_timezone_display_keeps_instant(self, world, human_client):
        (project,) = _plan_world(world, 1)
        client = human_client(world.owner)
        m = _milestone(client, world, project, "Beta", "2026-10-01T09:00:00", tz="Europe/Berlin")
        assert m["target_at"] == "2026-10-01T07:00:00Z"
        assert m["target_local"] == "2026-10-01T09:00:00+02:00"
        stored = Milestone.objects.get(id=m["id"]).target_at
        r = client.get(f"{world.base(project)}/milestones/{m['id']}/?tz=America/New_York")
        assert r.json()["target_display"] == "2026-10-01T03:00:00-04:00"
        assert r.json()["target_at"] == "2026-10-01T07:00:00Z"
        assert Milestone.objects.get(id=m["id"]).target_at == stored
        # ICS export uses UTC.
        r = client.get(f"{world.base(project)}/events.ics")
        assert r.status_code == 200
        text = r.content.decode()
        assert "DTSTART:20261001T070000Z" in text and text.startswith("BEGIN:VCALENDAR\r\n")

    def test_invalid_timezone_rejected(self, world, human_client):
        (project,) = _plan_world(world, 1)
        r = human_client(world.owner).post(
            f"{world.base(project)}/milestones/", {"name": "x", "timezone": "Mars/Base"}, format="json"
        )
        assert r.status_code == 422

    def test_plan_capability_required(self, world, human_client):
        project = world.project()
        world.enable(project)
        r = human_client(world.owner).post(f"{world.base(project)}/milestones/", {"name": "x"}, format="json")
        assert r.status_code == 403

    def test_unknown_confidence_no_fake_date(self, world, human_client):
        (project,) = _plan_world(world, 1)
        client = human_client(world.owner)
        m = _milestone(client, world, project, "GA", "2026-12-01T00:00:00Z", date_confidence="unknown")
        r = client.get(f"{world.ws_base()}/roadmap/")
        entry = next(x for x in r.json()["milestones"] if x["id"] == m["id"])
        assert entry["reliable_date"] is False and entry["date_label"] == "No reliable date"

    def test_events_and_ics_escape(self, world, human_client):
        (project,) = _plan_world(world, 1)
        client = human_client(world.owner)
        r = client.post(
            f"{world.base(project)}/events/",
            {"title": "Review; demo, all", "starts_at": "2026-10-02T15:00:00", "timezone": "Europe/Berlin"},
            format="json",
        )
        assert r.status_code == 201, r.content
        assert r.json()["starts_at"] == "2026-10-02T13:00:00Z"
        text = client.get(f"{world.base(project)}/events.ics").content.decode()
        assert "SUMMARY:Review\\; demo\\, all" in text


@pytest.mark.unit
class TestDependencies:
    def test_ac24_hard_cycle_rejected(self, world, human_client):
        p1, p2 = _plan_world(world)
        client = human_client(world.owner)
        a = world.issue(p1, name="Package A")
        b = world.issue(p2, name="Package B")
        r = _dep(client, world, {"type": "issue", "id": str(a.id)}, {"type": "issue", "id": str(b.id)})
        assert r.status_code == 201, r.content
        assert r.json()["blocking"] is True
        r = _dep(client, world, {"type": "issue", "id": str(b.id)}, {"type": "issue", "id": str(a.id)})
        assert r.status_code == 422, r.content
        body = r.json()
        assert body["code"] == "DEPENDENCY_CYCLE"
        assert len(body["detail"]["path"]) == 3
        assert body["detail"]["path"][0] == body["detail"]["path"][-1]
        assert "Package B" in body["detail"]["readable_path"] and "->" in body["detail"]["readable_path"]
        # A soft or suggested reverse link is allowed (never blocks).
        r = _dep(client, world, {"type": "issue", "id": str(b.id)}, {"type": "issue", "id": str(a.id)}, strength="soft")
        assert r.status_code == 201

    def test_transitive_cycle_on_confirm(self, world, human_client):
        (p1,) = _plan_world(world, 1)
        client = human_client(world.owner)
        a, b, c = (world.issue(p1, name=n) for n in "ABC")
        assert (
            _dep(client, world, {"type": "issue", "id": str(a.id)}, {"type": "issue", "id": str(b.id)}).status_code
            == 201
        )
        assert (
            _dep(client, world, {"type": "issue", "id": str(b.id)}, {"type": "issue", "id": str(c.id)}).status_code
            == 201
        )
        r = _dep(
            client,
            world,
            {"type": "issue", "id": str(c.id)},
            {"type": "issue", "id": str(a.id)},
            confirmation="suggested",
        )
        assert r.status_code == 201 and r.json()["style"] == "suggested" and r.json()["blocking"] is False
        r = client.post(f"{world.ws_base()}/dependencies/{r.json()['id']}/confirm", format="json")
        assert r.status_code == 422 and r.json()["code"] == "DEPENDENCY_CYCLE"
        assert len(r.json()["detail"]["path"]) == 4

    def test_agent_dependency_is_suggestion(self, world, human_client, runner_client):
        (p1,) = _plan_world(world, 1)
        _, token = world.runner(world.owner)
        a, b = world.issue(p1), world.issue(p1)
        r = _dep(runner_client(token), world, {"type": "issue", "id": str(a.id)}, {"type": "issue", "id": str(b.id)})
        assert r.status_code == 201, r.content
        assert r.json()["source"] == "ai" and r.json()["confirmation"] == "suggested"
        assert r.json()["blocking"] is False
        # Agents cannot confirm.
        r2 = runner_client(token).post(f"{world.ws_base()}/dependencies/{r.json()['id']}/confirm", format="json")
        assert r2.status_code == 403

    def test_requires_plan_on_both_projects(self, world, human_client):
        p1 = _plan_world(world, 1)[0]
        p2 = world.project()
        world.enable(p2)
        a, b = world.issue(p1), world.issue(p2)
        r = _dep(
            human_client(world.owner), world, {"type": "issue", "id": str(a.id)}, {"type": "issue", "id": str(b.id)}
        )
        assert r.status_code == 403


@pytest.mark.unit
class TestScenariosAndRisks:
    def _chain(self, world, client):
        p1, p2 = _plan_world(world)
        m1 = _milestone(client, world, p1, "API ready", "2026-10-01T00:00:00Z", date_confidence="confirmed")
        m2 = _milestone(client, world, p2, "UI ready", "2026-10-10T00:00:00Z", date_confidence="confirmed")
        m3 = _milestone(client, world, p2, "Launch", "2026-10-20T00:00:00Z", date_confidence="confirmed")
        for pred, succ in ((m1, m2), (m2, m3)):
            r = _dep(client, world, {"type": "milestone", "id": pred["id"]}, {"type": "milestone", "id": succ["id"]})
            assert r.status_code == 201, r.content
        return p1, p2, m1, m2, m3

    def test_fr_m03_scenario_does_not_change_plan(self, world, human_client):
        client = human_client(world.owner)
        p1, p2, m1, m2, m3 = self._chain(world, client)
        r = client.post(
            f"{world.ws_base()}/scenarios/",
            {
                "name": "API slips",
                "changes": [{"type": "milestone", "id": m1["id"], "target_at": "2026-10-15T00:00:00Z"}],
            },
            format="json",
        )
        assert r.status_code == 201, r.content
        sid = r.json()["id"]
        r = client.get(f"{world.ws_base()}/scenarios/{sid}/impact")
        assert r.status_code == 200, r.content
        affected = {a["id"]: a for a in r.json()["affected"]}
        assert affected[m2["id"]]["direct"] is True and affected[m2["id"]]["would_be_late"] is True
        assert affected[m3["id"]]["depth"] == 2 and affected[m3["id"]]["would_be_affected"] is True
        assert affected[m3["id"]]["current_target"] == "2026-10-20T00:00:00Z"
        # Nothing changed.
        assert Milestone.objects.get(id=m1["id"]).target_at == dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        # Apply changes only the explicit milestone.
        r = client.post(f"{world.ws_base()}/scenarios/{sid}/apply", format="json")
        assert r.status_code == 200, r.content
        assert r.json()["successors_changed"] == []
        assert Milestone.objects.get(id=m1["id"]).target_at == dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
        assert Milestone.objects.get(id=m2["id"]).target_at == dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
        assert Milestone.objects.get(id=m3["id"]).target_at == dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc)
        # Second apply is rejected.
        assert client.post(f"{world.ws_base()}/scenarios/{sid}/apply", format="json").status_code == 409

    def test_fr_m06_risk_links_cause(self, world, human_client):
        client = human_client(world.owner)
        p1, p2, m1, m2, m3 = self._chain(world, client)
        assert Risk.objects.filter(origin="automatic", status="open").count() == 0
        r = client.patch(
            f"{world.base(p1)}/milestones/{m1['id']}/", {"target_at": "2026-10-12T00:00:00Z"}, format="json"
        )
        assert r.status_code == 200, r.content
        risks = client.get(f"{world.base(p2)}/risks/").json()
        auto = [x for x in risks if x["origin"] == "automatic" and x["status"] == "open"]
        assert len(auto) == 1
        cause = auto[0]["cause"]
        assert cause["type"] == "late_predecessor"
        assert cause["predecessor"]["id"] == m1["id"]
        assert cause["predecessor"]["label"] == "API ready"
        assert cause["predecessor"]["link"]["project_id"] == str(p1.id)
        assert "UI ready" in auto[0]["title"]
        # Fixing the date resolves the automatic risk.
        client.patch(f"{world.base(p1)}/milestones/{m1['id']}/", {"target_at": "2026-10-02T00:00:00Z"}, format="json")
        assert Risk.objects.filter(origin="automatic", status="open").count() == 0
        # Manual risks are possible too.
        r = client.post(f"{world.base(p2)}/risks/", {"title": "Vendor delay", "severity": "low"}, format="json")
        assert r.status_code == 201 and r.json()["origin"] == "human"


@pytest.mark.unit
class TestRoadmapTeamsCycles:
    def test_fr_m01_two_teams_one_roadmap(self, world, human_client):
        p1, p2 = _plan_world(world)
        client = human_client(world.owner)
        r1 = client.post(f"{world.ws_base()}/teams/", {"name": "Backend", "project_ids": [str(p1.id)]}, format="json")
        r2 = client.post(f"{world.ws_base()}/teams/", {"name": "Frontend", "project_ids": [str(p2.id)]}, format="json")
        assert r1.status_code == 201 and r2.status_code == 201, (r1.content, r2.content)
        issue = world.issue(p1, name="Pkg")
        issue.target_date = dt.date(2026, 11, 1)
        issue.save()
        PackageProfile.objects.create(issue=issue)
        PackageProfile.objects.create(issue=world.issue(p2, name="Undated"))
        _milestone(client, world, p2, "Launch", "2026-11-05T00:00:00Z", date_confidence="confirmed")
        roadmap = client.get(f"{world.ws_base()}/roadmap/").json()
        assert {p["id"] for p in roadmap["projects"]} >= {str(p1.id), str(p2.id)}
        teams = {p["id"]: p["team_ids"] for p in roadmap["projects"]}
        assert teams[str(p1.id)] == [r1.json()["id"]] and teams[str(p2.id)] == [r2.json()["id"]]
        packages = {p["name"]: p for p in roadmap["packages"]}
        assert packages["Pkg"]["target_date"] == "2026-11-01"
        assert packages["Undated"]["target_label"] == "unknown" and packages["Undated"]["target_date"] is None
        filtered = client.get(f"{world.ws_base()}/roadmap/?team_id={r2.json()['id']}").json()
        assert [p["id"] for p in filtered["projects"]] == [str(p2.id)]
        assert [m["name"] for m in filtered["milestones"]] == ["Launch"]

    def test_fr_m05_cycles_are_context_only(self, world, human_client):
        (p1,) = _plan_world(world, 1)
        now = dt.datetime.now(dt.timezone.utc)
        cycle = Cycle.objects.create(
            name="Sprint 1",
            project=p1,
            workspace=world.workspace,
            owned_by=world.owner,
            start_date=now - dt.timedelta(days=3),
            end_date=now + dt.timedelta(days=4),
        )
        issue = world.issue(p1)
        PackageProfile.objects.create(issue=issue)
        CycleIssue.objects.create(cycle=cycle, issue=issue, project=p1, workspace=world.workspace)
        body = human_client(world.owner).get(f"{world.base(p1)}/cycles-context/").json()
        assert body["cycles"][0]["status"] == "current" and body["cycles"][0]["package_count"] == 1
        assert body["story_points_required"] is False
        assert body["delivery_blocked_until_cycle_end"] is False
        roadmap = human_client(world.owner).get(f"{world.ws_base()}/roadmap/").json()
        assert roadmap["cycles"][0]["read_only"] is True

    def test_dependency_types_rendered_differently(self, world, human_client):
        (p1,) = _plan_world(world, 1)
        client = human_client(world.owner)
        a, b, c = (world.issue(p1, name=n) for n in "ABC")
        _dep(client, world, {"type": "issue", "id": str(a.id)}, {"type": "issue", "id": str(b.id)})
        _dep(
            client,
            world,
            {"type": "issue", "id": str(b.id)},
            {"type": "issue", "id": str(c.id)},
            confirmation="suggested",
        )
        edges = client.get(f"{world.ws_base()}/roadmap/").json()["dependencies"]
        styles = sorted((e["style"], e["blocking"]) for e in edges)
        assert styles == [("hard", True), ("suggested", False)]
        assert PlanningDependency.objects.count() == 2
