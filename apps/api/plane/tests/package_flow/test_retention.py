# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Retention per category with cascading deletion (PRD §15.3, FR-I08, FR-C04)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.package_flow.models import AIProposal, Capability, Decision, Message, SearchDocument
from plane.package_flow.services.decisions import TOMBSTONE


@pytest.mark.unit
class TestRetention:
    def test_requires_workspace_admin(self, world, human_client):
        member = world.member()
        r = human_client(member).get(f"{world.ws_base()}/retention/")
        assert r.status_code == 403
        r = human_client(world.owner).get(f"{world.ws_base()}/retention/")
        assert r.status_code == 200
        assert {p["category"] for p in r.json()["policies"]} >= {"messages", "ai_outputs", "raw_events", "run_logs",
                                                                 "exports"}
        r = human_client(world.owner).put(f"{world.ws_base()}/retention/",
                                          {"policies": [{"category": "bogus", "retain_days": 3}]}, format="json")
        assert r.status_code == 422

    def test_message_retention_cascades(self, world, human_client):

        """FR-I08: retention deletes messages together with index rows and source excerpts."""
        alice = world.member()
        project = world.project(identifier="RET", members=[(alice, 15)])
        world.enable(project)
        world.grant(alice, Capability.DECISION_PUBLISH, project)
        client = human_client(alice)
        conv = client.post(f"{world.ws_base()}/conversations/", {"kind": "project", "project_id": str(project.id)},
                           format="json").json()
        old = client.post(f"{world.ws_base()}/conversations/{conv['id']}/messages/",
                          {"body": "confidential walrus figures"}, format="json").json()
        fresh = client.post(f"{world.ws_base()}/conversations/{conv['id']}/messages/",
                            {"body": "fresh walrus note"}, format="json").json()
        r = client.post(f"{world.base(project)}/decisions",
                        {"title": "Walrus", "text": "Adopt walrus plan.", "source_message_ids": [old["id"]]},
                        format="json")
        assert r.status_code == 201
        Message.objects.filter(id=old["id"]).update(created_at=timezone.now() - timedelta(days=40))
        AIProposal.objects.create(workspace=world.workspace, project=project, kind="answer", content={})
        AIProposal.objects.filter().update(created_at=timezone.now() - timedelta(days=100))

        admin = human_client(world.owner)
        r = admin.put(f"{world.ws_base()}/retention/", {"policies": [
            {"category": "messages", "retain_days": 30}, {"category": "ai_outputs", "retain_days": 90}]},
            format="json")
        assert r.status_code == 200, r.content
        result = admin.post(f"{world.ws_base()}/retention/apply").json()["result"]
        assert result["messages"]["deleted"] == 1 and result["ai_outputs"]["deleted"] >= 1

        assert not Message.all_objects.filter(id=old["id"]).exists()
        assert Message.objects.filter(id=fresh["id"]).exists()
        assert not SearchDocument.all_objects.filter(object_id=old["id"]).exists()
        d = Decision.objects.get()
        assert d.text == "Adopt walrus plan."
        assert d.source_snapshot[0]["body"] == TOMBSTONE
        assert "confidential" not in str(d.source_snapshot)
        results = client.get(f"{world.ws_base()}/search/?q=walrus").json()["results"]
        assert all("confidential" not in (r["snippet"] or "") for r in results)
        assert not AIProposal.objects.filter(kind="answer").exists()
