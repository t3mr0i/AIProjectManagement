# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811 - pytest fixtures imported from integration_helpers are used as arguments

"""Human review approvals and the merge gate (FR-R03, FR-R04, FR-G10, INV-03, INV-05, AC16, AC17)."""

import hashlib

import pytest

from plane.package_flow.models import (
    Capability,
    Delivery,
    DomainEvent,
    MergeRequestLink,
    PackageRevision,
    ReviewApproval,
)

from .integration_helpers import (  # noqa: F401 - fake_transport is an autouse fixture
    HEAD_A,
    HEAD_B,
    HEAD_C,
    deliver_gitlab,
    fake_transport,
    gl_merged,
    gl_mr,
    make_binding,
    make_connection,
    make_package,
)


@pytest.fixture
def setup(world):
    project = world.project()
    issue = world.issue(project)
    world.enable(project)
    world.grant_all(world.owner, project)
    c = make_connection(world)
    b = make_binding(world, project, c)
    profile, revision = make_package(issue, bindings=[b])
    deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
    link = MergeRequestLink.objects.get(issue=issue)
    return {
        "project": project,
        "issue": issue,
        "connection": c,
        "binding": b,
        "link": link,
        "revision": revision,
        "profile": profile,
    }


def _approve(client, world, s, kind="code", head=HEAD_A, **extra):
    body = {"kind": kind, "decision": "approved", **extra}
    if kind == "code":
        body.update(merge_request_id=str(s["link"].id), head_sha=head)
    return client.post(f"{world.base(s['project'])}/reviews/{s['issue'].id}/approvals", body, format="json")


def _merge(client, world, s, head=HEAD_A):
    return client.post(
        f"{world.base(s['project'])}/merge-requests/{s['link'].id}/merge", {"expected_head_sha": head}, format="json"
    )


def _provider_ok(t, head=HEAD_A, protected=True):
    t.add("GET", "/merge_requests/5", body={"sha": head, "state": "opened", "diff_refs": {"start_sha": ""}})
    if protected:
        t.add("GET", "/protected_branches/main", body={"name": "main"})
    t.add("PUT", "/merge_requests/5/merge", body={"state": "merged", "merge_commit_sha": "d" * 40})


@pytest.mark.unit
class TestApprovals:
    def test_agent_cannot_approve_or_merge(self, world, setup, runner_client):
        _, token = world.runner(world.owner)
        client = runner_client(token)
        r = _approve(client, world, setup)
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        r = _merge(client, world, setup)
        assert r.status_code == 403 and r.json()["code"] == "HUMAN_PRINCIPAL_REQUIRED"
        assert not ReviewApproval.objects.exists()

    def test_code_approval_needs_capability(self, world, setup, human_client):
        member = world.member()
        world.add_project_member(setup["project"], member, 15)
        r = _approve(human_client(member), world, setup)
        assert r.status_code == 403
        world.grant(member, Capability.REVIEW_APPROVE_CODE, setup["project"])
        r = _approve(human_client(member), world, setup)
        assert r.status_code == 201, r.content
        body = r.json()
        assert body["head_sha"] == HEAD_A and body["valid"] is True
        a = ReviewApproval.objects.get(id=body["id"])
        assert a.revision_id == setup["revision"].id and a.policy_version
        assert DomainEvent.objects.filter(event_type="review.approved", actor_kind="human").count() == 1

    def test_approval_of_stale_head_rejected(self, world, setup, human_client):
        r = _approve(human_client(world.owner), world, setup, head=HEAD_B)
        assert r.status_code == 409 and r.json()["code"] == "HEAD_MISMATCH"

    def test_ac16_new_head_invalidates_code_approval(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        deliver_gitlab(
            setup["connection"],
            gl_mr(
                action="update", head=HEAD_B, description=f"PH-{setup['issue'].id}", updated_at="2026-09-01T10:10:00Z"
            ),
        )
        a = ReviewApproval.objects.get()
        assert a.invalidated_at is not None and "new head" in a.invalidated_reason
        assert DomainEvent.objects.filter(event_type="review.invalidated").count() == 1
        review = client.get(f"{world.base(setup['project'])}/work-items/{setup['issue'].id}/review").json()
        [open_review] = [p for p in review["open_points"] if p["kind"] == "code_review_required"]
        assert open_review["head_sha"] == HEAD_B and open_review["invalidated"] is True
        assert review["approvals"][0]["validity"] == "invalidated"
        _provider_ok(fake_transport, head=HEAD_B)
        r = _merge(client, world, setup, head=HEAD_B)
        assert r.status_code == 409 and r.json()["code"] == "REVIEW_REQUIRED"
        assert not fake_transport.called("PUT")

    def test_fr_r04_outcome_acceptance_does_not_grant_merge(self, world, setup, human_client, fake_transport):
        biz = world.member()
        world.add_project_member(setup["project"], biz, 15)
        world.grant(biz, Capability.REVIEW_ACCEPT_OUTCOME, setup["project"])
        assert _approve(human_client(biz), world, setup, kind="outcome").status_code == 201
        assert _merge(human_client(biz), world, setup).status_code == 403
        _provider_ok(fake_transport)
        r = _merge(human_client(world.owner), world, setup)
        assert r.status_code == 409 and r.json()["code"] == "REVIEW_REQUIRED"
        assert not fake_transport.called("PUT")


@pytest.mark.unit
class TestMergeGate:
    def test_happy_path_is_pending_until_provider_confirms(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        _provider_ok(fake_transport)
        r = _merge(client, world, setup)
        assert r.status_code == 202, r.content
        assert r.json()["status"] == "pending_confirmation"
        [put] = fake_transport.called("PUT", "/merge")
        assert put["json"]["sha"] == HEAD_A
        # GET of the provider head happened before the PUT.
        methods = [c["method"] for c in fake_transport.calls]
        assert methods.index("GET") < methods.index("PUT")
        link = MergeRequestLink.objects.get(pk=setup["link"].pk)
        assert link.state == "open" and link.pending_merge["head_sha"] == HEAD_A
        assert not Delivery.objects.filter(issue=setup["issue"]).exists()
        # Idempotent replay while pending: no second provider call.
        assert _merge(client, world, setup).status_code == 202
        assert len(fake_transport.called("PUT")) == 1
        deliver_gitlab(setup["connection"], gl_merged(description=f"PH-{setup['issue'].id}"))
        link.refresh_from_db()
        assert link.state == "merged" and link.pending_merge.get("confirmed_at")
        assert Delivery.objects.filter(issue=setup["issue"], stage="integrated").count() == 1

    def test_ac17_head_changed_before_merge(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        _provider_ok(fake_transport, head=HEAD_C)
        r = _merge(client, world, setup)
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "HEAD_MISMATCH"
        assert body["detail"]["provider_head_sha"] == HEAD_C and body["detail"]["approved_head_sha"] == HEAD_A
        assert not fake_transport.called("PUT")
        assert ReviewApproval.objects.get().invalidated_at is not None
        assert MergeRequestLink.objects.get(pk=setup["link"].pk).head_sha == HEAD_C

    def test_expected_head_must_match(self, world, setup, human_client):
        r = _merge(human_client(world.owner), world, setup, head=HEAD_B)
        assert r.status_code == 409 and r.json()["code"] == "HEAD_MISMATCH"

    def test_fr_g10_unprotected_branch_is_read_only(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        _provider_ok(fake_transport, protected=False)
        r = _merge(client, world, setup)
        assert r.status_code == 409 and r.json()["code"] == "CAPABILITY_MISSING"
        assert r.json()["detail"]["reason"] == "target_branch_unprotected"
        assert not fake_transport.called("PUT")

    def test_fr_g10_edition_without_approval_rules_blocks(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        c = setup["connection"]
        c.edition = "free"
        c.save()
        _provider_ok(fake_transport)
        r = _merge(client, world, setup)
        assert r.status_code == 409 and r.json()["code"] == "CAPABILITY_MISSING"
        assert "verify_human_approval" in r.json()["detail"]["missing"]
        assert fake_transport.calls == []

    def test_inv05_revision_changed_blocks_merge(self, world, setup, human_client, fake_transport):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        PackageRevision.objects.create(
            issue=setup["issue"], number=2, title="changed", content_hash=hashlib.sha256(b"changed").hexdigest()
        )
        _provider_ok(fake_transport)
        r = _merge(client, world, setup)
        assert r.status_code == 409 and r.json()["code"] == "REVISION_STALE"
        assert not fake_transport.called("PUT")

    def test_offline_integration_blocks_merge(self, world, setup, human_client):
        client = human_client(world.owner)
        assert _approve(client, world, setup).status_code == 201
        c = setup["connection"]
        c.status = "offline"
        c.save()
        r = _merge(client, world, setup)
        assert r.status_code == 409 and r.json()["code"] == "CAPABILITY_MISSING"
