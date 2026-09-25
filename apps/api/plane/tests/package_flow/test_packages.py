# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from pathlib import Path

import pytest
from django.utils import timezone

from plane.db.models import Issue
from plane.package_flow.models import PackageProfile, PackageRevision, ReviewApproval
from plane.package_flow.services import packages as svc

from .conftest import World, human_client_for
from .pkg_support import READY_PROFILE, Pkg

SCHEMA_DIR = Path(__file__).resolve().parents[5] / "docs" / "project-hub" / "prd" / "schemas"


@pytest.mark.unit
class TestProfile:
    def test_pf02_profile_idempotent(self, world):
        pkg = Pkg(world)
        headers = {"HTTP_IDEMPOTENCY_KEY": "k-1"}
        r1 = pkg.human.post(f"{pkg.wi}/profile", {}, format="json", **headers)
        r2 = pkg.human.post(f"{pkg.wi}/profile", {}, format="json", **headers)
        r3 = pkg.human.post(f"{pkg.wi}/profile", {}, format="json")
        assert r1.status_code == 201, r1.content
        assert r2.status_code == 201 and r2["Idempotent-Replay"] == "true"
        assert r3.status_code == 200
        assert r1.json()["id"] == r2.json()["id"] == r3.json()["id"]
        assert PackageProfile.objects.filter(issue=pkg.issue).count() == 1
        # No second ticket was created (FR-B02).
        assert Issue.all_objects.filter(project=pkg.project).count() == 1
        assert r1.json()["work_item_id"] == str(pkg.issue.id)

    def test_idempotency_key_mismatch(self, world):
        pkg = Pkg(world)
        pkg.human.post(f"{pkg.wi}/profile", {}, format="json", HTTP_IDEMPOTENCY_KEY="k")
        r = pkg.human.post(f"{pkg.wi}/profile", {"profile_kind": "deep"}, format="json", HTTP_IDEMPOTENCY_KEY="k")
        assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_MISMATCH"

    def test_no_profile_404(self, world):
        pkg = Pkg(world)
        r = pkg.human.get(f"{pkg.wi}/profile")
        assert r.status_code == 404 and r.json()["code"] == "NO_PROFILE"

    def test_disabled_extension_blocks_writes_not_reads(self, world):
        pkg = Pkg(world)
        pkg.activate()
        from plane.package_flow.models import ExtensionActivation

        ExtensionActivation.objects.filter(workspace=world.workspace, project__isnull=True).update(is_enabled=False)
        assert pkg.human.get(f"{pkg.wi}/profile").status_code == 200
        r = pkg.human.patch(f"{pkg.wi}/profile", {"intent": "x"}, format="json")
        assert r.status_code == 403 and r.json()["code"] == "EXTENSION_DISABLED"

    def test_expected_version_conflict(self, world):
        pkg = Pkg(world)
        v = pkg.activate()["version"]
        r = pkg.human.patch(f"{pkg.wi}/profile", {"intent": "a", "expected_version": v}, format="json")
        assert r.status_code == 200 and r.json()["version"] == v + 1
        r = pkg.human.patch(f"{pkg.wi}/profile", {"intent": "b", "expected_version": v}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"

    def test_guest_cannot_edit(self, world):
        pkg = Pkg(world)
        pkg.activate()
        guest = world.member(role=5)
        world.add_project_member(pkg.project, guest, 5)
        c = human_client_for(guest)
        assert c.get(f"{pkg.wi}/profile").status_code == 200
        r = c.patch(f"{pkg.wi}/profile", {"intent": "x"}, format="json")
        assert r.status_code == 403

    def test_criteria_get_stable_ids(self, world):
        pkg = Pkg(world)
        pkg.activate()
        r = pkg.human.patch(f"{pkg.wi}/profile", {"criteria": ["a", {"text": "b"}]}, format="json")
        ids = [c["id"] for c in r.json()["criteria"]]
        assert ids == ["C-1", "C-2"]
        r = pkg.human.patch(
            f"{pkg.wi}/profile", {"criteria": [{"id": "C-2", "text": "b"}, {"text": "c"}]}, format="json"
        )
        assert [c["id"] for c in r.json()["criteria"]] == ["C-2", "C-3"]


@pytest.mark.unit
class TestReadiness:
    def test_ac01_empty_draft_saved_but_not_executable(self, world):
        pkg = Pkg(world)
        pkg.activate()
        r = pkg.human.get(f"{pkg.wi}/readiness")
        assert r.status_code == 200
        body = r.json()
        assert body["ready"] is False
        assert {m["field"] for m in body["missing"]} >= {"intent", "outcome", "criteria", "scope"}
        # Draft persisted.
        assert PackageProfile.objects.filter(issue=pkg.issue).exists()
        # A revision of the empty draft can be saved, but not approved nor run.
        rev = pkg.revision()
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"]), format="json")
        assert r.status_code == 422 and r.json()["code"] == "REVISION_NOT_READY"
        runner, rc = pkg.runner()
        r = pkg.claim(rc)
        assert r.status_code == 409 and r.json()["code"] == "REVISION_NOT_APPROVED"
        r = pkg.human.post(f"{pkg.wi}/runs", {"approval_id": None, "claim_id": None}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "REVISION_NOT_APPROVED"

    def test_light_ready(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        body = pkg.human.get(f"{pkg.wi}/readiness").json()
        assert body["ready"] is True, body
        assert body["policies"] == []

    def test_deep_requires_risk_and_non_goals(self, world):
        pkg = Pkg(world)
        pkg.make_ready(profile_kind="deep")
        body = pkg.human.get(f"{pkg.wi}/readiness").json()
        assert not body["ready"]
        assert {m["field"] for m in body["missing"]} == {"risk.notes", "non_goals"}
        pkg.human.patch(
            f"{pkg.wi}/profile", {"risk": {"notes": "data leak"}, "non_goals": ["no ACL change"]}, format="json"
        )
        assert pkg.human.get(f"{pkg.wi}/readiness").json()["ready"]

    def test_fr_w02_permission_change_shows_security_policy(self, world):
        pkg = Pkg(world)
        pkg.make_ready(scope={"in_scope": ["role editor"], "touches": ["permissions"]})
        body = pkg.human.get(f"{pkg.wi}/readiness").json()
        assert [p["id"] for p in body["policies"]] == ["security_review"]

    def test_fr_w02_small_text_change_needs_no_diagram(self, world):
        pkg = Pkg(world)
        pkg.make_ready(scope={"in_scope": ["fix typo in button label"]})
        body = pkg.human.get(f"{pkg.wi}/readiness").json()
        assert body["ready"] and not any("diagram" in m["field"] for m in body["missing"])


@pytest.mark.unit
class TestRevisions:
    def test_revision_immutable_and_numbered(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        r1 = pkg.revision()
        assert r1["number"] == 1 and len(r1["content_hash"]) == 64
        # Same content -> no duplicate revision (INV-07).
        again = pkg.human.post(f"{pkg.wi}/revisions", {}, format="json")
        assert again.status_code == 200 and again.json()["id"] == r1["id"]
        pkg.human.patch(f"{pkg.wi}/profile", {"outcome": "CSV and XLSX"}, format="json")
        r2 = pkg.revision()
        assert r2["number"] == 2 and r2["content_hash"] != r1["content_hash"]
        rev = PackageRevision.objects.get(id=r1["id"])
        rev.intent = "tamper"
        with pytest.raises(ValueError):
            rev.save()
        prof = pkg.human.get(f"{pkg.wi}/profile").json()
        assert prof["working_revision_id"] == r2["id"]

    def test_content_hash_includes_native_description(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        r1 = pkg.revision()
        Issue.all_objects.filter(id=pkg.issue.id).update(description_html="<p>Changed</p>")
        r2 = pkg.revision()
        assert r2["number"] == 2 and r2["content_hash"] != r1["content_hash"]
        assert (
            r2["source_versions"]["native"]["description_sha256"]
            != r1["source_versions"]["native"]["description_sha256"]
        )
        listing = pkg.human.get(f"{pkg.wi}/revisions").json()["results"]
        stale = {r["number"]: r["is_stale"] for r in listing}
        assert stale == {1: True, 2: False}

    def test_fr_w04_compare(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        pkg.revision()
        pkg.human.patch(
            f"{pkg.wi}/profile",
            {"outcome": "new outcome", "criteria": [{"id": "C-1", "text": "changed"}, {"text": "added"}]},
            format="json",
        )
        pkg.revision()
        r = pkg.human.get(f"{pkg.wi}/revisions/compare?from=1&to=2")
        assert r.status_code == 200, r.content
        body = r.json()
        fields = {c["field"] for c in body["changes"]}
        assert {"outcome", "criteria"} <= fields
        assert [c["id"] for c in body["criteria"]["added"]] == ["C-2"]
        assert [c["id"] for c in body["criteria"]["changed"]] == ["C-1"]
        # Old revision stays readable.
        old = pkg.human.get(f"{pkg.wi}/revisions").json()["results"][-1]
        assert old["outcome"] == READY_PROFILE["outcome"]

    def test_expected_revision_conflict(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        pkg.revision()
        pkg.human.patch(f"{pkg.wi}/profile", {"outcome": "o2"}, format="json")
        r = pkg.human.post(
            f"{pkg.wi}/revisions", {"expected_revision_id": "00000000-0000-4000-8000-000000000000"}, format="json"
        )
        assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"


@pytest.mark.unit
class TestChangeRecords:
    def test_fr_w06_change_records_under_package(self, world):
        pkg = Pkg(world)
        pkg.activate()
        r = pkg.human.post(
            f"{pkg.wi}/change-records", {"kind": "technical_task", "title": "Header order + test"}, format="json"
        )
        assert r.status_code == 201, r.content
        rid = r.json()["id"]
        r = pkg.human.patch(f"{pkg.wi}/change-records/{rid}", {"status": "done"}, format="json")
        assert r.json()["status"] == "done"
        assert len(pkg.human.get(f"{pkg.wi}/change-records").json()["results"]) == 1
        assert Issue.all_objects.filter(project=pkg.project).count() == 1


@pytest.mark.unit
class TestStatusAndList:
    def test_status_draft_then_ready(self, world):
        pkg = Pkg(world)
        pkg.activate()
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert (s["lifecycle"], s["phase"]) == ("draft", "drafts")
        assert s["delivery"] in ("unknown", "not_integrated")
        pkg.approve()
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert (s["lifecycle"], s["phase"]) == ("ready", "ready")

    def test_not_a_package(self, world):
        pkg = Pkg(world)
        s = svc.compute_package_status(pkg.issue)
        assert s["is_package"] is False and s["lifecycle"] is None

    def test_pf11_native_done_without_delivery(self, world):
        pkg = Pkg(world)
        pkg.approve()
        done = world.state(pkg.project, name="Done", group="completed")
        issue = Issue.all_objects.get(id=pkg.issue.id)
        issue.state = done
        issue.save()
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert "native_done_without_delivery" in s["flags"]
        assert s["phase"] == "ready" and s["lifecycle"] != "completed"
        assert s["native_state_group"] == "completed"

    def test_non_code_package_completes_without_git(self, world):

        """AC31 / FR-W10: non-code package completes by accepted deliverable, no fictitious commit."""
        pkg = Pkg(world, package_type="analysis")
        pkg.make_ready()
        rev = pkg.revision()
        ReviewApproval.objects.create(
            issue=pkg.issue,
            kind="outcome",
            revision_id=rev["id"],
            policy_version="pf-policy-1",
            approved_by=world.owner,
        )
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert (s["lifecycle"], s["phase"]) == ("completed", "done")

    def test_code_package_needs_delivery_for_done(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        rev = pkg.revision()
        ReviewApproval.objects.create(
            issue=pkg.issue, kind="outcome", revision_id=rev["id"], policy_version="p", approved_by=world.owner
        )
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert s["phase"] != "done"

    def test_cancelled_native_group(self, world):
        pkg = Pkg(world)
        pkg.activate()
        cancelled = world.state(pkg.project, name="Cancelled", group="cancelled")
        Issue.all_objects.filter(id=pkg.issue.id).update(state=cancelled)
        assert pkg.human.get(f"{pkg.wi}/status").json()["lifecycle"] == "cancelled"

    def test_pf07_draft_filter_respects_rights(self, world):
        pkg = Pkg(world)
        member = world.member()
        world.add_project_member(pkg.project, member, 15)
        own_draft = world.issue(pkg.project, name="My draft", is_draft=True)
        c = human_client_for(member)
        r = c.post(f"{pkg.base}/work-items/{own_draft.id}/profile", {}, format="json")
        assert r.status_code == 201, r.content
        # Private foreign project: not a member.
        other = world.project(name="Private")
        world.enable(other)
        foreign = world.issue(other, name="Foreign")
        PackageProfile.objects.create(issue=foreign)
        # Deleted and archived issues with profiles are never listed.
        deleted = world.issue(pkg.project, name="Deleted")
        PackageProfile.objects.create(issue=deleted)
        Issue.all_objects.filter(id=deleted.id).update(deleted_at=timezone.now())
        archived = world.issue(pkg.project, name="Archived")
        PackageProfile.objects.create(issue=archived)
        Issue.all_objects.filter(id=archived.id).update(archived_at=timezone.now().date())

        rows = c.get(f"{pkg.base}/packages/?view=drafts").json()["results"]
        assert [r["work_item_id"] for r in rows] == [str(own_draft.id)]
        assert rows[0]["is_draft"] is True
        # Foreign project's list and issue are 404 for this member.
        assert c.get(f"{world.base(other)}/packages/").status_code == 404
        assert c.get(f"{world.base(other)}/work-items/{foreign.id}/profile").status_code == 404
        # Cross-project id in own project's URL -> 404.
        assert c.get(f"{pkg.base}/work-items/{foreign.id}/profile").status_code == 404
        # Archived project: list still readable for members but no new claims.
        from plane.db.models import Project

        Project.objects.filter(id=pkg.project.id).update(archived_at=timezone.now())
        world.grant(member, "run.start", pkg.project)
        r = c.post(f"{pkg.base}/work-items/{own_draft.id}/claims", {}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "PROJECT_ARCHIVED"
        assert c.get(f"{pkg.base}/packages/").json()["results"] == []

    def test_list_views_filter_by_phase(self, world):

        """FR-P05: filtered views are projections of the same shared objects, not copies."""
        pkg = Pkg(world)
        pkg.approve()
        other = world.issue(pkg.project, name="Other")
        pkg.human.post(f"{pkg.base}/work-items/{other.id}/profile", {}, format="json")
        ready = pkg.human.get(f"{pkg.base}/packages/?view=ready").json()["results"]
        drafts = pkg.human.get(f"{pkg.base}/packages/?view=drafts").json()["results"]
        assert [r["work_item_id"] for r in ready] == [str(pkg.issue.id)]
        assert [r["work_item_id"] for r in drafts] == [str(other.id)]
        row = ready[0]
        for key in (
            "name",
            "sequence_id",
            "project_identifier",
            "priority",
            "assignee_ids",
            "updated_at",
            "open_questions",
            "lifecycle",
            "phase",
            "delivery",
            "flags",
        ):
            assert key in row
        assert pkg.human.get(f"{pkg.base}/packages/?view=bogus").status_code == 422


@pytest.mark.unit
class TestIsolation:
    def test_fr_b09_two_workspaces_isolated(self, world):
        """FR-P01: projects/workspaces stay isolated for users without membership."""
        pkg_a = Pkg(world)
        pkg_a.activate()
        world_b = World()
        pkg_b = Pkg(world_b)
        pkg_b.activate()
        c = pkg_a.human  # owner of workspace A only
        # Guessing B's ids, via B's URL or smuggled into A's URL: always 404.
        assert c.get(f"{pkg_b.wi}/profile").status_code == 404
        assert c.get(f"{pkg_a.base}/work-items/{pkg_b.issue.id}/profile").status_code == 404
        assert c.post(f"{pkg_a.base}/work-items/{pkg_b.issue.id}/profile", {}, format="json").status_code == 404
        assert c.get(f"{pkg_b.base}/packages/").status_code == 404
        assert c.get(f"{world_b.ws_base()}/capabilities/me/").status_code == 404
        # A runner of workspace A cannot reach workspace B.
        _, rc = pkg_a.runner()
        assert rc.get(f"{pkg_b.wi}/profile").status_code == 404

    def test_foreign_binding_cannot_be_injected(self, world):
        pkg = Pkg(world)
        other = world.project()
        from .pkg_support import make_binding

        foreign_binding = make_binding(world, other)
        pkg.make_ready()
        rev = pkg.revision()
        body = pkg.approval_body(rev["id"])
        body["repository_scope"][0]["binding_id"] = str(foreign_binding.id)
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", body, format="json")
        assert r.status_code == 422 and r.json()["code"] == "BINDING_NOT_FOUND"


@pytest.mark.unit
class TestContracts:
    def _schema(self, name):
        return json.loads((SCHEMA_DIR / name).read_text())

    def test_revision_and_approval_contracts_match_schemas(self, world):
        jsonschema = pytest.importorskip("jsonschema")
        pkg = Pkg(world)
        pkg.make_ready(
            scope={
                "in_scope": ["export"],
                "repositories": [
                    {
                        "binding_id": str(pkg.binding.id),
                        "base_commit": "b" * 40,
                        "target_branch": "main",
                        "allowed_paths": ["src/**"],
                    }
                ],
            },
            non_goals=["no ACL change"],
        )
        rev = pkg.revision()
        detail = pkg.human.get(f"{pkg.wi}/revisions/{rev['id']}").json()
        checker = jsonschema.FormatChecker()
        jsonschema.validate(detail["contract"], self._schema("package-revision.schema.json"), format_checker=checker)
        assert detail["contract"]["repositories"][0]["bindingId"] == str(pkg.binding.id)
        runner, _ = pkg.runner()
        r = pkg.human.post(
            f"{pkg.wi}/execution-approvals",
            pkg.approval_body(rev["id"], runner_profile_id=str(runner.id)),
            format="json",
        )
        assert r.status_code == 201, r.content
        contract = r.json()["contract"]
        jsonschema.validate(contract, self._schema("execution-authorization.schema.json"), format_checker=checker)
        via_endpoint = pkg.human.get(f"{pkg.wi}/execution-approvals/{r.json()['id']}/contract").json()
        assert via_endpoint == contract
        rev_contract = pkg.human.get(f"{pkg.wi}/revisions/{rev['id']}/contract").json()
        assert rev_contract == detail["contract"]
