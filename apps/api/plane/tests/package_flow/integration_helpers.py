# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared builders for integration/delivery/review tests.

No test ever reaches the network: every adapter created during a test uses
:class:`FakeTransport` (installed by the autouse ``fake_transport`` fixture).
Unmatched requests answer 404 so an unexpected call is visible, never sent.
"""

import hashlib
import hmac
import json
from uuid import uuid4

import pytest

from plane.package_flow.adapters.base import HttpResponse, HttpTransport, override_transport
from plane.package_flow.models import PackageProfile, PackageRevision, RepositoryBinding
from plane.package_flow.services import integrations as svc

SECRET = "whsec-" + "x" * 26
HEAD_A = "a" * 40
HEAD_B = "b" * 40
HEAD_C = "c" * 40


class FakeTransport(HttpTransport):
    def __init__(self):
        self.routes = []
        self.calls = []

    def add(self, method, contains, status=200, body=None):
        self.routes.insert(0, (method, contains, HttpResponse(status=status, body=body)))
        return self

    def request(self, method, url, *, headers=None, params=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "params": params, "json": json})
        for m, contains, resp in self.routes:
            if m == method and contains in url:
                return resp
        return HttpResponse(status=404, body={"message": "not found (fake transport)"})

    def called(self, method, contains=""):
        return [c for c in self.calls if c["method"] == method and contains in c["url"]]


@pytest.fixture(autouse=True)
def fake_transport(settings):
    settings.PACKAGE_FLOW_INLINE_TASKS = True
    # Fixture payloads carry fixed historical timestamps; tests of the replay window/rate limit opt in.
    settings.PACKAGE_FLOW_WEBHOOK_MAX_AGE_SECONDS = 0
    settings.PACKAGE_FLOW_WEBHOOK_RATE_LIMIT = 0
    transport = FakeTransport()
    with override_transport(transport):
        yield transport


def make_connection(
    world, provider="gitlab", instance_url="https://gitlab.example.test", edition="premium", secret=SECRET, **extra
):
    data = {"provider": provider, "instance_url": instance_url, "edition": edition, "webhook_secret": secret, **extra}
    return svc.create_connection(world.workspace, world.owner, data)


def make_binding(world, project, connection, external_id="101", path="grp/app", role="backend", branch="main"):
    return RepositoryBinding.objects.create(
        workspace=world.workspace,
        project=project,
        connection=connection,
        external_id=str(external_id),
        path_with_namespace=path,
        default_branch=branch,
        role=role,
    )


def make_package(issue, bindings=(), criteria=None, approved=True, content_hash=None, package_type="code"):
    revision = PackageRevision.objects.create(
        issue=issue,
        number=1,
        title=issue.name,
        intent="Customers can export invoices",
        outcome="Export button produces a CSV",
        scope={"repositories": [{"bindingId": str(b.id)} for b in bindings]},
        criteria=criteria if criteria is not None else [],
        content_hash=content_hash or hashlib.sha256(str(uuid4()).encode()).hexdigest(),
        package_type=package_type,
    )
    profile = PackageProfile.objects.create(
        issue=issue,
        package_type=package_type,
        working_revision=revision,
        approved_revision=revision if approved else None,
    )
    return profile, revision


# ---------------------------------------------------------------------------
# GitLab payloads
# ---------------------------------------------------------------------------


def gl_mr(
    project_ext="101",
    iid=5,
    *,
    action="open",
    state="opened",
    head=HEAD_A,
    title="Add export",
    source="feature/export",
    target="main",
    description="",
    updated_at="2026-09-01T10:00:00Z",
    merge_commit_sha=None,
    squash=False,
    squash_commit_sha=None,
    message="wip",
    path="grp/app",
):
    return {
        "object_kind": "merge_request",
        "project": {"id": int(project_ext), "path_with_namespace": path},
        "object_attributes": {
            "iid": iid,
            "id": 1000 + iid,
            "title": title,
            "description": description,
            "state": state,
            "action": action,
            "source_branch": source,
            "target_branch": target,
            "last_commit": {"id": head, "message": message, "timestamp": updated_at},
            "merge_commit_sha": merge_commit_sha,
            "squash": squash,
            "squash_commit_sha": squash_commit_sha,
            "updated_at": updated_at,
            "url": f"https://gitlab.example.test/{path}/-/merge_requests/{iid}",
            "target_project_id": int(project_ext),
        },
    }


def gl_merged(project_ext="101", iid=5, *, head=HEAD_A, merge_sha="d" * 40, updated_at="2026-09-01T12:00:00Z", **kw):
    return gl_mr(
        project_ext,
        iid,
        action="merge",
        state="merged",
        head=head,
        merge_commit_sha=merge_sha,
        updated_at=updated_at,
        **kw,
    )


def gl_pipeline(
    project_ext="101",
    *,
    sha=HEAD_A,
    status="success",
    name="tests",
    pipeline_id=77,
    iid=None,
    finished_at="2026-09-01T11:00:00Z",
    ref="feature/export",
):
    return {
        "object_kind": "pipeline",
        "project": {"id": int(project_ext), "path_with_namespace": "grp/app"},
        "object_attributes": {
            "id": pipeline_id,
            "ref": ref,
            "sha": sha,
            "status": status,
            "name": name,
            "created_at": finished_at,
            "finished_at": finished_at,
        },
        "merge_request": {"iid": iid} if iid else None,
    }


def gl_deployment(
    project_ext="101",
    *,
    sha="d" * 40,
    env="production",
    deployment_id=9,
    status="success",
    changed_at="2026-09-02T09:00:00Z",
):
    return {
        "object_kind": "deployment",
        "status": status,
        "deployment_id": deployment_id,
        "environment": env,
        "sha": sha,
        "ref": "main",
        "status_changed_at": changed_at,
        "project": {"id": int(project_ext), "path_with_namespace": "grp/app"},
    }


def gl_push(project_ext="101", *, branch="feature/export", after=HEAD_B, commits=None):
    return {
        "object_kind": "push",
        "ref": f"refs/heads/{branch}",
        "before": HEAD_A,
        "after": after,
        "project": {"id": int(project_ext), "path_with_namespace": "grp/app"},
        "commits": commits or [{"id": after, "message": "fix", "timestamp": "2026-09-01T10:30:00Z"}],
    }


def gl_headers(event_uuid=None, token=SECRET):
    headers = {"X-Gitlab-Token": token}
    if event_uuid:
        headers["X-Gitlab-Event-UUID"] = event_uuid
    return headers


def deliver(connection, payload, headers):
    """Service-level ingress (ack + inline processing via PACKAGE_FLOW_INLINE_TASKS)."""
    return svc.ingest_webhook(connection.id, headers, json.dumps(payload).encode())


def deliver_gitlab(connection, payload, event_uuid=None, token=SECRET):
    return deliver(connection, payload, gl_headers(event_uuid or str(uuid4()), token))


def post_webhook(client, connection, payload, headers):
    extra = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()}
    return client.post(
        f"/api/package-flow/webhooks/{connection.id}/",
        data=json.dumps(payload),
        content_type="application/json",
        **extra,
    )


def hub_signature(secret, body: bytes, prefix="sha256="):
    return prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
