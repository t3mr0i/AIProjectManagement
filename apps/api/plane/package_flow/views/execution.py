# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Runners, claims, runs, manifest, run events and the controlled action gate (API.md §3, I06/I07)."""

from rest_framework.response import Response

from ..capabilities import require_extension_enabled, workspace_role
from ..errors import NotFound, PermissionDenied, ValidationFailed
from ..models import Capability, ExecutionRun, RunnerProfile
from ..serializers_packages import claim_data, run_data, runner_data
from ..services import execution as svc
from .base import PackageFlowBaseView

ADMIN_ROLE, MEMBER_ROLE = 20, 15


def _body(request):
    data = request.data
    if not isinstance(data, dict):
        raise ValidationFailed("JSON object body expected")
    return data


class RunnerListView(PackageFlowBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        qs = RunnerProfile.objects.filter(workspace=workspace, deleted_at__isnull=True)
        if workspace_role(request.user, workspace.id) != ADMIN_ROLE:
            qs = qs.filter(owner=request.user)
        return Response({"results": [runner_data(r) for r in qs.order_by("-created_at")]})

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        role = workspace_role(request.user, workspace.id)
        if role is None or role < MEMBER_ROLE:
            raise PermissionDenied("Guests cannot register runners")
        require_extension_enabled(workspace.id)
        data = _body(request)

        def run():
            runner, token = svc.register_runner(
                workspace, self.principal, data.get("name"), data.get("kind") or "local"
            )
            return 201, runner_data(runner, token=token)

        # Token must never be replayed from storage: no idempotency record for this endpoint.
        code, body = run()
        return Response(body, status=code)


class RunnerDetailView(PackageFlowBaseView):
    def delete(self, request, slug, runner_id):
        workspace = self.get_workspace(slug)
        runner = RunnerProfile.objects.filter(id=runner_id, workspace=workspace, deleted_at__isnull=True).first()
        if runner is None:
            raise NotFound("Runner not found")
        if runner.owner_id != request.user.id and workspace_role(request.user, workspace.id) != ADMIN_ROLE:
            raise NotFound("Runner not found")
        svc.deactivate_runner(runner, self.principal)
        return Response(status=204)


class ClaimCreateView(PackageFlowBaseView):
    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.RUN_START)
        data = _body(request)

        def run():
            return 201, claim_data(svc.create_claim(issue, self.principal, data))

        return self.idempotent(issue.workspace_id, f"claim:{issue.id}", data, run)


class ClaimHeartbeatView(PackageFlowBaseView):
    def post(self, request, claim_id):
        data = _body(request)
        claim = svc.get_claim_for(self.principal, claim_id)
        claim = svc.heartbeat_claim(claim, self.principal, data.get("fencing_token"), data.get("lease_seconds"))
        return Response(claim_data(claim))


class ClaimReleaseView(PackageFlowBaseView):
    def post(self, request, claim_id):
        data = _body(request)
        claim = svc.get_claim_for(self.principal, claim_id)
        claim = svc.release_claim(claim, self.principal, data.get("fencing_token"))
        return Response(claim_data(claim))


class RunListView(PackageFlowBaseView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        self.require(issue.workspace_id, issue.project_id, Capability.PROJECT_READ, enabled=False)
        runs = ExecutionRun.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("-created_at")
        return Response({"results": [run_data(r) for r in runs]})

    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require(issue.workspace_id, issue.project_id, Capability.RUN_START)
        data = _body(request)
        run, token = svc.start_run(issue, self.principal, data)
        # The run token is shown once and never stored in an idempotency record.
        return Response({"run": run_data(run), "run_token": token, "manifest": run.manifest}, status=201)


class _RunTokenView(PackageFlowBaseView):
    def get_run(self, run_id):
        run = svc.get_run_for_token(self.principal, run_id, self.request.headers.get("X-Run-Token"))
        return run


class RunManifestView(_RunTokenView):
    def get(self, request, run_id):
        run = self.get_run(run_id)
        svc._require_run_start(self.principal, run)
        return Response({"manifest": run.manifest, "manifest_hash": run.manifest_hash})


class RunEventView(_RunTokenView):
    def post(self, request, run_id):
        run = self.get_run(run_id)
        run = svc.record_run_event(run, self.principal, _body(request))
        return Response(run_data(run))


class RunActionView(_RunTokenView):
    def post(self, request, run_id):
        run = self.get_run(run_id)
        return Response(svc.perform_action(run, self.principal, _body(request)))


class RunEvidenceView(_RunTokenView):
    def post(self, request, run_id):
        run = self.get_run(run_id)
        evidence = svc.record_evidence(run, self.principal, _body(request))
        return Response(
            {"id": str(evidence.id), "trust": evidence.trust, "result": evidence.result, "run_id": str(run.id)},
            status=201,
        )


class RunCancelView(PackageFlowBaseView):
    def post(self, request, slug, project_id, run_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        self.require(project.workspace_id, project.id, Capability.RUN_CANCEL, enabled=False)
        run = ExecutionRun.objects.filter(id=run_id, project_id=project.id, deleted_at__isnull=True).first()
        if run is None:
            raise NotFound("Run not found")
        data = request.data if isinstance(request.data, dict) else {}
        run = svc.cancel_run(run, self.principal, str(data.get("reason") or "cancelled"))
        return Response(run_data(run), status=202)
