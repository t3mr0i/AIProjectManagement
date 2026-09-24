# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Structured export (FR-I06) and its retention (FR-I08)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from plane.package_flow.models import (
    ExportJob,
    ExternalLink,
    IntegrationConnection,
    PackageProfile,
    PackageRevision,
)


def setup(world):
    alice, bob = world.member(), world.member()
    project = world.project(identifier="EXP", members=[(alice, 15), (bob, 15)])
    hidden = world.project(identifier="HID", members=[(bob, 15)])
    world.enable(project)
    issue = world.issue(project, name="Export package")
    PackageProfile.objects.create(issue=issue, outcome="CSV export")
    PackageRevision.objects.create(issue=issue, number=1, title=issue.name, content_hash="c" * 64)
    secret = world.issue(hidden, name="Hidden package")
    PackageProfile.objects.create(issue=secret, outcome="top secret outcome")
    conn = IntegrationConnection.objects.create(workspace=world.workspace, provider="jira",
                                                instance_url="https://jira.example.test")
    ExternalLink.objects.create(issue=issue, connection=conn, object_type="issue", external_id="10001",
                                external_key="EXP-1", represents_package=True)
    return project, hidden, alice, bob, issue, conn


def export(world, client, **body):
    r = client.post(f"{world.ws_base()}/exports/", body, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.unit
class TestExports:
    def test_fr_i06_export_keeps_ids_after_disconnect(self, world, human_client):
        project, hidden, alice, bob, issue, conn = setup(world)
        client = human_client(alice)
        first = export(world, client)["bundle"]
        assert [p["workItemId"] for p in first["packages"]] == [str(issue.id)]
        assert first["revisions"][0]["schemaVersion"] == "1.1.0"
        assert first["revisions"][0]["workItemId"] == str(issue.id)
        assert first["externalMappings"][0]["externalKey"] == "EXP-1"
        # ACL: nothing from the hidden project, not even its title.
        assert "top secret" not in str(first) and str(hidden.id) not in str(first)

        # Disconnect the tracker.
        IntegrationConnection.objects.filter(id=conn.id).update(status="disabled")
        ExternalLink.objects.filter(connection=conn).update(sync_state="disconnected")
        second = export(world, client)["bundle"]
        assert [p["workItemId"] for p in second["packages"]] == [p["workItemId"] for p in first["packages"]]
        assert [r["id"] for r in second["revisions"]] == [r["id"] for r in first["revisions"]]
        mapping = second["externalMappings"][0]
        assert mapping["connectionStatus"] == "disabled" and mapping["syncState"] == "disconnected"
        assert mapping["workItemId"] == str(issue.id)

        # Hidden project explicitly requested -> 404, no oracle.
        r = client.post(f"{world.ws_base()}/exports/", {"project_ids": [str(hidden.id)]}, format="json")
        assert r.status_code == 404

    def test_direct_messages_only_on_request_and_for_participants(self, world, human_client):
        project, _hidden, alice, bob, _issue, _conn = setup(world)
        client = human_client(alice)
        dm = client.post(f"{world.ws_base()}/conversations/", {"kind": "direct", "participant_ids": [str(bob.id)]},
                         format="json").json()
        client.post(f"{world.ws_base()}/conversations/{dm['id']}/messages/", {"body": "private kiwi"}, format="json")
        plain = export(world, client, project_ids=[str(project.id)])
        assert "kiwi" not in str(plain["bundle"])
        with_dm = export(world, client, project_ids=[str(project.id)],
                         include=["packages", "sources", "direct_messages"])
        assert "kiwi" in str(with_dm["bundle"]) and with_dm["contains_private"] is True
        # Workspace admin sees the job, but not the requester's private content.
        admin = human_client(world.owner)
        assert with_dm["id"] in [j["id"] for j in admin.get(f"{world.ws_base()}/exports/").json()]
        detail = admin.get(f"{world.ws_base()}/exports/{with_dm['id']}/").json()
        assert detail["content_withheld"] is True and detail["bundle"] is None
        # Other members cannot see it at all.
        assert human_client(bob).get(f"{world.ws_base()}/exports/{with_dm['id']}/").status_code == 404
        assert human_client(alice).get(f"{world.ws_base()}/exports/{with_dm['id']}/").json()["bundle"]

    def test_expired_exports_are_deleted_by_retention(self, world, human_client):
        project, _hidden, alice, _bob, _issue, _conn = setup(world)
        client = human_client(alice)
        old = export(world, client)
        fresh = export(world, client)
        ExportJob.objects.filter(id=old["id"]).update(expires_at=timezone.now() - timedelta(hours=1))
        assert client.get(f"{world.ws_base()}/exports/{old['id']}/").status_code == 410
        result = human_client(world.owner).post(f"{world.ws_base()}/retention/apply").json()["result"]
        assert result["exports"]["deleted"] == 1
        assert not ExportJob.all_objects.filter(id=old["id"]).exists()
        assert ExportJob.objects.filter(id=fresh["id"]).exists()
        # With a retention period, older jobs go as well.
        ExportJob.objects.filter(id=fresh["id"]).update(created_at=timezone.now() - timedelta(days=5))
        human_client(world.owner).put(f"{world.ws_base()}/retention/",
                                      {"policies": [{"category": "exports", "retain_days": 2}]}, format="json")
        result = human_client(world.owner).post(f"{world.ws_base()}/retention/apply").json()["result"]
        assert result["exports"]["deleted"] == 1 and not ExportJob.objects.exists()
