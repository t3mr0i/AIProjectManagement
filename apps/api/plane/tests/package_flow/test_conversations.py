# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Conversations: project chat, package threads, DMs, @AI (FR-C01, FR-C02, PRD §5.2, J08, AC12, AC14, PF03, PF09)."""

import re
import uuid

import pytest
from rest_framework.test import APIClient

from plane.db.models import ProjectMember
from plane.package_flow.models import Conversation, ConversationParticipant, Message, NotificationItem


def setup_project(world, n_members=2):
    members = [world.member() for _ in range(n_members)]
    project = world.project(identifier="COL", members=[(m, 15) for m in members])
    world.enable(project)
    return project, members


def channel(world, client, project):
    r = client.post(f"{world.ws_base()}/conversations/", {"kind": "project", "project_id": str(project.id)},
                    format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def dm(world, client, other):
    r = client.post(f"{world.ws_base()}/conversations/", {"kind": "direct", "participant_ids": [str(other.id)]},
                    format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def post(world, client, conv_id, body, **extra):
    r = client.post(f"{world.ws_base()}/conversations/{conv_id}/messages/", {"body": body, **extra}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.unit
class TestConversations:
    def test_pf03_same_native_identities(self, world, human_client):
        """FR-C01: the package thread is reachable from package and chat as one conversation."""
        project, (alice, _) = setup_project(world)
        issue = world.issue(project, name="Export reports")
        client = human_client(alice)
        r1 = client.post(f"{world.ws_base()}/conversations/",
                         {"kind": "package", "project_id": str(project.id), "issue_id": str(issue.id)}, format="json")
        assert r1.status_code == 201, r1.content
        # Reachable from the package without creating a second conversation (FR-C01).
        r2 = client.get(f"{world.base(project)}/work-items/{issue.id}/thread")
        assert r2.status_code == 200, r2.content
        assert r1.json()["id"] == r2.json()["id"]
        r3 = client.post(f"{world.ws_base()}/conversations/",
                         {"kind": "package", "project_id": str(project.id), "issue_id": str(issue.id)}, format="json")
        assert r3.status_code == 200 and r3.json()["id"] == r1.json()["id"]
        assert Conversation.objects.filter(issue=issue, kind="package").count() == 1
        conv = Conversation.objects.get(id=r1.json()["id"])
        assert conv.workspace_id == world.workspace.id
        assert conv.project_id == project.id and conv.issue_id == issue.id
        msg = post(world, client, conv.id, "hello")
        assert msg["author_id"] == str(alice.id)

    def test_admin_cannot_read_dm(self, world, human_client):
        project, (alice, bob) = setup_project(world)
        conv = dm(world, human_client(alice), bob)
        post(world, human_client(alice), conv["id"], "private salary topic")
        admin = human_client(world.owner)  # workspace admin + project admin, not a participant
        assert admin.get(f"{world.ws_base()}/conversations/{conv['id']}/").status_code == 404
        assert admin.get(f"{world.ws_base()}/conversations/{conv['id']}/messages/").status_code == 404
        listed = admin.get(f"{world.ws_base()}/conversations/").json()
        assert conv["id"] not in [c["id"] for c in listed]
        assert admin.get(f"{world.ws_base()}/search/?q=salary").json()["results"] == []
        # The participant can read it.
        assert human_client(bob).get(f"{world.ws_base()}/conversations/{conv['id']}/messages/").status_code == 200

    def test_dm_is_deduplicated_and_agents_cannot_read(self, world, human_client, runner_client):
        _, (alice, bob) = setup_project(world)
        c1 = dm(world, human_client(alice), bob)
        c2 = dm(world, human_client(bob), alice)
        assert c1["id"] == c2["id"]
        _, token = world.runner(alice)
        assert runner_client(token).get(f"{world.ws_base()}/conversations/{c1['id']}/").status_code == 404

    def test_mention_notifies_and_reading_does_not_mark_read(self, world, human_client):
        project, (alice, bob) = setup_project(world)
        conv = channel(world, human_client(alice), project)
        post(world, human_client(alice), conv["id"], f"@{bob.display_name} please review")
        note = NotificationItem.objects.get(recipient=bob)
        assert note.category == "mention" and note.delivery == "immediate"
        bob_client = human_client(bob)
        bob_client.get(f"{world.ws_base()}/conversations/{conv['id']}/messages/")
        detail = bob_client.get(f"{world.ws_base()}/conversations/{conv['id']}/").json()
        # Reading does not mark read (J08).
        assert detail["unread_count"] == 1 and detail["last_read_at"] is None
        r = bob_client.post(f"{world.ws_base()}/conversations/{conv['id']}/read")
        assert r.status_code == 200
        assert bob_client.get(f"{world.ws_base()}/conversations/{conv['id']}/").json()["unread_count"] == 0

    def test_edit_keeps_versions(self, world, human_client):
        project, (alice, bob) = setup_project(world)
        conv = channel(world, human_client(alice), project)
        msg = post(world, human_client(alice), conv["id"], "first")
        url = f"{world.ws_base()}/conversations/{conv['id']}/messages/{msg['id']}/"
        assert human_client(bob).patch(url, {"body": "hijack"}, format="json").status_code == 403
        r = human_client(alice).patch(url, {"body": "second"}, format="json")
        assert r.status_code == 200 and r.json()["version"] == 2
        versions = human_client(alice).get(url + "versions/").json()
        assert [v["body"] for v in versions] == ["first", "second"]

    def test_ai_answer_shows_context(self, world, human_client):
        project, (alice, _) = setup_project(world)
        issue = world.issue(project, name="Monthly export")
        client = human_client(alice)
        thread = client.get(f"{world.base(project)}/work-items/{issue.id}/thread").json()
        post(world, client, thread["id"], "The export should run monthly for finance.")
        r = post(world, client, thread["id"], "@AI when should the export run?")
        ai = r["ai_answer"]
        assert ai["author_kind"] == "ai" and ai["parent_id"] == r["id"]
        ctx = ai["ai_context"]
        assert ctx["status"] == "ok"
        used = {(s["type"], s["id"]) for s in ctx["sources_used"]}
        assert ("issue", str(issue.id)) in used
        assert all(s["status"] in ("observed", "confirmed", "inferred", "proposed") for s in ctx["statements"])
        assert any(s["status"] == "observed" and s["sources"] for s in ctx["statements"])

    def test_ac12_private_dm_not_published_to_project(self, world, human_client):
        project, (alice, bob, carol) = setup_project(world, n_members=3)
        private = dm(world, human_client(alice), bob)
        secret = post(world, human_client(alice), private["id"], "Confidential: vendor price is 42k")
        conv = channel(world, human_client(alice), project)
        r = post(world, human_client(alice), conv["id"], "@AI summarize the vendor price",
                 selection=[{"type": "message", "id": secret["id"]}])
        ctx = r["ai_answer"]["ai_context"]
        blocked = {b["ref"]["id"]: b["reason"] for b in ctx["blocked"]}
        assert blocked.get(secret["id"]) == "private_source"
        assert secret["id"] not in [s["id"] for s in ctx["sources_used"]]
        assert "42k" not in r["ai_answer"]["body"]
        # Carol (project member, not in the DM) sees the channel but not the DM content.
        msgs = human_client(carol).get(f"{world.ws_base()}/conversations/{conv['id']}/messages/").json()
        assert all("42k" not in m["body"] for m in msgs)
        # Within the DM itself the audience matches -> allowed.
        r2 = post(world, human_client(alice), private["id"], "@AI what is the vendor price?")
        assert secret["id"] in [s["id"] for s in r2["ai_answer"]["ai_context"]["sources_used"]]

    def test_ac14_revoked_access_hides_search_and_ai(self, world, human_client):
        project, (alice, bob) = setup_project(world)
        issue = world.issue(project, name="Zephyr migration")
        conv = channel(world, human_client(alice), project)
        post(world, human_client(alice), conv["id"], "zephyr rollout starts monday")
        bob_client = human_client(bob)
        assert bob_client.get(f"{world.ws_base()}/search/?q=zephyr").json()["results"]
        other = world.project(identifier="OTH", members=[(bob, 15), (alice, 15)])
        world.enable(other)
        other_conv = channel(world, bob_client, other)

        ProjectMember.objects.filter(project=project, member=bob).update(is_active=False)

        assert bob_client.get(f"{world.ws_base()}/search/?q=zephyr").json()["results"] == []
        assert bob_client.get(f"{world.ws_base()}/conversations/{conv['id']}/messages/").status_code == 404
        assert conv["id"] not in [c["id"] for c in bob_client.get(f"{world.ws_base()}/conversations/").json()]
        r = post(world, bob_client, other_conv["id"], "@AI tell me about zephyr",
                 selection=[{"type": "issue", "id": str(issue.id)}])
        ctx = r["ai_answer"]["ai_context"]
        assert {"ref": {"type": "issue", "id": str(issue.id)}, "reason": "unavailable"} in ctx["blocked"]
        assert "Zephyr" not in r["ai_answer"]["body"]
        preview = bob_client.post(f"{world.ws_base()}/ai/context-preview",
                                  {"selection": [{"type": "issue", "id": str(issue.id)}]}, format="json").json()
        assert preview["allowed"] == [] and preview["visible"][0]["title"] is None

    def test_pf09_private_content_not_in_public_surfaces(self, world, human_client):
        project, (alice, bob, carol) = setup_project(world, n_members=3)
        private = dm(world, human_client(alice), bob)
        post(world, human_client(alice), private["id"], "internal codename bluefalcon")
        # Project member outside the DM gets nothing — no title, no count.
        r = human_client(carol).get(f"{world.ws_base()}/search/?q=bluefalcon")
        assert r.json() == {"results": []}
        assert human_client(bob).get(f"{world.ws_base()}/search/?q=bluefalcon").json()["results"]

        # No package-flow URL is reachable anonymously (public Plane surfaces expose nothing).
        from plane.package_flow.urls import urlpatterns

        anon = APIClient()
        for pattern in urlpatterns:
            route = str(pattern.pattern)
            url = "/api/" + re.sub(r"<str:[^>]+>", world.workspace.slug, route)
            url = re.sub(r"<uuid:project_id>", str(project.id), url)
            url = re.sub(r"<uuid:[^>]+>", str(uuid.uuid4()), url)
            url = re.sub(r"<int:[^>]+>", "1", url)
            url = re.sub(r"<(path|slug):[^>]+>", "x", url)
            status = anon.get(url).status_code
            assert status >= 400, (url, status)
            if "conversations" in route or "search" in route or "decisions" in route:
                assert status in (401, 403), (url, status)
        assert not Message.objects.filter(body__contains="bluefalcon").exclude(
            conversation__kind="direct"
        ).exists()
        assert ConversationParticipant.objects.filter(conversation_id=private["id"]).count() == 2


@pytest.mark.unit
def test_pf09_public_deploy_board_has_no_package_flow_data(world, human_client):
    """Native public (space) endpoints of a published project expose no extension data (FR-B09)."""
    from plane.db.models import DeployBoard
    from plane.package_flow.models import Decision, PackageProfile

    project, (alice, bob) = setup_project(world)
    issue = world.issue(project, name="Public item")
    PackageProfile.objects.create(issue=issue, outcome="profile-marker-7781", intent="intent-marker-7781")
    Decision.objects.create(workspace=world.workspace, project=project, issue=issue, title="decision-marker-7781",
                            text="decision-marker-7781", status="confirmed", confirmed_by=alice)
    thread = human_client(alice).get(f"{world.base(project)}/work-items/{issue.id}/thread").json()
    post(world, human_client(alice), thread["id"], "message-marker-7781")
    private = dm(world, human_client(alice), bob)
    post(world, human_client(alice), private["id"], "dm-marker-7781")
    board = DeployBoard.objects.create(workspace=world.workspace, project=project, entity_name="project",
                                       entity_identifier=project.id)

    anon = APIClient()
    urls = [
        f"/api/public/anchor/{board.anchor}/issues/",
        f"/api/public/anchor/{board.anchor}/issues/{issue.id}/",
        f"/api/public/anchor/{board.anchor}/meta/",
        f"/api/public/anchor/{board.anchor}/settings/",
    ]
    seen_ok = 0
    for url in urls:
        r = anon.get(url)
        if r.status_code == 200:
            seen_ok += 1
        assert "7781" not in r.content.decode(), url
        assert "package_profile" not in r.content.decode() and "pf_" not in r.content.decode()
    assert seen_ok >= 1  # the public surface itself works
    assert "Public item" in anon.get(urls[0]).content.decode()  # native data is published, extension data is not
