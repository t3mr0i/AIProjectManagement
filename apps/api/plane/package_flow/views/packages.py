# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Packages, revisions, readiness, approvals, change records, status (API.md §2, I02)."""

from rest_framework.response import Response

from ..errors import HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import Capability, ChangeRecord, ExecutionApproval, PackageRevision
from ..serializers_packages import (
    approval_contract,
    approval_data,
    change_record_data,
    profile_data,
    revision_contract,
    revision_data,
)
from ..services import packages as svc
from .base import PackageFlowBaseView


def _body(request):
    data = request.data
    if not isinstance(data, dict):
        raise ValidationFailed("JSON object body expected")
    return data


class _IssueView(PackageFlowBaseView):
    """Resolves workspace -> project -> issue; reads need project.read, writes a capability + enabled flag."""

    def read_issue(self, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        self.require(issue.workspace_id, issue.project_id, Capability.PROJECT_READ, enabled=False)
        return issue

    def write_issue(self, slug, project_id, issue_id, capability=Capability.PACKAGE_EDIT):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, capability)
        return issue


class PackageListView(PackageFlowBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        self.require(project.workspace_id, project.id, Capability.PROJECT_READ, enabled=False)
        view = request.query_params.get("view") or "all"
        rows = svc.list_packages(request.user, project.workspace_id, [project.id], view)
        return Response({"results": rows, "count": len(rows), "view": view})


class ProfileView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        return Response(profile_data(profile, issue))

    def post(self, request, slug, project_id, issue_id):
        issue = self.write_issue(slug, project_id, issue_id)
        data = _body(request)

        def run():
            profile, created = svc.activate_profile(
                issue, self.principal, data.get("profile_kind"), data.get("package_type")
            )
            return (201 if created else 200), profile_data(profile, issue)

        return self.idempotent(issue.workspace_id, f"profile:{issue.id}", data, run)

    def patch(self, request, slug, project_id, issue_id):
        issue = self.write_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        profile = svc.update_profile(profile, _body(request), self.principal)
        return Response(profile_data(profile, issue))


class ReadinessView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        return Response(svc.profile_readiness(profile, issue))


class RevisionListView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        current = svc.native_source_hash(issue)
        revisions = PackageRevision.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("-number")
        return Response({"results": [revision_data(r, profile, current) for r in revisions]})

    def post(self, request, slug, project_id, issue_id):
        issue = self.write_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        data = _body(request)

        def run():
            revision, created = svc.create_revision(
                issue,
                profile,
                self.principal,
                decisions=data.get("decisions"),
                artifacts=data.get("artifacts"),
                expected_revision_id=data.get("expected_revision_id"),
            )
            profile.refresh_from_db()
            return (201 if created else 200), revision_data(revision, profile, with_contract=True)

        return self.idempotent(issue.workspace_id, f"revision:{issue.id}", data, run)


def _get_revision(issue, revision_id):
    revision = PackageRevision.objects.filter(id=revision_id, issue_id=issue.id, deleted_at__isnull=True).first()
    if revision is None:
        raise NotFound("Revision not found")
    return revision


class RevisionDetailView(_IssueView):
    def get(self, request, slug, project_id, issue_id, revision_id):
        issue = self.read_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        revision = _get_revision(issue, revision_id)
        return Response(revision_data(revision, profile, with_contract=True))


class RevisionContractView(_IssueView):
    def get(self, request, slug, project_id, issue_id, revision_id):
        issue = self.read_issue(slug, project_id, issue_id)
        return Response(revision_contract(_get_revision(issue, revision_id)))


class RevisionCompareView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        a, b = request.query_params.get("from"), request.query_params.get("to")
        if not a or not b:
            raise ValidationFailed("from and to are required")
        qs = PackageRevision.objects.filter(issue_id=issue.id, deleted_at__isnull=True)

        def pick(ref):
            rev = qs.filter(number=int(ref)).first() if str(ref).isdigit() else None
            if rev is None and not str(ref).isdigit():
                rev = qs.filter(id=ref).first() if svc._is_uuid(ref) else None
            if rev is None:
                raise NotFound("Revision not found")
            return rev

        return Response(svc.compare_revisions(pick(a), pick(b)))


class ApprovalListView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        approvals = ExecutionApproval.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
        return Response({"results": [approval_data(a) for a in approvals]})

    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        # Human check first: an agent never gets further, whatever its payload claims (AC03).
        if not self.principal.is_human:
            raise HumanPrincipalRequired("Execution approvals require an interactive human principal")
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_APPROVE_EXECUTION)
        profile = svc.require_profile(issue)
        data = _body(request)

        def run():
            approval = svc.create_approval(issue, profile, self.principal, data)
            return 201, approval_data(approval)

        return self.idempotent(issue.workspace_id, f"approval:{issue.id}", data, run)


def _get_approval(issue, approval_id):
    approval = ExecutionApproval.objects.filter(id=approval_id, issue_id=issue.id, deleted_at__isnull=True).first()
    if approval is None:
        raise NotFound("Approval not found")
    return approval


class ApprovalContractView(_IssueView):
    def get(self, request, slug, project_id, issue_id, approval_id):
        issue = self.read_issue(slug, project_id, issue_id)
        return Response(approval_contract(_get_approval(issue, approval_id)))


class ApprovalRevokeView(_IssueView):
    def post(self, request, slug, project_id, issue_id, approval_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_APPROVE_EXECUTION, enabled=False)
        approval = _get_approval(issue, approval_id)
        data = _body(request)
        approval = svc.revoke_approval(issue, approval, self.principal, data.get("reason", ""))
        return Response(approval_data(approval))


class ChangeRecordListView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        records = ChangeRecord.objects.filter(issue_id=issue.id, deleted_at__isnull=True)
        return Response({"results": [change_record_data(r) for r in records]})

    def post(self, request, slug, project_id, issue_id):
        issue = self.write_issue(slug, project_id, issue_id)
        profile = svc.require_profile(issue)
        data = _body(request)

        def run():
            return 201, change_record_data(svc.create_change_record(issue, profile, self.principal, data))

        return self.idempotent(issue.workspace_id, f"change-record:{issue.id}", data, run)


class ChangeRecordDetailView(_IssueView):
    def patch(self, request, slug, project_id, issue_id, record_id):
        issue = self.write_issue(slug, project_id, issue_id)
        record = ChangeRecord.objects.filter(id=record_id, issue_id=issue.id, deleted_at__isnull=True).first()
        if record is None:
            raise NotFound("Change record not found")
        return Response(change_record_data(svc.update_change_record(record, _body(request), self.principal)))


class StatusView(_IssueView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.read_issue(slug, project_id, issue_id)
        return Response(svc.compute_package_status(issue))
