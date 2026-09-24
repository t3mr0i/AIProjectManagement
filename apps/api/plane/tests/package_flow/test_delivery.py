# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811 - pytest fixtures imported from integration_helpers are used as arguments

"""Delivery correlation and projection (FR-G01, FR-G08, FR-G09, FR-R01/02/05/06, AC15..AC23, AC32, PF10, PF11)."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from plane.package_flow.models import (
    AuditEntry,
    Delivery,
    DomainEvent,
    Evidence,
    InboundEvent,
    IntegrationConnection,
    MergeRequestLink,
    RepositoryBinding,
)
from plane.package_flow.services import integrations as svc
from plane.package_flow.services.delivery import delivery_summary, observe_native_merge, review_view

from .integration_helpers import (  # noqa: F401 - fake_transport is an autouse fixture
    HEAD_A,
    SECRET,
    deliver,
    deliver_gitlab,
    fake_transport,
    gl_deployment,
    gl_merged,
    gl_mr,
    gl_pipeline,
    gl_push,
    hub_signature,
    make_binding,
    make_connection,
    make_package,
)

CI_CRITERION = [{"id": "c1", "statement": "Automated tests pass", "verification": "ci", "required": True}]


def _setup(world, **pkg):
    project = world.project(identifier="ABC")
    issue = world.issue(project, name="Export invoices")
    c = make_connection(world)
    b = make_binding(world, project, c)
    world.enable(project)
    make_package(issue, bindings=[b], **pkg)
    return project, issue, c, b


def _merge_events(issue):
    return DomainEvent.objects.filter(issue_id=issue.id, event_type="git.merge.observed")


@pytest.mark.unit
class TestEvidence:
    def test_ac15_commit_message_is_not_test_evidence(self, world):
        project, issue, c, b = _setup(world, criteria=CI_CRITERION)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}", message="All tests passed"))
        deliver_gitlab(
            c,
            gl_push(commits=[{"id": "b" * 40, "message": "Alle Tests bestanden", "timestamp": "2026-09-01T10:30:00Z"}]),
        )
        assert not Evidence.objects.filter(issue=issue).exists()
        # A local self-report does not satisfy a trusted-CI criterion either (FR-R02).
        Evidence.objects.create(
            issue=issue,
            kind="test",
            name="tests",
            source="agent",
            trust="local_self_report",
            result="passed",
            criterion_ids=["c1"],
            occurred_at=timezone.now(),
        )
        view = review_view(issue)
        [crit] = view["criteria"]
        assert crit["state"] == "not_proven"
        assert "trust" in crit["reason"]
        messages = [
            cl for cl in view["claims"] if "passed" in (cl["message"] or "") or "bestanden" in (cl["message"] or "")
        ]
        assert messages and all(cl["status"] == "claimed" for cl in messages)
        assert any(p["kind"] == "criterion_not_proven" for p in view["open_points"])

    def test_provider_ci_proves_criterion(self, world):
        project, issue, c, b = _setup(world, criteria=CI_CRITERION)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
        deliver_gitlab(c, gl_pipeline(status="success", iid=5))
        [ev] = Evidence.objects.filter(issue=issue)
        assert ev.trust == "provider_ci" and ev.commit_sha == HEAD_A
        assert review_view(issue)["criteria"][0]["state"] == "proven"


@pytest.mark.unit
class TestDeliveryStates:
    def test_ac18_partial_integration_two_repos(self, world):
        project = world.project()
        issue = world.issue(project)
        c = make_connection(world)
        backend = make_binding(world, project, c, external_id="101", path="grp/backend", role="backend")
        frontend = make_binding(world, project, c, external_id="202", path="grp/frontend", role="frontend")
        make_package(issue, bindings=[backend, frontend])
        assert delivery_summary(issue)["delivery"] == "not_integrated"
        deliver_gitlab(c, gl_mr("101", description=f"PH-{issue.id}"))
        deliver_gitlab(c, gl_mr("202", iid=8, description=f"PH-{issue.id}"))
        deliver_gitlab(c, gl_merged("101", description=f"PH-{issue.id}"))
        s = delivery_summary(issue)
        assert s["delivery"] == "partially_integrated"
        states = {r["role"]: r["delivery"] for r in s["repositories"]}
        assert states == {"backend": "integrated", "frontend": "not_integrated"}
        deliver_gitlab(c, gl_merged("202", iid=8, merge_sha="8" * 40, description=f"PH-{issue.id}"))
        assert delivery_summary(issue)["delivery"] == "integrated"

    def test_ac19_merge_without_deploy_not_productive(self, world, fake_transport):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_merged(description=f"PH-{issue.id}", merge_sha="d" * 40))
        s = delivery_summary(issue)
        assert s["delivery"] == "integrated"
        assert s["repositories"][0]["environments"] == []
        # A later deployment of a descendant commit counts only via the provider ancestry check.
        fake_transport.add("GET", "/repository/merge_base", body={"id": "d" * 40})
        deliver_gitlab(c, gl_deployment(sha="e" * 40, env="production"))
        s = delivery_summary(issue)
        assert s["delivery"] == "deployed"
        assert s["repositories"][0]["environments"][0]["name"] == "production"

    def test_failed_deployment_is_not_delivery(self, world):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_merged(description=f"PH-{issue.id}", merge_sha="d" * 40))
        deliver_gitlab(c, gl_deployment(sha="d" * 40, status="failed"))
        assert delivery_summary(issue)["delivery"] == "integrated"

    def test_ac20_rollback_keeps_history(self, world):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_merged(description=f"PH-{issue.id}", merge_sha="d" * 40))
        deliver_gitlab(c, gl_deployment(sha="d" * 40, env="production"))
        assert delivery_summary(issue)["delivery"] == "deployed"
        revert = gl_merged(
            iid=6,
            title='Revert "Add export"',
            description="This reverts merge request !5",
            source="revert-export",
            head="7" * 40,
            merge_sha="6" * 40,
            updated_at="2026-09-03T10:00:00Z",
        )
        deliver_gitlab(c, revert)
        s = delivery_summary(issue)
        assert s["delivery"] == "rolled_back"
        rows = list(Delivery.objects.filter(issue=issue).order_by("occurred_at"))
        assert [r.stage for r in rows] == ["integrated", "deployed", "rolled_back"]
        assert rows[-1].reverts_id == rows[1].id
        assert DomainEvent.objects.filter(issue_id=issue.id, event_type="delivery.rolled_back").count() == 1

    def test_ac20_environment_rollback_github(self, world):
        project = world.project()
        issue = world.issue(project)
        gh = make_connection(world, provider="github", instance_url="https://github.com", edition="team")
        b = make_binding(world, project, gh, external_id="55", path="org/app")
        make_package(issue, bindings=[b])

        def send(event, payload, delivery):
            body = json.dumps(payload).encode()
            svc.ingest_webhook(
                gh.id,
                {
                    "X-GitHub-Event": event,
                    "X-GitHub-Delivery": delivery,
                    "X-Hub-Signature-256": hub_signature(SECRET, body),
                },
                body,
            )

        pr = {
            "number": 3,
            "title": "Export",
            "body": f"PH-{issue.id}",
            "merged": True,
            "merge_commit_sha": "f" * 40,
            "merged_at": "2026-09-01T12:00:00Z",
            "head": {"ref": "feat", "sha": HEAD_A},
            "base": {"ref": "main", "sha": "0" * 40, "repo": {"id": 55}},
        }
        send("pull_request", {"action": "closed", "repository": {"id": 55}, "pull_request": pr}, "g1")
        dep = {
            "repository": {"id": 55},
            "deployment": {"id": 1, "sha": "f" * 40, "environment": "production"},
            "deployment_status": {
                "state": "success",
                "environment": "production",
                "updated_at": "2026-09-02T00:00:00Z",
            },
        }
        send("deployment_status", dep, "g2")
        assert delivery_summary(issue)["delivery"] == "deployed"
        rb = {
            "repository": {"id": 55},
            "deployment": {"id": 2, "sha": "1" * 40, "environment": "production", "task": "deploy:rollback"},
            "deployment_status": {
                "state": "success",
                "environment": "production",
                "updated_at": "2026-09-03T00:00:00Z",
            },
        }
        send("deployment_status", rb, "g3")
        s = delivery_summary(issue)
        assert s["delivery"] == "rolled_back"
        assert s["repositories"][0]["environments"][0]["state"] == "rolled_back"
        assert Delivery.objects.filter(issue=issue, stage="deployed").count() == 1  # history kept

    def test_ac21_duplicate_and_late_events(self, world):
        project, issue, c, b = _setup(world, criteria=CI_CRITERION)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}", updated_at="2026-09-01T10:00:00Z"))
        deliver_gitlab(c, gl_pipeline(status="success", pipeline_id=78, finished_at="2026-09-01T11:00:00Z"))
        merged = gl_merged(description=f"PH-{issue.id}", updated_at="2026-09-01T12:00:00Z")
        status, first = deliver_gitlab(c, merged, event_uuid="m-1")
        assert status == 202
        status, again = deliver_gitlab(c, merged, event_uuid="m-1")
        assert status == 200 and again["duplicate"] is True and again["event_id"] == first["event_id"]
        assert InboundEvent.objects.get(id=first["event_id"]).attempts == 1
        # Same merge from a different raw delivery (provider retry with new id).
        deliver_gitlab(c, merged, event_uuid="m-2")
        # Older build + older MR update arrive late.
        deliver_gitlab(c, gl_pipeline(status="failed", pipeline_id=76, finished_at="2026-09-01T10:30:00Z"))
        deliver_gitlab(
            c, gl_mr(action="update", head="9" * 40, description=f"PH-{issue.id}", updated_at="2026-09-01T09:00:00Z")
        )
        assert _merge_events(issue).count() == 1
        assert Delivery.objects.filter(issue=issue, stage="integrated").count() == 1
        link = MergeRequestLink.objects.get(issue=issue)
        assert link.state == "merged" and link.head_sha == HEAD_A
        assert delivery_summary(issue)["delivery"] == "integrated"
        assert review_view(issue)["criteria"][0]["state"] == "proven"

    def test_ac23_offline_integration_shows_last_known(self, world, human_client):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_merged(description=f"PH-{issue.id}"))
        last = timezone.now() - timedelta(hours=5)
        IntegrationConnection.objects.filter(pk=c.pk).update(status="offline", last_successful_sync_at=last)
        s = delivery_summary(issue)
        assert "integration_offline" in s["flags"]
        assert s["integrations"][0]["last_successful_sync_at"] == last.isoformat()
        assert s["last_known_at"] == last.isoformat()
        health = human_client(world.owner).get(f"{world.ws_base()}/connections/{c.id}/health").json()
        assert health["status"] == "offline" and health["live"] is False
        assert "read_merge_requests" in health["affected_capabilities"]
        assert health["last_successful_sync_at"] == last.isoformat()
        # Active but stale connection is flagged as well.
        IntegrationConnection.objects.filter(pk=c.pk).update(status="active")
        assert "integration_offline" in delivery_summary(issue)["flags"]
        IntegrationConnection.objects.filter(pk=c.pk).update(last_successful_sync_at=timezone.now())
        assert "integration_offline" not in delivery_summary(issue)["flags"]

    def test_ac32_no_runner_local_state_unknown(self, world, human_client):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
        r = human_client(world.owner).get(f"{world.base(project)}/work-items/{issue.id}/delivery")
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["visibility"] == "known_provider_states_only"
        assert body["local_state"] == "unknown"
        text = json.dumps(body).lower()
        assert "uncommitted" not in text and "working_copy" not in text
        assert body["repositories"][0]["merge_request_state"] == "open"

    def test_pf10_native_activity_and_webhook_correlate_once(self, world):
        project, issue, c, b = _setup(world)
        observe_native_merge(issue, b, "5", ref="issue-activity:123")
        merged = gl_merged(description=f"PH-{issue.id}", merge_sha="d" * 40)
        deliver_gitlab(c, merged, event_uuid="w-1")
        deliver_gitlab(c, merged, event_uuid="w-2")
        deliver_gitlab(c, merged, event_uuid="w-1")
        assert _merge_events(issue).count() == 1
        [d] = Delivery.objects.filter(issue=issue)
        assert d.commit_sha == "d" * 40
        kinds = [s["kind"] for s in d.detail["sources"]]
        assert kinds.count("native_activity") == 1 and kinds.count("provider_webhook") == 2
        assert InboundEvent.objects.filter(connection=c).count() == 2  # raw sources stay traceable

    def test_pf11_done_is_not_deployment(self, world):
        project = world.project()
        done = world.state(project, name="Done", group="completed")
        issue = world.issue(project, state=done)
        make_package(issue)
        s = delivery_summary(issue)
        assert s["delivery"] not in ("deployed", "released")
        assert s["delivery"] == "unknown"
        assert "native_done_without_delivery_evidence" in s["flags"]

    def test_fr_g01_same_name_repos_different_instances(self, world):
        project = world.project()
        issue_a = world.issue(project)
        issue_b = world.issue(project)
        ca = make_connection(world, instance_url="https://gitlab-a.example.test")
        cb = make_connection(world, instance_url="https://gitlab-b.example.test")
        ba = make_binding(world, project, ca, external_id="101", path="grp/app")
        bb = make_binding(world, project, cb, external_id="101", path="grp/app")
        assert ba.id != bb.id and RepositoryBinding.objects.filter(project=project).count() == 2
        deliver_gitlab(ca, gl_mr(description=f"PH-{issue_a.id}"))
        deliver_gitlab(cb, gl_mr(description=f"PH-{issue_b.id}", head="3" * 40))
        la = MergeRequestLink.objects.get(repository_binding=ba)
        lb = MergeRequestLink.objects.get(repository_binding=bb)
        assert la.issue_id == issue_a.id and lb.issue_id == issue_b.id
        assert la.head_sha == HEAD_A and lb.head_sha == "3" * 40

    def test_fr_g08_squash_merge_records_new_commit(self, world):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
        deliver_gitlab(
            c, gl_merged(description=f"PH-{issue.id}", merge_sha=None, squash=True, squash_commit_sha="e" * 40)
        )
        [d] = Delivery.objects.filter(issue=issue, stage="integrated")
        assert d.commit_sha == "e" * 40 and d.commit_sha != HEAD_A
        assert delivery_summary(issue)["repositories"][0]["integrated_commit_sha"] == "e" * 40

    def test_sequence_reference_in_branch_correlates(self, world):
        project, issue, c, b = _setup(world)
        deliver_gitlab(c, gl_mr(source=f"feature/abc-{issue.sequence_id}-export"))
        assert MergeRequestLink.objects.filter(issue=issue).exists()


@pytest.mark.unit
class TestImportPreview:
    def test_j01_preview_observed_and_proposed_without_writes(self, world, human_client, fake_transport):
        project = world.project()
        c = make_connection(world)
        fake_transport.add(
            "GET", "/projects/101", body={"id": 101, "path_with_namespace": "grp/app", "default_branch": "main"}
        )
        fake_transport.add("GET", "/repository/commits/main", body={"id": "c" * 40})
        fake_transport.add(
            "GET",
            "/repository/tree",
            body=[{"path": "openspec/specs/export/spec.md", "type": "blob"}, {"path": "src/app.py", "type": "blob"}],
        )
        fake_transport.add(
            "GET",
            "/merge_requests",
            body=[
                {
                    "iid": 1,
                    "title": "Old",
                    "state": "merged",
                    "sha": "1" * 40,
                    "updated_at": "2025-01-01T00:00:00Z",
                    "source_branch": "x",
                    "target_branch": "main",
                }
            ],
        )
        def counts():
            return (
                DomainEvent.objects.count(),
                AuditEntry.objects.count(),
                RepositoryBinding.objects.count(),
                InboundEvent.objects.count(),
            )

        before = counts()
        r = human_client(world.owner).post(
            f"{world.base(project)}/repositories/import-preview",
            {"connection_id": str(c.id), "external_id": "101"},
            format="json",
        )
        assert r.status_code == 200, r.content
        body = r.json()
        assert counts() == before
        assert body["commit"] == "c" * 40 and body["writes_performed"] is False
        kinds = {(i["kind"], i["status"]) for i in body["items"]}
        assert ("repository", "observed") in kinds and ("spec_file", "observed") in kinds
        assert ("package_proposal", "proposed") in kinds and ("merge_request", "observed") in kinds
        mr = next(i for i in body["items"] if i["kind"] == "merge_request")
        assert mr["occurred_at"].startswith("2025-01-01")
        assert all(call["method"] == "GET" for call in fake_transport.calls)


@pytest.mark.unit
class TestReadEndpoints:
    def test_mr_evidence_review_endpoints(self, world, human_client):
        project, issue, c, b = _setup(world, criteria=CI_CRITERION)
        deliver_gitlab(c, gl_mr(description=f"PH-{issue.id}"))
        deliver_gitlab(c, gl_pipeline(status="success"))
        client = human_client(world.owner)
        base = f"{world.base(project)}/work-items/{issue.id}"
        mrs = client.get(f"{base}/merge-requests").json()["results"]
        assert mrs[0]["head_sha"] == HEAD_A and mrs[0]["commits"][0]["status"] == "claimed"
        assert client.get(f"{base}/evidence").json()["results"][0]["trust"] == "provider_ci"
        review = client.get(f"{base}/review").json()
        assert review["revision"]["intent"] and review["criteria"][0]["state"] == "proven"
        assert any(p["kind"] == "code_review_required" for p in review["open_points"])
        outsider = world.member()
        assert human_client(outsider).get(f"{base}/review").status_code == 404
