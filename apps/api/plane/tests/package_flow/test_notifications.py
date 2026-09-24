# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Targeted vs bundled notifications (FR-C07)."""

import pytest

from plane.db.models import IssueAssignee, ProjectMember
from plane.package_flow.models import NotificationItem
from plane.package_flow.services.events import emit


def setup(world):
    alice = world.member()
    project = world.project(identifier="NTF", members=[(alice, 15)])
    world.enable(project)
    issue = world.issue(project, name="Build me")
    IssueAssignee.objects.create(issue=issue, assignee=alice, project=project, workspace=world.workspace)
    return project, alice, issue


def ev(world, project, issue, event_type, **payload):
    return emit(workspace_id=world.workspace.id, project_id=project.id, issue_id=issue.id, event_type=event_type,
                aggregate_type="issue", aggregate_id=issue.id, actor_kind="system", actor_id="ci", payload=payload,
                summary=f"{event_type} {payload}")


@pytest.mark.unit
class TestNotifications:
    def test_fr_c07_builds_bundled(self, world, human_client):
        project, alice, issue = setup(world)
        for _ in range(10):
            ev(world, project, issue, "ci.check.observed", status="success")
        items = NotificationItem.objects.filter(recipient=alice)
        assert items.count() == 1
        digest = items.get()
        assert digest.delivery == "digest" and digest.category == "technical" and digest.count == 10
        ev(world, project, issue, "run.finished", status="failed")
        ev(world, project, issue, "question.raised")
        data = human_client(alice).get(f"{world.ws_base()}/notifications/").json()
        assert len(data["bundled"]) == 1 and data["bundled"][0]["count"] == 10
        assert sorted(n["category"] for n in data["targeted"]) == ["blocked", "decision_needed"]
        # After reading the digest, a new digest starts.
        human_client(alice).post(f"{world.ws_base()}/notifications/{digest.id}/read")
        ev(world, project, issue, "ci.check.observed", status="success")
        open_digest = NotificationItem.objects.filter(recipient=alice, delivery="digest", read_at__isnull=True).get()
        assert open_digest.count == 1

    def test_review_request_is_targeted(self, world):
        project, alice, issue = setup(world)
        bob = world.member()
        world.add_project_member(project, bob)
        ev(world, project, issue, "git.mr.observed", review_requested_ids=[str(bob.id)])
        item = NotificationItem.objects.get(recipient=bob)
        assert item.category == "review_request" and item.delivery == "immediate"

    def test_revoked_member_gets_nothing(self, world, human_client):
        project, alice, issue = setup(world)
        ev(world, project, issue, "ci.check.observed", status="success")
        ProjectMember.objects.filter(project=project, member=alice).update(is_active=False)
        data = human_client(alice).get(f"{world.ws_base()}/notifications/").json()
        assert data == {"targeted": [], "bundled": []}
        ev(world, project, issue, "question.raised")
        assert NotificationItem.objects.filter(recipient=alice).count() == 1
