# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811 - pytest fixtures imported from integration_helpers are used as arguments

"""Tracker sync, field ownership, echo/conflicts, disconnect/reconnect, reconciliation (FR-I03..FR-I06, AC22)."""

import json

import pytest

from plane.package_flow.adapters.base import TransportError
from plane.package_flow.models import (
    AIProposal,
    Delivery,
    DomainEvent,
    ExternalLink,
    InboundEvent,
    IntegrationConnection,
    MergeRequestLink,
    PackageProfile,
    SyncConflict,
)
from plane.package_flow.principal import AGENT, HUMAN, Principal
from plane.package_flow.services import integrations as svc

from .integration_helpers import (  # noqa: F401 - fake_transport is an autouse fixture
    SECRET,
    deliver_gitlab,
    fake_transport,
    gl_headers,
    gl_merged,
    gl_mr,
    hub_signature,
    make_binding,
    make_connection,
    make_package,
    post_webhook,
)


def jira_update(priority=None, summary=None, updated="2026-09-01T10:00:00.000+0000", issue_ext="10001"):
    fields, items = {"updated": updated}, []
    if priority:
        fields["priority"] = {"name": priority}
        items.append({"field": "priority", "toString": priority})
    if summary:
        fields["summary"] = summary
        items.append({"field": "summary", "toString": summary})
    return {
        "webhookEvent": "jira:issue_updated",
        "issue": {"id": issue_ext, "key": "OPS-1", "fields": fields},
        "changelog": {"id": updated, "items": items},
    }


def send_jira(connection, payload, delivery):
    body = json.dumps(payload).encode()
    return svc.ingest_webhook(
        connection.id,
        {"X-Hub-Signature": hub_signature(SECRET, body), "X-Atlassian-Webhook-Identifier": delivery},
        body,
    )


@pytest.fixture
def tracker(world):
    project = world.project()
    issue = world.issue(project)
    issue.priority = "medium"
    issue.save()
    world.enable(project)
    make_package(issue)
    jira = make_connection(world, provider="jira", instance_url="https://acme.atlassian.net", edition="cloud")
    link = ExternalLink.objects.create(
        issue=issue,
        connection=jira,
        object_type="issue",
        external_id="10001",
        external_key="OPS-1",
        represents_package=True,
    )
    return {"project": project, "issue": issue, "jira": jira, "link": link}


@pytest.mark.unit
class TestFieldOwnership:
    def test_ac22_tracker_owned_priority_not_overwritten(self, world, tracker):
        issue, link = tracker["issue"], tracker["link"]
        link.field_ownership = {"priority": "external"}
        link.save()
        ai = Principal(user=world.owner, kind=AGENT, via="runner")
        result = svc.propose_or_apply_field(
            issue, "priority", "urgent", principal=ai, source="ai_summary", reason="Summary sounds urgent"
        )
        assert result["applied"] is False
        proposal = AIProposal.objects.get(id=result["proposal_id"])
        assert proposal.kind == "priority_suggestion" and proposal.content["proposed_value"] == "urgent"
        assert proposal.content["owner"] == "external:jira"
        # Even a human platform write is only a proposal while Jira owns the field.
        human = Principal(user=world.owner, kind=HUMAN)
        assert svc.propose_or_apply_field(issue, "priority", "low", principal=human)["applied"] is False
        issue.refresh_from_db()
        assert issue.priority == "medium"
        # The tracker value itself is applied to the native field.
        send_jira(tracker["jira"], jira_update(priority="High"), "j-1")
        issue.refresh_from_db()
        assert issue.priority == "high"
        assert not SyncConflict.objects.exists()

    def test_platform_owned_external_change_creates_conflict(self, world, tracker, human_client):
        issue = tracker["issue"]
        send_jira(tracker["jira"], jira_update(priority="Highest"), "j-1")
        issue.refresh_from_db()
        assert issue.priority == "medium"
        [conflict] = SyncConflict.objects.filter(issue=issue)
        assert conflict.platform_value == "medium" and conflict.external_value == "urgent"
        assert conflict.platform_changed_at and conflict.external_changed_at
        tracker["link"].refresh_from_db()
        assert tracker["link"].sync_state == "conflict"
        client = human_client(world.owner)
        base = f"{world.base(tracker['project'])}/work-items/{issue.id}/sync-conflicts"
        [row] = client.get(base).json()["results"]
        assert row["external"]["source"] == "jira" and row["platform"]["value"] == "medium"
        r = client.post(f"{base}/{conflict.id}/resolve", {"resolution": "take_external"}, format="json")
        assert r.status_code == 200, r.content
        issue.refresh_from_db()
        tracker["link"].refresh_from_db()
        assert issue.priority == "urgent" and tracker["link"].sync_state == "ok"

    def test_echo_ignored_but_concurrent_change_conflicts(self, world, tracker):
        issue = tracker["issue"]
        human = Principal(user=world.owner, kind=HUMAN)
        result = svc.propose_or_apply_field(issue, "priority", "high", principal=human)
        assert result["applied"] and result["operation_ids"]
        send_jira(tracker["jira"], jira_update(priority="High"), "echo-1")  # our own write coming back
        assert not SyncConflict.objects.exists()
        send_jira(tracker["jira"], jira_update(priority="Low", updated="2026-09-01T10:01:00.000+0000"), "real-1")
        [conflict] = SyncConflict.objects.all()
        assert conflict.platform_value == "high" and conflict.external_value == "low"
        issue.refresh_from_db()
        assert issue.priority == "high"

    def test_late_tracker_event_does_not_regress(self, world, tracker):
        issue, link = tracker["issue"], tracker["link"]
        link.field_ownership = {"priority": "external"}
        link.save()
        send_jira(tracker["jira"], jira_update(priority="High", updated="2026-09-01T10:00:00.000+0000"), "a")
        send_jira(tracker["jira"], jira_update(priority="Low", updated="2026-09-01T09:00:00.000+0000"), "b")
        issue.refresh_from_db()
        assert issue.priority == "high"


@pytest.mark.unit
class TestDisconnectReconnect:
    def test_fr_i06_disconnect_keeps_ids(self, world, tracker, human_client):
        issue, jira = tracker["issue"], tracker["jira"]
        issue_id, link_id = issue.id, tracker["link"].id
        r = human_client(world.owner).delete(f"{world.ws_base()}/connections/{jira.id}/")
        assert r.status_code == 200 and r.json()["status"] == "disabled"
        link = ExternalLink.objects.get(id=link_id)
        assert link.sync_state == "disconnected" and link.issue_id == issue_id and link.external_key == "OPS-1"
        assert PackageProfile.objects.filter(issue_id=issue_id).exists()
        body = json.dumps(jira_update(priority="Low")).encode()
        from rest_framework.test import APIClient

        r = APIClient().post(
            f"/api/package-flow/webhooks/{jira.id}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE=hub_signature(SECRET, body),
        )
        assert r.status_code == 404

    def test_fr_i05_reconnect_no_duplicates(self, world, human_client, fake_transport):
        project = world.project()
        issue = world.issue(project)
        world.enable(project)
        c = make_connection(world)
        make_binding(world, project, c)
        make_package(issue)
        link = ExternalLink.objects.create(issue=issue, connection=c, object_type="merge_request", external_id="5")
        merged = gl_merged(description=f"PH-{issue.id}")
        deliver_gitlab(c, merged, event_uuid="m-1")
        client = human_client(world.owner)
        assert client.delete(f"{world.ws_base()}/connections/{c.id}/").status_code == 200
        assert post_webhook(client, c, merged, gl_headers("m-2")).status_code == 404
        # Provider poll after reconnect returns the same merged MR (within the overlap window).
        fake_transport.add(
            "GET",
            "/merge_requests",
            body=[
                {
                    "iid": 5,
                    "title": "Add export",
                    "description": f"PH-{issue.id}",
                    "state": "merged",
                    "sha": "a" * 40,
                    "merge_commit_sha": "d" * 40,
                    "updated_at": "2026-09-01T12:00:00Z",
                    "source_branch": "feature/export",
                    "target_branch": "main",
                    "target_project_id": 101,
                }
            ],
        )
        r = client.patch(f"{world.ws_base()}/connections/{c.id}/", {"status": "active"}, format="json")
        assert r.status_code == 200 and r.json()["status"] == "active"
        assert post_webhook(client, c, merged, gl_headers("m-1")).json()["duplicate"] is True
        post_webhook(client, c, merged, gl_headers("m-3"))
        assert Delivery.objects.filter(issue=issue).count() == 1
        assert DomainEvent.objects.filter(issue_id=issue.id, event_type="git.merge.observed").count() == 1
        assert MergeRequestLink.objects.filter(issue=issue).count() == 1
        assert ExternalLink.objects.filter(issue=issue).count() == 1
        link.refresh_from_db()
        assert link.sync_state == "ok"
        c.refresh_from_db()
        assert c.last_successful_sync_at is not None and c.sync_cursor.get("watermark")
        assert InboundEvent.objects.filter(connection=c, payload__has_key="polled").count() == 1


class FailingTransport:
    def request(self, method, url, **kwargs):
        raise TransportError("GET failed: ConnectionError")


@pytest.mark.unit
class TestReconciliation:
    def test_reconcile_replays_backlog(self, world, human_client):
        project = world.project()
        issue = world.issue(project)
        world.enable(project)
        c = make_connection(world, edition="premium")
        make_binding(world, project, c)
        # Simulates an event stored but never processed (worker lost).
        ev = InboundEvent.objects.create(
            connection=c,
            workspace=world.workspace,
            external_event_id="lost-1",
            event_type="mr.opened",
            payload={"headers": {}, "body": gl_mr(description=f"PH-{issue.id}")},
        )
        assert svc.connection_health(c)["backlog_count"] == 1
        r = human_client(world.owner).post(f"{world.ws_base()}/connections/{c.id}/reconcile")
        assert r.status_code == 202, r.content
        ev.refresh_from_db()
        assert ev.status == "processed"
        assert MergeRequestLink.objects.filter(issue=issue).exists()
        c.refresh_from_db()
        assert c.backlog_count == 0 and c.last_successful_sync_at is not None

    def test_reconcile_transport_error_degrades_then_recovers(self, world):
        project = world.project()
        c = make_connection(world)
        make_binding(world, project, c)
        from plane.package_flow.adapters.base import override_transport

        with override_transport(FailingTransport()):
            result = svc.reconcile_connection(c.id)
        assert result["status"] == "degraded" and result["gaps"]
        c.refresh_from_db()
        assert c.status == "degraded" and "ConnectionError" in c.last_error
        assert DomainEvent.objects.filter(event_type="integration.stale").count() == 1
        assert svc.connection_health(c)["affected_capabilities"]
        result = svc.reconcile_connection(c.id)  # fake transport: reachable, no changes
        c.refresh_from_db()
        assert c.status == "active"
        assert DomainEvent.objects.filter(event_type="integration.recovered").count() == 1

    def test_failed_processing_is_retried(self, world, monkeypatch):
        project = world.project()
        issue = world.issue(project)
        c = make_connection(world)
        make_binding(world, project, c)
        from plane.package_flow.services import delivery

        original = delivery.handle_code_event
        monkeypatch.setattr(delivery, "handle_code_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        _, body = deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
        ev = InboundEvent.objects.get(id=body["event_id"])
        assert ev.status == "failed" and ev.attempts == 1
        monkeypatch.setattr(delivery, "handle_code_event", original)
        svc.reconcile_connection(c.id)
        ev.refresh_from_db()
        assert ev.status == "processed" and ev.attempts == 2
        assert IntegrationConnection.objects.get(pk=c.pk).backlog_count == 0


JIRA_PUT = "/rest/api/3/issue/10001"


@pytest.mark.unit
class TestOutboundSync:
    def test_platform_owned_title_pushed_once_echo_ignored_concurrent_conflicts(self, tracker, fake_transport):
        issue = tracker["issue"]
        fake_transport.add("PUT", JIRA_PUT, status=204)
        issue.name = "Export invoices as CSV"
        issue.save()
        [put] = fake_transport.called("PUT", JIRA_PUT)
        assert put["json"] == {"fields": {"summary": "Export invoices as CSV"}}
        link = ExternalLink.objects.get(pk=tracker["link"].pk)
        assert link.observed_fields["_last_op"]["fields"] == {"title": "Export invoices as CSV"}
        assert link.observed_fields["_last_push"]["ok"] is True
        op_id = link.observed_fields["_last_op"]["op_id"]
        issue.save()  # no relevant change -> no second push
        assert len(fake_transport.called("PUT")) == 1
        # Our own write comes back from Jira: recognised as echo.
        send_jira(tracker["jira"], jira_update(summary="Export invoices as CSV"), "echo-t")
        assert not SyncConflict.objects.exists()
        assert ExternalLink.objects.get(pk=link.pk).observed_fields["_last_op"]["op_id"] == op_id
        # A different concurrent external edit in the same window is not swallowed.
        send_jira(tracker["jira"], jira_update(summary="Something else", updated="2026-09-01T10:02:00.000+0000"), "c-t")
        [conflict] = SyncConflict.objects.all()
        assert conflict.field == "title" and conflict.external_value == "Something else"
        assert conflict.platform_value == "Export invoices as CSV"
        issue.refresh_from_db()
        assert issue.name == "Export invoices as CSV"
        assert len(fake_transport.called("PUT")) == 1

    def test_external_owned_field_never_pushed(self, tracker, fake_transport):
        issue, link = tracker["issue"], tracker["link"]
        link.field_ownership = {"priority": "external"}
        link.save()
        fake_transport.add("PUT", JIRA_PUT, status=204)
        issue.priority = "urgent"
        issue.save()
        send_jira(tracker["jira"], jira_update(priority="Low"), "ext-p")  # applied natively, not echoed back
        issue.refresh_from_db()
        assert issue.priority == "low"
        assert fake_transport.called("PUT") == []

    def test_offline_connection_queues_push_until_reconcile(self, tracker, fake_transport):
        issue, jira = tracker["issue"], tracker["jira"]
        IntegrationConnection.objects.filter(pk=jira.pk).update(status="offline")
        fake_transport.add("PUT", JIRA_PUT, status=204)
        issue.priority = "high"
        issue.save()
        assert fake_transport.called("PUT") == []
        link = ExternalLink.objects.get(pk=tracker["link"].pk)
        assert link.observed_fields["_pending_push"]["fields"] == {"priority": "high"}
        jira.refresh_from_db()
        assert svc.connection_health(jira)["backlog_count"] == 1
        result = svc.reconcile_connection(jira.id)
        assert result["status"] == "active" and result["pushed"] == 1
        [put] = fake_transport.called("PUT", JIRA_PUT)
        assert put["json"] == {"fields": {"priority": {"name": "High"}}}
        link.refresh_from_db()
        assert "_pending_push" not in link.observed_fields
        assert svc.connection_health(IntegrationConnection.objects.get(pk=jira.pk))["backlog_count"] == 0

    def test_disabled_connection_never_pushes(self, world, tracker, fake_transport):
        svc.disconnect_connection(tracker["jira"], world.owner)
        issue = tracker["issue"]
        issue.name = "changed while disconnected"
        issue.save()
        assert fake_transport.calls == []
        assert "_pending_push" not in ExternalLink.objects.get(pk=tracker["link"].pk).observed_fields

    def test_transport_failure_is_queued_not_lost(self, tracker):
        from plane.package_flow.adapters.base import override_transport

        issue = tracker["issue"]
        with override_transport(FailingTransport()):
            issue.priority = "low"
            issue.save()
        link = ExternalLink.objects.get(pk=tracker["link"].pk)
        assert link.observed_fields["_pending_push"]["fields"] == {"priority": "low"}
