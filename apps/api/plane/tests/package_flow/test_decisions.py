# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Decisions from chat (FR-C03, FR-C04, J06, AC11, AC12, AC13)."""

import pytest

from plane.package_flow.models import Capability, Decision, DomainEvent, SearchDocument
from plane.package_flow.services.decisions import TOMBSTONE


def setup(world, n_members=2):
    members = [world.member() for _ in range(n_members)]
    project = world.project(identifier="DEC", members=[(m, 15) for m in members])
    world.enable(project)
    world.grant(members[0], Capability.DECISION_PUBLISH, project)
    return project, members


def conversation(world, client, **body):
    r = client.post(f"{world.ws_base()}/conversations/", body, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def post(world, client, conv_id, body):
    r = client.post(f"{world.ws_base()}/conversations/{conv_id}/messages/", {"body": body}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.unit
class TestDecisions:
    def test_ac11_decision_published_once_on_redelivery(self, world, human_client):
        project, (alice, _) = setup(world)
        issue = world.issue(project, name="Export")
        client = human_client(alice)
        thread = client.get(f"{world.base(project)}/work-items/{issue.id}/thread").json()
        msg = post(world, client, thread["id"], "We use CSV as export format.")
        preview = client.post(
            f"{world.base(project)}/decisions/preview",
            {"conversation_id": thread["id"], "message_ids": [msg["id"]], "instruction": "Export format is CSV"},
            format="json",
        ).json()
        assert preview["type"] == "preview" and preview["issue_id"] == str(issue.id)
        assert Decision.objects.count() == 0  # a preview books nothing
        body = {"preview_id": preview["preview_id"], "idempotency_key": "cmd-123"}
        r1 = client.post(f"{world.base(project)}/decisions", body, format="json")
        r2 = client.post(f"{world.base(project)}/decisions", body, format="json")
        assert r1.status_code == 201, r1.content
        assert r2.status_code == 200 and r2["Idempotent-Replay"] == "true"
        assert r1.json()["id"] == r2.json()["id"]
        assert Decision.objects.filter(project=project).count() == 1
        d = Decision.objects.get()
        assert d.confirmed_by_id == alice.id and d.issue_id == issue.id
        assert d.source_snapshot[0]["message_id"] == msg["id"] and d.source_snapshot[0]["version"] == 1
        assert DomainEvent.objects.filter(event_type="decision.published", aggregate_id=d.id).count() == 1

    def test_confirm_requires_human_and_capability(self, world, human_client, runner_client):
        project, (alice, bob) = setup(world)
        body = {"title": "T", "text": "Use CSV", "idempotency_key": "k1"}
        r = human_client(bob).post(f"{world.base(project)}/decisions", body, format="json")
        assert r.status_code == 403
        _, token = world.runner(alice)
        r = runner_client(token).post(f"{world.base(project)}/decisions", body, format="json")
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        assert not Decision.objects.exists()

    def test_preview_asks_when_ambiguous(self, world, human_client):
        project, (alice, _) = setup(world)
        a = world.issue(project, name="A")
        b = world.issue(project, name="B")
        client = human_client(alice)
        conv = conversation(world, client, kind="project", project_id=str(project.id))
        msg = post(world, client, conv["id"], f"DEC-{a.sequence_id} and DEC-{b.sequence_id} should use CSV")
        url = f"{world.base(project)}/decisions/preview"
        r = client.post(url, {"conversation_id": conv["id"], "message_ids": [msg["id"]]}, format="json").json()
        assert r["type"] == "clarification" and r["reason"] == "ambiguous_target"
        assert {o["issue_id"] for o in r["options"]} == {str(a.id), str(b.id)}
        r = client.post(url, {"conversation_id": conv["id"], "message_ids": []}, format="json").json()
        assert r["type"] == "clarification" and r["reason"] == "no_selection"

    def test_ac13_edited_message_keeps_decision(self, world, human_client):
        project, (alice, _) = setup(world)
        client = human_client(alice)
        conv = conversation(world, client, kind="project", project_id=str(project.id))
        msg = post(world, client, conv["id"], "Deploy on Tuesdays.")
        r = client.post(
            f"{world.base(project)}/decisions",
            {"title": "Deploy day", "text": "Deploy on Tuesdays.", "source_message_ids": [msg["id"]],
             "idempotency_key": "d-1"},
            format="json",
        )
        assert r.status_code == 201, r.content
        listed = client.get(f"{world.base(project)}/decisions/").json()
        assert listed[0]["source_changed_since_decision"] is False
        r = client.patch(f"{world.ws_base()}/conversations/{conv['id']}/messages/{msg['id']}/",
                         {"body": "Deploy on Fridays."}, format="json")
        assert r.status_code == 200
        listed = client.get(f"{world.base(project)}/decisions/").json()
        assert listed[0]["text"] == "Deploy on Tuesdays."
        assert listed[0]["source_snapshot"][0]["body"] == "Deploy on Tuesdays."
        assert listed[0]["source_snapshot"][0]["version"] == 1
        assert listed[0]["source_changed_since_decision"] is True
        versions = client.get(
            f"{world.ws_base()}/conversations/{conv['id']}/messages/{msg['id']}/versions/"
        ).json()
        assert [v["version"] for v in versions] == [1, 2]

    def test_ac12_private_dm_decision_requires_reviewed_summary(self, world, human_client):
        project, (alice, bob, _carol) = setup(world, n_members=3)
        client = human_client(alice)
        dm = conversation(world, client, kind="direct", participant_ids=[str(bob.id)])
        msg = post(world, client, dm["id"], "Between us: supplier X is unreliable, pick Y.")
        url = f"{world.base(project)}/decisions"
        body = {"title": "Supplier", "text": "Pick Y", "source_message_ids": [msg["id"]], "idempotency_key": "p1"}
        r = client.post(url, body, format="json")
        assert r.status_code == 403 and r.json()["code"] == "PRIVATE_SOURCE"
        assert not Decision.objects.exists()
        body.update({"publish_reviewed_summary": True, "summary": "We choose supplier Y.", "idempotency_key": "p2"})
        r = client.post(url, body, format="json")
        assert r.status_code == 201, r.content
        d = Decision.objects.get()
        assert d.text == "We choose supplier Y."
        dumped = str(d.source_snapshot)
        assert "unreliable" not in dumped and msg["id"] not in dumped
        assert d.source_conversation_id is None

    def test_deleted_source_is_tombstoned(self, world, human_client):
        project, (alice, bob) = setup(world)
        client = human_client(alice)
        conv = conversation(world, client, kind="project", project_id=str(project.id))
        msg = post(world, client, conv["id"], "Use the quokka library.")
        r = client.post(f"{world.base(project)}/decisions",
                        {"title": "Library", "text": "Use quokka.", "source_message_ids": [msg["id"]]},
                        format="json")
        assert r.status_code == 201
        r = client.delete(f"{world.ws_base()}/conversations/{conv['id']}/messages/{msg['id']}/")
        assert r.status_code == 204
        d = Decision.objects.get()
        assert d.text == "Use quokka."
        assert d.source_snapshot[0]["body"] == TOMBSTONE and d.source_snapshot[0]["deleted"] is True
        assert not SearchDocument.objects.filter(object_type="message", object_id=msg["id"]).exists()
        listed = client.get(f"{world.base(project)}/decisions/").json()
        assert listed[0]["source_deleted"] is True
