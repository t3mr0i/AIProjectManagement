# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811 - pytest fixtures imported from integration_helpers are used as arguments

"""Webhook ingress, inbox durability, connection API (FR-I04, PRD §13.4, AC02)."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.package_flow.models import (
    ExecutionApproval,
    ExecutionRun,
    ExternalLink,
    InboundEvent,
    IntegrationConnection,
    MergeRequestLink,
)
from plane.package_flow.services import integrations as svc
from plane.tests.package_flow.conftest import World

from .integration_helpers import (  # noqa: F401 - fake_transport is an autouse fixture
    SECRET,
    fake_transport,
    gl_headers,
    gl_mr,
    hub_signature,
    make_binding,
    make_connection,
    make_package,
    post_webhook,
)


@pytest.mark.unit
class TestIngress:
    def test_webhook_bad_signature_returns_401(self, world):
        c = make_connection(world)
        r = post_webhook(APIClient(), c, gl_mr(), gl_headers(str(uuid4()), token="wrong-token-value-123"))
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_SIGNATURE"
        assert not InboundEvent.objects.filter(connection=c).exists()

    def test_unknown_or_disabled_connection_404(self, world):
        r = APIClient().post(f"/api/package-flow/webhooks/{uuid4()}/", data="{}", content_type="application/json")
        assert r.status_code == 404
        c = make_connection(world)
        svc.disconnect_connection(c, world.owner)
        assert post_webhook(APIClient(), c, gl_mr(), gl_headers(str(uuid4()))).status_code == 404

    def test_durable_store_before_ack_and_duplicate(self, world):
        project = world.project()
        issue = world.issue(project)
        c = make_connection(world)
        make_binding(world, project, c)
        payload = gl_mr(description=f"PH-{issue.id}")
        headers = gl_headers("evt-1")
        r1 = post_webhook(APIClient(), c, payload, headers)
        assert r1.status_code == 202, r1.content
        body = r1.json()
        assert body["duplicate"] is False
        ev = InboundEvent.objects.get(id=body["event_id"])
        assert ev.workspace_id == world.workspace.id and ev.status == "processed" and ev.attempts == 1
        # Signature headers are never persisted.
        assert "x-gitlab-token" not in ev.payload["headers"]
        r2 = post_webhook(APIClient(), c, payload, headers)
        assert r2.status_code == 200 and r2.json()["duplicate"] is True
        ev.refresh_from_db()
        assert ev.attempts == 1  # not reprocessed
        assert InboundEvent.objects.filter(connection=c).count() == 1
        assert MergeRequestLink.objects.filter(issue=issue).count() == 1

    def test_payload_claiming_another_workspace_is_ignored(self, world):
        project = world.project()
        c = make_connection(world)
        make_binding(world, project, c)
        other = World()
        other_project = other.project()
        foreign_issue = other.issue(other_project)
        payload = gl_mr(description=f"PH-{foreign_issue.id}")
        payload["workspace"] = other.workspace.slug
        payload["workspace_id"] = str(other.workspace.id)
        r = post_webhook(APIClient(), c, payload, gl_headers("evt-x"))
        assert r.status_code == 202
        ev = InboundEvent.objects.get(id=r.json()["event_id"])
        assert ev.workspace_id == world.workspace.id
        assert ev.status == "ignored"
        assert not MergeRequestLink.objects.filter(issue=foreign_issue).exists()

    def test_github_ingress_uses_hmac(self, world):
        c = make_connection(world, provider="github", instance_url="https://github.com", edition="team")
        payload = {"zen": "hi", "repository": {"id": 1}}
        body = json.dumps(payload).encode()
        client = APIClient()
        ok = client.post(
            f"/api/package-flow/webhooks/{c.id}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=hub_signature(SECRET, body),
            HTTP_X_GITHUB_EVENT="ping",
            HTTP_X_GITHUB_DELIVERY="gh-1",
        )
        assert ok.status_code == 202, ok.content
        bad = client.post(
            f"/api/package-flow/webhooks/{c.id}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=hub_signature("another-secret-value-000", body),
            HTTP_X_GITHUB_EVENT="ping",
            HTTP_X_GITHUB_DELIVERY="gh-2",
        )
        assert bad.status_code == 401

    def test_broker_failure_falls_back_to_sync_processing(
        self, world, settings, monkeypatch, django_capture_on_commit_callbacks
    ):
        settings.PACKAGE_FLOW_INLINE_TASKS = False
        project = world.project()
        issue = world.issue(project)
        c = make_connection(world)
        make_binding(world, project, c)
        from plane.package_flow import tasks

        def boom(*args, **kwargs):
            raise ConnectionError("broker down")

        monkeypatch.setattr(tasks.process_inbound_event, "delay", boom)
        with django_capture_on_commit_callbacks(execute=True):
            status, body = svc.ingest_webhook(
                c.id, gl_headers("evt-broker"), json.dumps(gl_mr(description=f"PH-{issue.id}")).encode()
            )
        assert status == 202
        assert InboundEvent.objects.get(id=body["event_id"]).status == "processed"

    def test_ac02_in_progress_webhook_creates_no_run(self, world):
        project = world.project()
        issue = world.issue(project, is_draft=True)
        state_before = issue.state_id
        make_package(issue, approved=False)
        jira = make_connection(world, provider="jira", instance_url="https://acme.atlassian.net", edition="cloud")
        link = ExternalLink.objects.create(
            issue=issue,
            connection=jira,
            object_type="issue",
            external_id="10001",
            external_key="OPS-1",
            represents_package=True,
        )
        payload = {
            "webhookEvent": "jira:issue_updated",
            "timestamp": 1788000000000,
            "issue": {
                "id": "10001",
                "key": "OPS-1",
                "fields": {"status": {"name": "In Progress"}, "updated": "2026-09-01T10:00:00.000+0000"},
            },
            "changelog": {"id": "1", "items": [{"field": "status", "toString": "In Progress"}]},
        }
        body = json.dumps(payload).encode()
        status, _ = svc.ingest_webhook(
            jira.id, {"X-Hub-Signature": hub_signature(SECRET, body), "X-Atlassian-Webhook-Identifier": "j1"}, body
        )
        assert status == 202
        assert not ExecutionRun.objects.filter(issue=issue).exists()
        assert not ExecutionApproval.objects.filter(issue=issue).exists()
        link.refresh_from_db()
        issue.refresh_from_db()
        # Stored as an external observation, separate from execution rights and the native state.
        assert link.observed_fields["status"] == "In Progress"
        assert issue.state_id == state_before and issue.is_draft


@pytest.mark.unit
class TestConnectionApi:
    def test_providers_listed(self, world, human_client):
        r = human_client(world.owner).get(f"{world.ws_base()}/providers/")
        assert r.status_code == 200
        assert {p["provider"] for p in r.json()["providers"]} == {
            "gitlab",
            "jira",
            "linear",
            "azure_devops",
            "generic_git",
            "github",
        }

    def test_crud_never_returns_secret(self, world, human_client):
        world.enable()
        client = human_client(world.owner)
        r = client.post(
            f"{world.ws_base()}/connections/",
            {
                "provider": "gitlab",
                "instance_url": "https://gl.example.test",
                "edition": "premium",
                "webhook_secret": SECRET,
            },
            format="json",
        )
        assert r.status_code == 201, r.content
        assert SECRET not in r.content.decode()
        assert r.json()["webhook_secret_configured"] is True
        cid = r.json()["id"]
        stored = IntegrationConnection.objects.get(id=cid).webhook_secret
        assert stored and stored != SECRET
        detail = client.get(f"{world.ws_base()}/connections/{cid}/")
        assert SECRET not in detail.content.decode()
        dup = client.post(
            f"{world.ws_base()}/connections/",
            {"provider": "gitlab", "instance_url": "https://gl.example.test"},
            format="json",
        )
        assert dup.status_code == 409 and dup.json()["code"] == "CONNECTION_EXISTS"
        health = client.get(f"{world.ws_base()}/connections/{cid}/health")
        assert health.status_code == 200 and health.json()["status"] == "active"
        gone = client.delete(f"{world.ws_base()}/connections/{cid}/")
        assert gone.status_code == 200 and gone.json()["status"] == "disabled"

    def test_non_admin_without_grant_cannot_manage(self, world, human_client):
        world.enable()
        member = world.member(role=15)
        r = human_client(member).post(
            f"{world.ws_base()}/connections/",
            {"provider": "gitlab", "instance_url": "https://x.example.test"},
            format="json",
        )
        assert r.status_code == 403


@pytest.mark.unit
class TestIngressLimits:
    def test_rate_limit_per_connection_returns_429_with_retry_after(self, world, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "pf-rl"}}
        settings.PACKAGE_FLOW_WEBHOOK_RATE_LIMIT = 2
        settings.PACKAGE_FLOW_WEBHOOK_RATE_WINDOW_SECONDS = 60
        c = make_connection(world)
        other = make_connection(world, instance_url="https://other.example.test")
        client = APIClient()
        assert post_webhook(client, c, gl_mr(), gl_headers("r1")).status_code == 202
        assert post_webhook(client, c, gl_mr(), gl_headers("r2")).status_code == 202
        r = post_webhook(client, c, gl_mr(), gl_headers("r3"))
        assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"
        assert 1 <= int(r["Retry-After"]) <= 60
        assert not InboundEvent.objects.filter(connection=c, external_event_id="gitlab:r3").exists()
        # Quota is per connection; bad signatures do not consume it.
        assert post_webhook(client, other, gl_mr(), gl_headers("o1")).status_code == 202

    def test_replay_window_stores_old_event_as_ignored(self, world, settings):
        settings.PACKAGE_FLOW_WEBHOOK_MAX_AGE_SECONDS = 7 * 24 * 3600
        from django.utils import timezone as tz

        project = world.project()
        issue = world.issue(project)
        c = make_connection(world)
        make_binding(world, project, c)
        old = (tz.now() - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = post_webhook(APIClient(), c, gl_mr(description=f"PH-{issue.id}", updated_at=old), gl_headers("old-1"))
        assert r.status_code == 202 and r.json()["ignored"] == "outside_replay_window"
        ev = InboundEvent.objects.get(id=r.json()["event_id"])
        assert ev.status == "ignored" and "replay window" in ev.error
        assert not MergeRequestLink.objects.filter(issue=issue).exists()
        fresh = tz.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        r = post_webhook(APIClient(), c, gl_mr(description=f"PH-{issue.id}", updated_at=fresh), gl_headers("new-1"))
        assert r.status_code == 202 and "ignored" not in r.json()
        assert MergeRequestLink.objects.filter(issue=issue).exists()
