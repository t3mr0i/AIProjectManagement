# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.utils import timezone

from plane.db.models import Issue, Project, ProjectMember
from plane.package_flow.models import Claim, DomainEvent, ExecutionApproval, ExecutionRun, PackageProfile

from .conftest import human_client_for
from .pkg_support import Pkg, action


def _native_patch(pkg, body):
    url = f"/api/workspaces/{pkg.world.workspace.slug}/projects/{pkg.project.id}/issues/{pkg.issue.id}/"
    return pkg.human.patch(url, body, format="json")


@pytest.mark.unit
class TestStateIsNotApproval:
    def test_pf05_state_change_is_not_approval(self, world):
        pkg = Pkg(world)
        pkg.make_ready()
        pkg.revision()
        started = world.state(pkg.project, name="In Progress", group="started")
        # 1) ORM save (drag-and-drop path)
        issue = Issue.all_objects.get(id=pkg.issue.id)
        issue.state = started
        issue.is_draft = False
        issue.save()
        assert DomainEvent.objects.filter(event_type="native.state.observed", issue_id=pkg.issue.id).exists()
        # 2) native Plane API
        todo = world.state(pkg.project, name="Todo2", group="unstarted")
        r = _native_patch(pkg, {"state_id": str(todo.id)})
        assert r.status_code in (200, 204), r.content
        r = _native_patch(pkg, {"state_id": str(started.id)})
        assert r.status_code in (200, 204), r.content
        assert Issue.all_objects.get(id=pkg.issue.id).state_id == started.id
        # 3) bulk paths (queryset update / bulk_update bypass signals entirely)
        Issue.all_objects.filter(project=pkg.project).update(state=todo)
        issues = list(Issue.all_objects.filter(project=pkg.project))
        for i in issues:
            i.state = started
        Issue.all_objects.bulk_update(issues, ["state"])

        assert not ExecutionApproval.objects.filter(issue_id=pkg.issue.id).exists()
        assert PackageProfile.objects.get(issue=pkg.issue).approved_revision_id is None
        s = pkg.human.get(f"{pkg.wi}/status").json()
        assert s["lifecycle"] == "draft" and s["native_state_group"] == "started"
        _, rc = pkg.runner()
        r = pkg.claim(rc)
        assert r.status_code == 409 and r.json()["code"] == "REVISION_NOT_APPROVED"
        r = rc.post(f"{pkg.wi}/runs", {"mode": "agent"}, format="json")
        assert r.status_code == 409 and r.json()["code"] == "REVISION_NOT_APPROVED"


@pytest.mark.unit
class TestScopeChange:
    def test_pf06_native_description_change_blocks_run_before_event(self, world):
        pkg = Pkg(world)
        approval = pkg.approve()
        _, rc = pkg.runner()
        claim = pkg.claim(rc).json()
        # Change bypasses signals (no event projected yet).
        Issue.all_objects.filter(id=pkg.issue.id).update(description_html="<p>Also delete all records</p>")
        assert not DomainEvent.objects.filter(event_type="package.scope_changed").exists()
        r = pkg.start(rc, approval["id"], claim["id"])
        assert r.status_code == 409 and r.json()["code"] == "NATIVE_SOURCE_CHANGED"

    def test_pf06_action_gate_rechecks_native_source(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        Issue.all_objects.filter(id=pkg.issue.id).update(name="Export AND delete data")
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        assert r.status_code == 409 and r.json()["code"] == "NATIVE_SOURCE_CHANGED"

    def test_description_change_via_native_api_flags_and_pauses(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = _native_patch(pkg, {"description_html": "<p>New intent: export PDF</p>"})
        assert r.status_code in (200, 204), r.content
        profile = PackageProfile.objects.get(issue=pkg.issue)
        assert "scope_changed" in profile.flags
        assert DomainEvent.objects.filter(event_type="package.scope_changed", issue_id=pkg.issue.id).exists()
        assert DomainEvent.objects.filter(event_type="native.description.changed", issue_id=pkg.issue.id).exists()
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert (run_obj.status, run_obj.pause_reason) == ("waiting", "scope_changed")
        assert "scope_changed" in pkg.human.get(f"{pkg.wi}/status").json()["flags"]
        r = action(rc, run["id"], token, claim["fencing_token"], "create_commit")
        assert r.status_code == 409
        # Old approval cannot be reused for the new intent; re-approval clears the flag.
        pkg.revision()
        rev = pkg.human.get(f"{pkg.wi}/revisions").json()["results"][0]
        r = pkg.human.post(f"{pkg.wi}/execution-approvals", pkg.approval_body(rev["id"]), format="json")
        assert r.status_code == 201, r.content
        assert "scope_changed" not in PackageProfile.objects.get(issue=pkg.issue).flags

    def test_name_change_without_profile_is_untouched(self, world):
        project = world.project()
        issue = world.issue(project)
        issue.name = "renamed"
        issue.description_html = "<p>x</p>"
        issue.save()
        assert not DomainEvent.objects.exists()


@pytest.mark.unit
class TestArchiveAndMembership:
    def test_project_archive_revokes_claims_and_runs(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        r = pkg.human.post(f"/api/workspaces/{world.workspace.slug}/projects/{pkg.project.id}/archive/")
        assert r.status_code == 200, r.content
        assert Claim.objects.get(id=claim["id"]).status == "revoked"
        run_obj = ExecutionRun.objects.get(id=run["id"])
        assert run_obj.status == "cancelled" and run_obj.run_token_hash == ""
        assert DomainEvent.objects.filter(event_type="access.revoked", project_id=pkg.project.id).exists()
        r = action(rc, run["id"], token, claim["fencing_token"], "push_work_branch")
        assert r.status_code == 403
        r = pkg.claim(rc)
        assert r.status_code == 409 and r.json()["code"] == "PROJECT_ARCHIVED"

    def test_project_archive_via_orm_update_still_blocks_actions(self, world):
        pkg = Pkg(world)
        approval, rc, claim, run, token = pkg.running()
        Project.objects.filter(id=pkg.project.id).update(archived_at=timezone.now())
        r = action(rc, run["id"], token, claim["fencing_token"], "push_work_branch")
        assert r.status_code == 409 and r.json()["code"] == "PROJECT_ARCHIVED"

    def test_member_deactivation_revokes_members_claims(self, world):
        pkg = Pkg(world)
        dev = world.member()
        world.add_project_member(pkg.project, dev, 15)
        world.grant(dev, "run.start", pkg.project)
        approval = pkg.approve()
        runner, token = world.runner(dev, name="dev-runner")
        from .conftest import runner_client_for

        rc = runner_client_for(token)
        claim = pkg.claim(rc).json()
        run = pkg.start(rc, approval["id"], claim["id"]).json()
        pm = ProjectMember.objects.get(project=pkg.project, member=dev)
        pm.is_active = False
        pm.save()
        assert Claim.objects.get(id=claim["id"]).status == "revoked"
        assert ExecutionRun.objects.get(id=run["run"]["id"]).status == "cancelled"
        # Owner's own rights are untouched.
        assert human_client_for(world.owner).get(f"{pkg.wi}/profile").status_code == 200

    def test_hooks_never_break_native_saves(self, world, monkeypatch):
        from plane.package_flow.services import execution

        pkg = Pkg(world)
        pkg.approve()

        def boom(*a, **k):
            raise RuntimeError("extension failure")

        monkeypatch.setattr(execution, "pause_runs_for_scope_change", boom)
        issue = Issue.all_objects.get(id=pkg.issue.id)
        issue.description_html = "<p>changed</p>"
        issue.save()  # must not raise
        assert Issue.all_objects.get(id=pkg.issue.id).description_html == "<p>changed</p>"
