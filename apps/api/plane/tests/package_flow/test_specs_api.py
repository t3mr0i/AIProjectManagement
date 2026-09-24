# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""OpenSpec export/import API (FR-W08, FR-W09, FR-G02, AC07, AC08, INV-02)."""

import pytest

from plane.package_flow.models import (
    DomainEvent,
    ExecutionApproval,
    ExecutionRun,
    IntegrationConnection,
    PackageProfile,
    PackageRevision,
    RepositoryBinding,
    SpecSyncState,
)
from plane.tests.package_flow.test_openspec import PROPOSAL, SPEC, TASKS


def _setup(world):
    project = world.project()
    world.enable(project)
    issue = world.issue(project, name="Two factor auth")
    profile = PackageProfile.objects.create(issue=issue, intent="", outcome="")
    conn = IntegrationConnection.objects.create(
        workspace=world.workspace, provider="gitlab", instance_url="https://git.example.test"
    )
    binding = RepositoryBinding.objects.create(
        workspace=world.workspace,
        project=project,
        connection=conn,
        external_id="42",
        path_with_namespace="team/app",
        specs_branch="specs",
    )
    return project, issue, profile, binding


def _files(**overrides):
    files = {"proposal.md": PROPOSAL, "tasks.md": TASKS, "specs/auth/spec.md": SPEC}
    files.update(overrides)
    return files


def _url(world, project, issue, action=""):
    return f"{world.base(project)}/work-items/{issue.id}/spec" + (f"/{action}" if action else "")


@pytest.mark.unit
class TestSpecApi:
    def _import(self, client, world, project, issue, binding, files, commit):
        return client.post(
            _url(world, project, issue, "import"),
            {"files": files, "commit": commit, "repository_binding_id": str(binding.id)},
            format="json",
        )

    def test_import_then_export_is_byte_identical(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        client = human_client(world.owner)
        r = self._import(client, world, project, issue, binding, _files(), "c1")
        assert r.status_code == 200, r.content
        assert r.json()["revision_created"] is True
        profile.refresh_from_db()
        assert profile.intent.startswith("Accounts are compromised")
        assert [c["id"] for c in profile.criteria][:2] == ["C-1", "C-2"]
        revision = PackageRevision.objects.get(id=r.json()["revision_id"])
        assert revision.origin == "openspec_import"

        r = client.post(
            _url(world, project, issue, "export"),
            {"repository_binding_id": str(binding.id), "expected_base_commit": "c1"},
            format="json",
        )
        assert r.status_code == 200, r.content
        body = r.json()
        prefix = body["spec_path"] + "/"
        for name, text in _files().items():
            assert body["files"][prefix + name] == text
        assert body["manifest"]["workItemId"] == str(issue.id)
        assert body["force_push"] is False

        # Re-import of unchanged content creates no new revision.
        r = self._import(client, world, project, issue, binding, _files(), "c2")
        assert r.status_code == 200, r.content
        assert r.json()["revision_created"] is False

    def test_export_with_moved_head_is_rejected(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        client = human_client(world.owner)
        assert self._import(client, world, project, issue, binding, _files(), "c1").status_code == 200
        r = client.post(
            _url(world, project, issue, "export"),
            {"repository_binding_id": str(binding.id), "expected_base_commit": "old-head"},
            format="json",
        )
        assert r.status_code == 409
        assert r.json()["code"] == "SPEC_BASE_MOVED"

    def test_ac07_ui_and_ide_edit_same_section_conflict(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        client = human_client(world.owner)
        assert self._import(client, world, project, issue, binding, _files(), "c1").status_code == 200
        profile.refresh_from_db()
        profile.intent = "UI edit of why."
        profile.save()
        before = profile.working_revision_id
        ide = _files(
            **{"proposal.md": PROPOSAL.replace("Accounts are compromised through reused passwords.", "IDE edit.")}
        )
        r = self._import(client, world, project, issue, binding, ide, "c2")
        assert r.status_code == 409, r.content
        assert r.json()["code"] == "SPEC_CONFLICT"
        conflict = r.json()["detail"]["conflicts"][0]
        assert conflict["block_id"] == "proposal.md#why"
        assert "UI edit of why." in conflict["platform"] and "IDE edit." in conflict["git"]
        state = SpecSyncState.objects.get(issue=issue)
        assert state.state == "conflict"
        profile.refresh_from_db()
        # Neither side was silently overwritten.
        assert profile.intent == "UI edit of why."
        assert profile.working_revision_id == before
        # Export is blocked while the conflict is open.
        r = client.post(
            _url(world, project, issue, "export"),
            {"repository_binding_id": str(binding.id), "expected_base_commit": "c1"},
            format="json",
        )
        assert r.status_code == 409 and r.json()["code"] == "SPEC_CONFLICT"
        # Explicit resolution merges.
        r = client.post(
            _url(world, project, issue, "import"),
            {
                "files": ide,
                "commit": "c2",
                "repository_binding_id": str(binding.id),
                "resolutions": {"proposal.md#why": "platform"},
            },
            format="json",
        )
        assert r.status_code == 200, r.content
        profile.refresh_from_db()
        assert profile.intent == "UI edit of why."

    def test_non_overlapping_edits_merge(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        client = human_client(world.owner)
        assert self._import(client, world, project, issue, binding, _files(), "c1").status_code == 200
        profile.refresh_from_db()
        profile.intent = "UI edit of why."
        profile.save()
        ide = _files(**{"tasks.md": TASKS + "- [ ] 1.3 Write docs\n"})
        r = self._import(client, world, project, issue, binding, ide, "c2")
        assert r.status_code == 200, r.content
        profile.refresh_from_db()
        assert profile.intent == "UI edit of why."
        assert "1.3 Write docs" in profile.scope["tasks"][0]["text"]
        state = SpecSyncState.objects.get(issue=issue)
        assert state.base_commit == "c2" and state.state == "ahead"

    def test_ac08_lossy_export_blocked_via_api(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        client = human_client(world.owner)
        assert self._import(client, world, project, issue, binding, _files(), "c1").status_code == 200
        profile.refresh_from_db()
        criteria = list(profile.criteria)
        criteria[1] = {**criteria[1], "text": "The system SHALL issue twelve recovery codes."}
        profile.criteria = criteria
        profile.save()
        r = client.post(
            _url(world, project, issue, "export"),
            {"repository_binding_id": str(binding.id), "expected_base_commit": "c1"},
            format="json",
        )
        assert r.status_code == 422, r.content
        assert r.json()["code"] == "SPEC_EXPORT_LOSSY"
        assert r.json()["detail"]["blocks"][0]["block_id"] == "specs/auth/spec.md#req:C-2"

    def test_fr_w09_import_does_not_replace_approved_revision(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        approved = PackageRevision.objects.create(
            issue=issue, number=1, title=issue.name, intent="approved intent", content_hash="x" * 64
        )
        profile.approved_revision = approved
        profile.working_revision = approved
        profile.save()
        client = human_client(world.owner)
        r = self._import(client, world, project, issue, binding, _files(), "c1")
        assert r.status_code == 200, r.content
        profile.refresh_from_db()
        assert profile.approved_revision_id == approved.id
        assert profile.working_revision_id != approved.id
        new = profile.working_revision
        assert new.number == 2 and new.origin == "openspec_import" and new.based_on_id == approved.id
        approved.refresh_from_db()
        assert approved.intent == "approved intent"

    def test_inv02_spec_export_is_not_execution(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        profile.intent = "Why from UI"
        profile.criteria = [{"id": "C-1", "text": "It SHALL work."}]
        profile.save()
        client = human_client(world.owner)
        r = client.post(
            _url(world, project, issue, "export"),
            {"repository_binding_id": str(binding.id), "expected_base_commit": ""},
            format="json",
        )
        assert r.status_code == 200, r.content
        assert r.json()["execution_approved"] is False
        assert ExecutionApproval.objects.filter(issue=issue).count() == 0
        assert ExecutionRun.objects.filter(issue=issue).count() == 0
        assert DomainEvent.objects.filter(issue=issue, event_type="spec.exported").count() == 1
        assert not DomainEvent.objects.filter(issue=issue, event_type="package.execution.approved").exists()

    def test_manifest_for_other_package_rejected(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        other = world.issue(project, name="Other")
        manifest = '{"workItemId": "%s"}\n' % other.id
        r = self._import(
            human_client(world.owner), world, project, issue, binding, _files(**{"project-hub.json": manifest}), "c1"
        )
        assert r.status_code == 422 and r.json()["code"] == "SPEC_MANIFEST_MISMATCH"

    def test_guest_cannot_import_and_state_readable(self, world, human_client):
        project, issue, profile, binding = _setup(world)
        guest = world.member(role=5)
        world.add_project_member(project, guest, role=5)
        r = self._import(human_client(guest), world, project, issue, binding, _files(), "c1")
        assert r.status_code == 403
        r = human_client(guest).get(_url(world, project, issue))
        assert r.status_code == 200 and r.json()["states"] == []
