# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Collaboration, AI, knowledge endpoints (API.md §5; I08/I09/I13).

All scope resolution goes through native rows (``PackageFlowBaseView``);
reads of history stay available when the extension is disabled, writes need
the extension enabled. DMs are only visible to their human participants —
workspace admins and agent principals get 404 (PRD §5.2).
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from ..ai import clarify as clarify_ai
from ..ai.context import assemble_context, conversation_audience, projects_audience
from ..ai.provider import get_provider
from ..capabilities import accessible_project_ids, require_extension_enabled
from ..errors import Conflict, HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import AIProposal, Capability, Conversation, MessageVersion, NotificationItem, PackageProfile
from ..services import activity as activity_service
from ..services import conversations as conv_service
from ..services import decisions as decision_service
from ..services import knowledge as knowledge_service
from ..services import notifications as notification_service
from ..services import retention as retention_service
from ..services import search as search_service
from .base import PackageFlowBaseView


def _bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")


class CollaborationBaseView(PackageFlowBaseView):
    def require_human(self):
        if not self.principal.is_human:
            raise HumanPrincipalRequired("This action requires a verified human principal")

    def conversation(self, workspace, conversation_id):
        conv = conv_service.get_readable(self.request.user, workspace, conversation_id)
        if conv.kind == Conversation.Kind.DIRECT and not self.principal.is_human:
            # Agents never read private DMs.
            raise NotFound("Conversation not found")
        return conv

    def require_enabled_for(self, conv):
        require_extension_enabled(conv.workspace_id, conv.project_id)


# -- conversations --------------------------------------------------------------------


class ConversationListEndpoint(CollaborationBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        convs = conv_service.list_for(request.user, workspace)
        if not self.principal.is_human:
            convs = [c for c in convs if c.kind != Conversation.Kind.DIRECT]
        kind = request.query_params.get("kind")
        project_id = request.query_params.get("project_id")
        if kind:
            convs = [c for c in convs if c.kind == kind]
        if project_id:
            convs = [c for c in convs if str(c.project_id) == project_id]
        return Response([conv_service.serialize_conversation(c, request.user) for c in convs])

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        data = request.data
        kind = data.get("kind")
        project_id = data.get("project_id")
        require_extension_enabled(workspace.id, project_id if kind != Conversation.Kind.DIRECT else None)
        conv, created = conv_service.create(
            request.user,
            workspace,
            kind=kind,
            project_id=project_id,
            issue_id=data.get("issue_id"),
            participant_ids=data.get("participant_ids") or [],
            title=data.get("title") or "",
        )
        return Response(
            conv_service.serialize_conversation(conv, request.user),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationDetailEndpoint(CollaborationBaseView):
    def get(self, request, slug, conversation_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        return Response(conv_service.serialize_conversation(conv, request.user))


class PackageThreadEndpoint(CollaborationBaseView):
    """The package's single thread, reachable from the package (FR-C01)."""

    def get(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id, allow_archived=True)
        existing = Conversation.objects.filter(issue=issue, kind=Conversation.Kind.PACKAGE).first()
        if existing is None:
            if not self.principal.is_human:
                raise NotFound("Thread not found")
            require_extension_enabled(issue.workspace_id, issue.project_id)
            existing, _ = conv_service.package_thread(issue)
        return Response(conv_service.serialize_conversation(existing, request.user))


class MessageListEndpoint(CollaborationBaseView):
    def get(self, request, slug, conversation_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        # Reading does not mark anything read (J08).
        msgs = conv_service.list_messages(conv, after=request.query_params.get("after"))
        return Response([conv_service.serialize_message(m) for m in msgs])

    def post(self, request, slug, conversation_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        self.require_human()
        self.require_enabled_for(conv)
        data = request.data
        msg, ai_msg = conv_service.post_message(
            request.user,
            conv,
            body=data.get("body"),
            parent_id=data.get("parent_id"),
            selection=data.get("selection") or [],
            source_links=data.get("source_links") or [],
        )
        body = conv_service.serialize_message(msg)
        body["ai_answer"] = conv_service.serialize_message(ai_msg) if ai_msg else None
        return Response(body, status=status.HTTP_201_CREATED)


class MessageDetailEndpoint(CollaborationBaseView):
    def get(self, request, slug, conversation_id, message_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        return Response(conv_service.serialize_message(conv_service.get_message(conv, message_id)))

    def patch(self, request, slug, conversation_id, message_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        self.require_human()
        self.require_enabled_for(conv)
        msg = conv_service.get_message(conv, message_id)
        msg = conv_service.edit_message(request.user, conv, msg, body=request.data.get("body"))
        return Response(conv_service.serialize_message(msg))

    def delete(self, request, slug, conversation_id, message_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        self.require_human()
        msg = conv_service.get_message(conv, message_id)
        conv_service.delete_message(request.user, conv, msg)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageVersionsEndpoint(CollaborationBaseView):
    def get(self, request, slug, conversation_id, message_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        msg = conv_service.get_message(conv, message_id)
        versions = [
            {"version": v.version, "body": v.body, "created_at": v.created_at}
            for v in MessageVersion.objects.filter(message=msg).order_by("version")
        ]
        versions.append({"version": msg.version, "body": msg.body, "created_at": msg.edited_at or msg.created_at,
                         "current": True})
        return Response(versions)


class ConversationReadEndpoint(CollaborationBaseView):
    def post(self, request, slug, conversation_id):
        workspace = self.get_workspace(slug)
        conv = self.conversation(workspace, conversation_id)
        self.require_human()
        part = conv_service.mark_read(request.user, conv)
        return Response({"conversation_id": str(conv.id), "last_read_at": part.last_read_at})


# -- AI context preview -----------------------------------------------------------------


class AIContextPreviewEndpoint(CollaborationBaseView):
    """Shows which sources the AI may use for the audience, and which are blocked (FR-C02)."""

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        data = request.data
        audience = set()
        if data.get("conversation_id"):
            conv = self.conversation(workspace, data["conversation_id"])
            audience |= conversation_audience(conv)
        allowed_projects = {str(p) for p in accessible_project_ids(request.user, workspace.id)}
        project_ids = [str(p) for p in data.get("project_ids") or []]
        if any(p not in allowed_projects for p in project_ids):
            raise NotFound("Project not found")
        audience |= projects_audience(project_ids)
        ctx = assemble_context(
            requester=request.user,
            workspace_id=workspace.id,
            audience_ids=audience,
            selection=data.get("selection") or [],
        )
        return Response(ctx.as_dict())


# -- decisions ----------------------------------------------------------------------------


class DecisionPreviewEndpoint(CollaborationBaseView):
    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PROJECT_READ)
        data = request.data
        result = decision_service.preview(
            request.user,
            project,
            conversation_id=data.get("conversation_id"),
            message_ids=data.get("message_ids") or [],
            issue_id=data.get("issue_id"),
            instruction=data.get("instruction") or "",
        )
        return Response(result, status=status.HTTP_200_OK)


class DecisionListEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        qp = request.query_params
        rows = decision_service.list_for(
            project, issue_id=qp.get("issue_id"), status=qp.get("status"), kind=qp.get("kind")
        )
        return Response([decision_service.serialize(d) for d in rows])

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require_human()
        kind = request.data.get("kind") or "decision"
        cap = Capability.DECISION_PUBLISH if kind == "decision" else Capability.PACKAGE_EDIT
        self.require(project.workspace_id, project.id, cap)
        data = dict(request.data)
        if not data.get("idempotency_key") and request.headers.get("Idempotency-Key"):
            data["idempotency_key"] = request.headers["Idempotency-Key"]
        decision, created = decision_service.confirm(request.user, project, data)
        response = Response(
            decision_service.serialize(decision), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        if not created:
            response["Idempotent-Replay"] = "true"
        return response


# -- clarification --------------------------------------------------------------------------


class ClarifyEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        return Response({"questions": clarify_ai.candidate_questions(issue)})

    def post(self, request, slug, project_id, issue_id):
        issue = self.get_issue(slug, project_id, issue_id)
        self.require_human()
        self.require(issue.workspace_id, issue.project_id, Capability.PACKAGE_EDIT)
        data = request.data
        result = clarify_ai.step(
            issue,
            request.user,
            answer=data.get("answer"),
            stop=_bool(data.get("stop", False)),
            cont=_bool(data.get("continue", False)),
        )
        return Response(result)


# -- proposals --------------------------------------------------------------------------------

PROFILE_PATCH_FIELDS = ("intent", "outcome", "non_goals", "criteria", "risk", "scope")


def serialize_proposal(p):
    return {
        "id": str(p.id),
        "kind": p.kind,
        "status": p.status,
        "issue_id": str(p.issue_id) if p.issue_id else None,
        "project_id": str(p.project_id) if p.project_id else None,
        "content": p.content,
        "selection": p.selection,
        "sources": p.sources,
        "base_version": p.base_version,
        "requested_by": str(p.requested_by_id) if p.requested_by_id else None,
        "decided_by": str(p.decided_by_id) if p.decided_by_id else None,
        "decided_at": p.decided_at,
        "created_at": p.created_at,
    }


class ProposalListEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        qs = AIProposal.objects.filter(project=project)
        qp = request.query_params
        if qp.get("issue_id"):
            qs = qs.filter(issue_id=qp["issue_id"])
        if qp.get("status"):
            qs = qs.filter(status=qp["status"])
        if qp.get("kind"):
            qs = qs.filter(kind=qp["kind"])
        return Response([serialize_proposal(p) for p in qs.order_by("-created_at")[:200]])

    def post(self, request, slug, project_id):
        """Ask the AI to concretize/interpret/report — the output is only a pending proposal."""
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        data = request.data
        task = data.get("task") or "concretize"
        if task not in ("concretize", "interpret", "report", "answer"):
            raise ValidationFailed("Unknown AI task")
        issue = None
        selection = list(data.get("selection") or [])
        if data.get("issue_id"):
            issue = self.get_issue(slug, project_id, data["issue_id"])
            selection.insert(0, {"type": "issue", "id": str(issue.id)})
        ctx = assemble_context(
            requester=request.user,
            workspace_id=project.workspace_id,
            audience_ids=projects_audience([project.id]),
            selection=selection,
        )
        result = get_provider().complete(
            task, [{"role": "user", "content": data.get("instruction") or ""}] + ctx.provider_messages()
        )
        proposal = AIProposal.objects.create(
            workspace_id=project.workspace_id,
            project=project,
            issue=issue,
            kind=AIProposal.Kind.DRAFT_EDIT if task == "concretize" else AIProposal.Kind.ANSWER,
            requested_by=request.user,
            content={
                "task": task,
                "result": result.as_dict(),
                "patch": {},
                "context": ctx.as_dict(),
            },
            selection={"items": selection},
            sources=[a["ref"] for a in ctx.allowed],
        )
        code = status.HTTP_201_CREATED if result.ok else status.HTTP_200_OK
        return Response(serialize_proposal(proposal), status=code)


class ProposalDecisionEndpoint(CollaborationBaseView):
    """Human accept/reject. A rejected proposal changes nothing (FR-E06)."""

    def post(self, request, slug, project_id, proposal_id, action):
        project = self.get_project(slug, project_id)
        self.require_human()
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        if action not in ("accept", "reject"):
            raise NotFound("Unknown action")
        with transaction.atomic():
            proposal = AIProposal.objects.select_for_update().filter(id=proposal_id, project=project).first()
            if proposal is None:
                raise NotFound("Proposal not found")
            if proposal.status != AIProposal.Status.PENDING:
                raise Conflict("Proposal already decided", code="PROPOSAL_DECIDED")
            applied = {}
            if action == "accept":
                applied = self._apply(proposal, request.user)
            proposal.status = AIProposal.Status.ACCEPTED if action == "accept" else AIProposal.Status.REJECTED
            proposal.decided_by = request.user
            proposal.decided_at = timezone.now()
            proposal.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        body = serialize_proposal(proposal)
        body["applied"] = applied
        return Response(body)

    def _apply(self, proposal, user):
        if proposal.kind == AIProposal.Kind.DRAFT_EDIT:
            patch = (proposal.content or {}).get("patch") or {}
            if not patch:
                return {}
            profile = PackageProfile.objects.select_for_update().filter(issue_id=proposal.issue_id).first()
            if profile is None:
                raise Conflict("The work item has no package profile", code="PROFILE_REQUIRED")
            if proposal.base_version and str(profile.version) != proposal.base_version:
                proposal.status = AIProposal.Status.STALE
                proposal.save(update_fields=["status", "updated_at"])
                raise Conflict("The draft changed since this proposal was made", code="VERSION_CONFLICT")
            changed = []
            for field in PROFILE_PATCH_FIELDS:
                if field not in patch:
                    continue
                value = patch[field]
                if field == "scope" and isinstance(value, dict):
                    value = {**(profile.scope or {}), **value}
                setattr(profile, field, value)
                changed.append(field)
            profile.version += 1
            profile.save(update_fields=changed + ["version", "updated_at"])
            # Only the working draft changes — never an approval or revision (skill package-clarify).
            return {"profile_fields": changed, "profile_version": profile.version}
        if proposal.kind == AIProposal.Kind.DIAGRAM_INTERPRETATION:
            try:
                from ..services import diagrams  # owned by another workstream

                hook = getattr(diagrams, "accept_proposal", None)
            except ImportError:
                hook = None
            if hook:
                return hook(proposal, user) or {}
        return {}


# -- uploads --------------------------------------------------------------------------------------


class UploadRegisterEndpoint(CollaborationBaseView):
    def post(self, request, slug, project_id, asset_id):
        project = self.get_project(slug, project_id)
        self.require(project.workspace_id, project.id, Capability.PACKAGE_EDIT)
        data = request.data
        record = knowledge_service.register(
            request.user,
            project,
            asset_id,
            declared_mime=data.get("declared_mime") or "",
            filename=data.get("filename") or "",
            issue_id=data.get("issue_id"),
        )
        return Response(knowledge_service.serialize(record), status=status.HTTP_201_CREATED)


class UploadDetailEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id, asset_id):
        from ..models import UploadRecord

        project = self.get_project(slug, project_id, allow_archived=True)
        record = UploadRecord.objects.filter(asset_id=asset_id, project=project).first()
        if record is None:
            raise NotFound("Upload not found")
        return Response(knowledge_service.serialize(record))


# -- search ------------------------------------------------------------------------------------------


class SearchEndpoint(CollaborationBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        qp = request.query_params
        types = [t for t in (qp.get("types") or "").split(",") if t] or None
        results = search_service.search(request.user, workspace, qp.get("q"), types=types, limit=qp.get("limit"))
        if not self.principal.is_human:
            results = [r for r in results if not (r["type"] == "message" and r.get("conversation_id")
                                                  and Conversation.objects.filter(
                                                      id=r["conversation_id"], kind="direct").exists())]
        # No total counts (FR-P06): only the visible page of results.
        return Response({"results": results})


# -- activity / overview --------------------------------------------------------------------------


class ActivityEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        qp = request.query_params
        if qp.get("ids"):
            return Response({"raw": activity_service.raw_events(project, qp["ids"].split(","))})
        try:
            data = activity_service.feed(
                request.user,
                project,
                since=qp.get("since"),
                until=qp.get("until"),
                raw=_bool(qp.get("raw", "0")),
                issue_id=qp.get("issue_id"),
            )
        except ValueError as exc:
            raise ValidationFailed(str(exc))
        return Response(data)


class ActivityVisitEndpoint(CollaborationBaseView):
    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        marker = activity_service.record_visit(request.user, project)
        return Response(
            {"last_visited_at": marker.last_visited_at, "previous_visited_at": marker.previous_visited_at}
        )


class OverviewEndpoint(CollaborationBaseView):
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id, allow_archived=True)
        return Response(activity_service.overview(request.user, project))


# -- notifications ------------------------------------------------------------------------------------


class NotificationListEndpoint(CollaborationBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        items = notification_service.list_for(
            request.user, workspace, unread_only=_bool(request.query_params.get("unread", "0"))
        )
        data = [notification_service.serialize(i) for i in items]
        return Response(
            {
                "targeted": [d for d in data if d["delivery"] == "immediate"],
                "bundled": [d for d in data if d["delivery"] == "digest"],
            }
        )


class NotificationReadEndpoint(CollaborationBaseView):
    def post(self, request, slug, notification_id):
        workspace = self.get_workspace(slug)
        updated = NotificationItem.objects.filter(
            id=notification_id, recipient=request.user, workspace=workspace, read_at__isnull=True
        ).update(read_at=timezone.now())
        if not updated and not NotificationItem.objects.filter(
            id=notification_id, recipient=request.user, workspace=workspace
        ).exists():
            raise NotFound("Notification not found")
        return Response({"id": str(notification_id), "read": True})


# -- retention -------------------------------------------------------------------------------------------


class RetentionEndpoint(CollaborationBaseView):
    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require(workspace.id, None, Capability.WORKSPACE_ADMIN, enabled=False)
        return Response({"policies": retention_service.get_policies(workspace)})

    def put(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        self.require(workspace.id, None, Capability.WORKSPACE_ADMIN, enabled=False)
        policies = retention_service.set_policies(request.user, workspace, request.data.get("policies") or [])
        return Response({"policies": policies})


class RetentionApplyEndpoint(CollaborationBaseView):
    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        self.require(workspace.id, None, Capability.WORKSPACE_ADMIN, enabled=False)
        return Response({"result": retention_service.apply(workspace, user=request.user)})

