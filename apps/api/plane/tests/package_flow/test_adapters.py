# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Adapter contract tests: honest declarations, webhook auth, normalization (FR-I02, PRD §12)."""

import base64
import json

import pytest

from plane.package_flow.adapters import ADAPTERS, get_adapter
from plane.package_flow.adapters.base import (
    CAPABILITIES,
    LEVELS,
    UNSUPPORTED,
    ProviderContext,
    RepoRef,
    fallback_event_id,
    parse_references,
)

from .integration_helpers import HEAD_A, SECRET, FakeTransport, gl_merged, gl_mr, gl_pipeline, hub_signature


@pytest.mark.unit
class TestDeclarations:
    @pytest.mark.parametrize("provider", sorted(ADAPTERS))
    def test_every_adapter_declares_all_13_capabilities(self, provider):
        decl = get_adapter(provider, transport=FakeTransport()).declare()
        assert set(decl.capabilities) == set(CAPABILITIES) and len(CAPABILITIES) == 13
        assert all(level in LEVELS for level in decl.capabilities.values())
        data = decl.as_dict()
        for key in ("editions", "instance_types", "min_requirements", "auth_methods", "rate_limits", "event_types"):
            assert data[key], f"{provider} must declare {key}"
        assert data["field_mapping"]
        assert data["webhook_auth"]

    def test_generic_git_is_honest(self):
        decl = get_adapter("generic_git").declare()
        for cap in ("read_checks", "read_deployments", "verify_human_approval", "request_merge", "read_merge_requests"):
            assert decl.level(cap) == UNSUPPORTED

    def test_gitlab_free_edition_cannot_verify_approvals_fully(self):
        adapter = get_adapter("gitlab")
        assert adapter.declare(edition="free").level("verify_human_approval") == "partial"
        assert adapter.declare(edition="premium").level("verify_human_approval") == "supported"

    def test_trackers_declare_no_git_capabilities(self):
        for provider in ("jira", "linear"):
            decl = get_adapter(provider).declare()
            assert decl.level("request_merge") == UNSUPPORTED
            assert decl.level("read_merge_requests") == UNSUPPORTED


@pytest.mark.unit
class TestWebhookVerification:
    def test_gitlab_token_constant_time(self):
        a = get_adapter("gitlab")
        assert a.verify_webhook({"X-Gitlab-Token": SECRET}, b"{}", SECRET)
        assert not a.verify_webhook({"X-Gitlab-Token": "nope"}, b"{}", SECRET)
        assert not a.verify_webhook({}, b"{}", SECRET)
        assert not a.verify_webhook({"X-Gitlab-Token": ""}, b"{}", "")

    def test_github_hmac(self):
        body = b'{"a":1}'
        a = get_adapter("github")
        assert a.verify_webhook({"X-Hub-Signature-256": hub_signature(SECRET, body)}, body, SECRET)
        assert not a.verify_webhook({"X-Hub-Signature-256": hub_signature(SECRET, b"other")}, body, SECRET)
        assert not a.verify_webhook({"X-Hub-Signature-256": hub_signature(SECRET, body)[7:]}, body, SECRET)

    def test_linear_and_jira_hmac(self):
        body = b'{"type":"Issue"}'
        sig = hub_signature(SECRET, body, prefix="")
        assert get_adapter("linear").verify_webhook({"Linear-Signature": sig}, body, SECRET)
        assert not get_adapter("linear").verify_webhook({"Linear-Signature": sig}, body + b" ", SECRET)
        assert get_adapter("jira").verify_webhook({"X-Hub-Signature": "sha256=" + sig}, body, SECRET)
        assert not get_adapter("jira").verify_webhook({}, body, SECRET)

    def test_azure_basic_auth(self):
        secret = "hook-user:" + "p" * 20
        header = "Basic " + base64.b64encode(secret.encode()).decode()
        a = get_adapter("azure_devops")
        assert a.verify_webhook({"Authorization": header}, b"{}", secret)
        assert not a.verify_webhook({"Authorization": "Basic Zm9vOmJhcg=="}, b"{}", secret)

    def test_generic_git_signature(self):
        body = b'{"ref":"refs/heads/main","after":"x"}'
        a = get_adapter("generic_git")
        assert a.verify_webhook({"X-Signature-256": hub_signature(SECRET, body)}, body, SECRET)
        assert not a.verify_webhook({"X-Signature-256": "sha256=00"}, body, SECRET)


@pytest.mark.unit
class TestNormalization:
    def test_references(self):
        uid = "0f8fad5b-d9cb-469f-a165-70867728950e"
        refs = parse_references(f"feature/abc-12-export PH-{uid}", f"workItemId: {uid}", "Fixes XYZ-3")
        assert {"type": "uuid", "value": uid} in refs
        assert {"type": "sequence", "identifier": "ABC", "sequence": 12} in refs
        assert {"type": "sequence", "identifier": "XYZ", "sequence": 3} in refs
        assert len([r for r in refs if r["type"] == "uuid"]) == 1

    def test_gitlab_mr_and_delivery_ids(self):
        a = get_adapter("gitlab")
        payload = gl_mr(description="Implements PH-0f8fad5b-d9cb-469f-a165-70867728950e")
        [ev] = a.normalize({"X-Gitlab-Event-UUID": "u-1"}, payload)
        assert ev.kind == "mr.opened" and ev.mr_external_id == "5" and ev.head_sha == HEAD_A
        assert ev.external_event_id == "gitlab:u-1"
        assert any(r["type"] == "uuid" for r in ev.correlation)
        # Deterministic fallback: same object state -> same id; later update -> new id.
        [x] = a.normalize({}, payload)
        [y] = a.normalize({}, payload)
        assert x.external_event_id == y.external_event_id and x.external_event_id.startswith("h:")
        later = gl_mr(updated_at="2026-09-01T10:05:00Z")
        [z] = a.normalize({}, later)
        assert z.external_event_id != x.external_event_id

    def test_gitlab_squash_and_fast_forward(self):
        a = get_adapter("gitlab")
        [sq] = a.normalize({}, gl_merged(merge_sha=None, squash=True, squash_commit_sha="e" * 40))
        assert sq.kind == "mr.merged" and sq.merged_commit_sha == "e" * 40 and sq.merge_method == "squash"
        [ff] = a.normalize({}, gl_merged(merge_sha=None))
        assert ff.merge_method == "fast_forward" and ff.merged_commit_sha == HEAD_A

    def test_gitlab_pipeline(self):
        [ev] = get_adapter("gitlab").normalize({}, gl_pipeline(status="failed"))
        assert ev.kind == "check" and ev.check_status == "failed" and ev.check_id == "pipeline:77"

    def test_github_pr_check_and_rollback(self):
        a = get_adapter("github")
        pr = {
            "action": "closed",
            "repository": {"id": 55, "full_name": "org/app"},
            "pull_request": {
                "number": 3,
                "title": "Export",
                "body": "",
                "merged": True,
                "merge_commit_sha": "f" * 40,
                "merged_at": "2026-09-01T12:00:00Z",
                "head": {"ref": "feature/abc-1", "sha": HEAD_A},
                "base": {"ref": "main", "sha": "0" * 40, "repo": {"id": 55}},
            },
        }
        [ev] = a.normalize({"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "d-1"}, pr)
        assert ev.kind == "mr.merged" and ev.merged_commit_sha == "f" * 40 and ev.external_event_id == "github:d-1"
        check = {
            "repository": {"id": 55, "full_name": "org/app"},
            "check_run": {
                "id": 1,
                "name": "unit tests",
                "status": "completed",
                "conclusion": "success",
                "head_sha": HEAD_A,
                "completed_at": "2026-09-01T11:00:00Z",
                "pull_requests": [{"number": 3}],
            },
        }
        [c] = a.normalize({"X-GitHub-Event": "check_run"}, check)
        assert c.check_status == "passed" and c.check_kind == "test" and c.mr_external_id == "3"
        dep = {
            "repository": {"id": 55},
            "deployment": {"id": 8, "sha": "1" * 40, "environment": "production", "task": "deploy:rollback"},
            "deployment_status": {
                "state": "success",
                "environment": "production",
                "updated_at": "2026-09-03T00:00:00Z",
            },
        }
        [d] = a.normalize({"X-GitHub-Event": "deployment_status"}, dep)
        assert d.kind == "deployment" and d.is_rollback and d.deployment_status == "success"

    def test_jira_priority_changelog(self):
        payload = {
            "webhookEvent": "jira:issue_updated",
            "timestamp": 1788000000000,
            "issue": {
                "id": "10001",
                "key": "OPS-1",
                "fields": {"priority": {"name": "Highest"}, "summary": "T", "status": {"name": "In Progress"}},
            },
            "changelog": {"id": "5", "items": [{"field": "priority", "toString": "Highest"}]},
        }
        [ev] = get_adapter("jira").normalize({"X-Atlassian-Webhook-Identifier": "j-1"}, payload)
        assert ev.kind == "issue.updated" and ev.fields == {"priority": "urgent"} and ev.external_issue_key == "OPS-1"

    def test_linear_and_azure_workitems(self):
        lin = {
            "action": "update",
            "type": "Issue",
            "data": {"id": "L1", "identifier": "ENG-4", "priority": 2, "updatedAt": "2026-09-01T10:00:00Z"},
            "updatedFrom": {"priority": 3},
        }
        [ev] = get_adapter("linear").normalize({"Linear-Delivery": "x"}, lin)
        assert ev.fields == {"priority": "high"}
        az = {
            "id": "evt-1",
            "eventType": "workitem.updated",
            "createdDate": "2026-09-01T10:00:00Z",
            "resource": {
                "workItemId": 42,
                "fields": {"Microsoft.VSTS.Common.Priority": {"oldValue": 3, "newValue": 1}},
            },
        }
        [w] = get_adapter("azure_devops").normalize({}, az)
        assert (
            w.fields == {"priority": "urgent"} and w.external_issue_id == "42" and w.external_event_id == "azure:evt-1"
        )

    def test_azure_pr_completed_squash(self):
        az = {
            "id": "evt-2",
            "eventType": "git.pullrequest.merged",
            "resource": {
                "pullRequestId": 9,
                "title": "t",
                "status": "completed",
                "sourceRefName": "refs/heads/feat/abc-2",
                "targetRefName": "refs/heads/main",
                "lastMergeSourceCommit": {"commitId": HEAD_A},
                "lastMergeCommit": {"commitId": "9" * 40},
                "completionOptions": {"mergeStrategy": "squash"},
                "repository": {"id": "repo-guid", "name": "app", "project": {"name": "P"}},
            },
        }
        [ev] = get_adapter("azure_devops").normalize({}, az)
        assert ev.kind == "mr.merged" and ev.merge_method == "squash" and ev.merged_commit_sha == "9" * 40
        assert ev.source_branch == "feat/abc-2" and ev.repository_path == "P/app"

    def test_fallback_hash_is_documented_and_deterministic(self):
        assert fallback_event_id("x", "mr", 1, "t", "a") == fallback_event_id("x", "mr", 1, "t", "a")
        assert fallback_event_id("x", "mr", 1, "t", "a") != fallback_event_id("x", "mr", 1, "t2", "a")


@pytest.mark.unit
class TestOutboundViaInjectedTransport:
    def test_gitlab_calls_go_through_transport(self):
        t = FakeTransport()
        t.add("GET", "/merge_requests/5", body={"sha": HEAD_A, "state": "opened", "diff_refs": {"start_sha": "0" * 40}})
        t.add("PUT", "/merge_requests/5/merge", body={"state": "merged", "merge_commit_sha": "d" * 40})
        t.add("GET", "/protected_branches/main", body={"name": "main"})
        a = get_adapter("gitlab", transport=t)
        ctx = ProviderContext("https://gitlab.example.test", token="tok")
        repo = RepoRef("101", "grp/app")
        assert a.fetch_merge_request(ctx, repo, "5")["head_sha"] == HEAD_A
        assert a.fetch_branch_protection(ctx, repo, "main")["protected"] is True
        result = a.merge(ctx, repo, "5", sha=HEAD_A)
        assert result["accepted"] and result["merged_commit_sha"] == "d" * 40
        put = t.called("PUT")[0]
        assert put["json"]["sha"] == HEAD_A
        assert put["url"].startswith("https://gitlab.example.test/api/v4/projects/101/")
        assert put["headers"]["PRIVATE-TOKEN"] == "tok"

    def test_github_head_mismatch_maps_409(self):
        t = FakeTransport().add("PUT", "/pulls/3/merge", status=409, body={"message": "Head branch was modified"})
        res = get_adapter("github", transport=t).merge(
            ProviderContext("https://github.com"), RepoRef("55", "org/app"), "3", sha=HEAD_A
        )
        assert res["head_mismatch"] and not res["accepted"]
        assert t.calls[0]["url"] == "https://api.github.com/repos/org/app/pulls/3/merge"

    def test_normalize_is_pure(self):
        # normalization never performs HTTP
        t = FakeTransport()
        get_adapter("gitlab", transport=t).normalize({}, json.loads(json.dumps(gl_mr())))
        assert t.calls == []


@pytest.mark.unit
class TestTrackerWriteBack:
    def test_linear_and_azure_bounded_updates(self):
        t = FakeTransport()
        t.add("POST", "api.linear.app/graphql", body={"data": {"issueUpdate": {"success": True}}})
        t.add("PATCH", "/_apis/wit/workitems/42", body={"id": 42})
        res = get_adapter("linear", transport=t).update_work_item(
            ProviderContext("https://linear.app", token="lin_api_x"), "L1", {"title": "T", "priority": "urgent"}
        )
        assert res["ok"] and t.calls[0]["json"]["variables"] == {"id": "L1", "input": {"title": "T", "priority": 1}}
        res = get_adapter("azure_devops", transport=t).update_work_item(
            ProviderContext("https://dev.azure.com/org", token="pat"), "42", {"priority": "low"}
        )
        assert res["ok"]
        patch = t.called("PATCH")[0]
        assert patch["json"] == [{"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": 4}]
        assert patch["headers"]["Content-Type"] == "application/json-patch+json"

    def test_none_priority_is_not_pushed(self):
        t = FakeTransport()
        res = get_adapter("jira", transport=t).update_work_item(
            ProviderContext("https://a.atlassian.net"), "1", {"priority": "none"}
        )
        assert res["pushed"] == {} and t.calls == []

    def test_git_only_adapters_refuse_writes(self):
        from plane.package_flow.adapters.base import CapabilityUnsupported

        with pytest.raises(CapabilityUnsupported):
            get_adapter("generic_git", transport=FakeTransport()).update_work_item(
                ProviderContext("https://git.example.test"), "1", {"title": "x"}
            )
