# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Activity feed, visit marker and overview (FR-P02..FR-P04, J08, AC29)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.package_flow.models import (
    ConversationParticipant,
    Decision,
    ExecutionApproval,
    PackageProfile,
    PackageRevision,
    PlanningDependency,
    VisitMarker,
)
from plane.package_flow.services.events import emit


def setup(world):
    alice = world.member()
    project = world.project(identifier="ACT", members=[(alice, 15)])
    world.enable(project)
    return project, alice


def ev(world, project, issue, event_type, when=None, **payload):
    return emit(workspace_id=world.workspace.id, project_id=project.id, issue_id=issue.id if issue else None,
                event_type=event_type, aggregate_type="issue", aggregate_id=issue.id if issue else project.id,
                actor_kind="system", actor_id="ci", payload=payload, occurred_at=when,
                summary=payload.pop("summary", event_type))[0]


def approve(world, issue, user):
    rev = PackageRevision.objects.create(issue=issue, number=1, title=issue.name, content_hash="h")
    now = timezone.now()
    return ExecutionApproval.objects.create(
        issue=issue, revision=rev, revision_hash="h", approved_by=user, approved_at=now,
        expires_at=now + timedelta(days=1), policy_version="1", repository_scope=[], allowed_actions=[], limits={},
    )


@pytest.mark.unit
class TestActivity:
    def test_fr_p03_ten_pipeline_events_one_entry(self, world, human_client):
        project, alice = setup(world)
        issue = world.issue(project, name="Build pipeline")
        for i in range(10):
            ev(world, project, issue, "ci.check.observed", status="success" if i < 8 else "failure")
        client = human_client(alice)
        data = client.get(f"{world.base(project)}/activity/").json()
        group = next(g for g in data["groups"] if g["issue_id"] == str(issue.id))
        entries = [e for d in group["days"] for e in d["entries"]]
        summaries = [e for e in entries if e["kind"] == "summary"]
        assert len(summaries) == 1 and summaries[0]["count"] == 10
        assert "8 success" in summaries[0]["summary"] and "2 failure" in summaries[0]["summary"]
        assert not [e for e in entries if e.get("event_type") == "ci.check.observed" and e["kind"] == "event"]
        # Raw events remain individually retrievable.
        raw = client.get(f"{world.base(project)}/activity/?raw=1").json()
        raw_entries = [e for g in raw["groups"] for d in g["days"] for e in d["entries"]
                       if e.get("event_type") == "ci.check.observed"]
        assert len(raw_entries) == 10
        by_ids = client.get(f"{world.base(project)}/activity/?ids={','.join(summaries[0]['raw_ids'])}").json()
        assert len(by_ids["raw"]) == 10

    def test_ac29_since_last_visit_grouped(self, world, human_client):
        project, alice = setup(world)
        a = world.issue(project, name="Package A")
        b = world.issue(project, name="Package B")
        now = timezone.now()
        VisitMarker.objects.create(workspace=world.workspace, project=project, member=alice,
                                   last_visited_at=now - timedelta(days=3))
        ev(world, project, a, "native.state.observed", when=now - timedelta(days=4), summary="old change")
        ev(world, project, a, "run.finished", when=now - timedelta(days=2), summary="Run finished",
           reason="all checks passed")
        for i in range(3):
            ev(world, project, b, "ci.check.observed", when=now - timedelta(days=1, minutes=i), status="success")
        Decision.objects.create(workspace=world.workspace, project=project, issue=b, title="Which DB?",
                                text="Postgres or MySQL?", kind="open_question", status="proposed")
        client = human_client(alice)
        conv = client.post(f"{world.ws_base()}/conversations/", {"kind": "project", "project_id": str(project.id)},
                           format="json").json()
        client.post(f"{world.ws_base()}/conversations/{conv['id']}/messages/", {"body": "hi"}, format="json")

        visit = client.post(f"{world.base(project)}/activity/visit").json()
        assert visit["previous_visited_at"] is not None
        data = client.get(f"{world.base(project)}/activity/?since=last_visit").json()
        groups = {g["issue_id"]: g for g in data["groups"]}
        assert {str(a.id), str(b.id)} <= set(groups)
        a_entries = [e for d in groups[str(a.id)]["days"] for e in d["entries"]]
        assert [e["summary"] for e in a_entries] == ["Run finished"]  # the 4-day-old change is excluded
        assert a_entries[0]["reason"] == "all checks passed"
        b_entries = [e for d in groups[str(b.id)]["days"] for e in d["entries"]]
        assert b_entries[0]["kind"] == "summary" and b_entries[0]["count"] == 3
        assert [d["title"] for d in data["open_decisions"]] == ["Which DB?"]
        # Viewing activity does not mark messages as read (J08).
        assert not ConversationParticipant.objects.filter(member=alice, last_read_at__isnull=False).exists()

    def test_fr_p04_blocked_package_not_immediately_executable(self, world, human_client):
        project, alice = setup(world)
        pred = world.issue(project, name="Schema migration")
        blocked = world.issue(project, name="Use new schema")
        free = world.issue(project, name="Docs")
        for i in (pred, blocked, free):
            PackageProfile.objects.create(issue=i)
        blocked.priority = "urgent"
        blocked.save()
        free.priority = "low"
        free.save()
        approve(world, blocked, alice)
        approve(world, free, alice)
        PlanningDependency.objects.create(
            workspace=world.workspace, project=project, predecessor_type="issue", predecessor_id=pred.id,
            predecessor_project=project, successor_type="issue", successor_id=blocked.id, successor_project=project,
            strength="hard", confirmation="confirmed",
        )
        data = human_client(alice).get(f"{world.base(project)}/overview").json()
        nw = {w["issue_id"]: w for w in data["next_work"]}
        assert nw[str(blocked.id)]["immediately_executable"] is False
        assert nw[str(blocked.id)]["blocked"] is True
        assert any("Schema migration" in r for r in nw[str(blocked.id)]["reasons"])
        assert nw[str(free.id)]["immediately_executable"] is True
        # Blocked urgent work is not ranked above executable work; priority stays native.
        assert data["next_work"][0]["issue_id"] == str(free.id)
        assert data["priority_source"] == "native"
        blocked.refresh_from_db()
        assert blocked.priority == "urgent"
        assert set(data["packages"]) >= {"active", "ready", "review", "shipped"}
