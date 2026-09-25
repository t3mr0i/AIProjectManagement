# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AI core endpoints: status, Ask AI, writing assist (+ streaming), project report, usage, reindex.

All calls go through ``services.ai`` → ``package_flow.ai`` (one provider layer
with timeout, budget, guards and usage metering). No endpoint lets the AI write
product data; changes are pending proposals a human accepts.
"""

import json

from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIRequest
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response

from ..capabilities import accessible_project_ids
from ..errors import HumanPrincipalRequired, NotFound, ValidationFailed
from ..models import Capability
from ..services import ai as ai_service
from ..ai import usage as usage_service
from ..ai.config import load_config
from .base import PackageFlowBaseView
from .collaboration import serialize_proposal

MAX_QUESTION_CHARS = 4000
MAX_ASSIST_TEXT_CHARS = 40000


class AIBaseView(PackageFlowBaseView):
    def require_human(self):
        if not self.principal.is_human:
            raise HumanPrincipalRequired("This action requires a verified human principal")

    def text_field(self, name, *, required=True, limit=MAX_QUESTION_CHARS):
        value = self.request.data.get(name)
        value = value.strip() if isinstance(value, str) else ""
        if required and not value:
            raise ValidationFailed(f"{name} is required", detail={"field": name})
        return value[:limit]

    def member_project(self, workspace, project_id):
        if not project_id:
            return None
        readable = {str(p) for p in accessible_project_ids(self.request.user, workspace.id)}
        if str(project_id) not in readable:
            raise NotFound("Project not found")
        return str(project_id)


class AIStatusEndpoint(AIBaseView):
    """``GET W/ai/status`` — which AI is active and which features are available (no secrets)."""

    def get(self, request, slug):
        self.get_workspace(slug)
        return Response(ai_service.status())


class AIAskEndpoint(AIBaseView):
    """``POST W/ai/ask`` — private question over everything the requester can read."""

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        question = self.text_field("question")
        project_ids = request.data.get("project_ids") or None
        if project_ids is not None:
            readable = {str(p) for p in accessible_project_ids(request.user, workspace.id)}
            if not isinstance(project_ids, list) or any(str(p) not in readable for p in project_ids):
                raise NotFound("Project not found")
        answer = ai_service.ask(
            request.user,
            workspace,
            question,
            project_ids=project_ids,
            selection=request.data.get("selection") or [],
        )
        return Response(answer)


class AIAssistEndpoint(AIBaseView):
    """``POST W/ai/assist`` — writing help (rewrite, summarize, draft) for editors."""

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        instruction = self.text_field("instruction")
        text = self.text_field("text", required=False, limit=MAX_ASSIST_TEXT_CHARS)
        project_id = self.member_project(workspace, request.data.get("project_id"))
        result = ai_service.assist(request.user, workspace, instruction=instruction, text=text, project_id=project_id)
        body = {
            "text": result.text,
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "error_code": result.error_code,
            "error": result.error,
        }
        return Response(body, status=status.HTTP_200_OK if result.ok else status.HTTP_503_SERVICE_UNAVAILABLE)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


_END = object()


def _next_or_end(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _END


async def _async_iter(iterator):
    while True:
        chunk = await sync_to_async(_next_or_end, thread_sensitive=True)(iterator)
        if chunk is _END:
            return
        yield chunk


class AIAssistStreamEndpoint(AIAssistEndpoint):
    """``POST W/ai/assist/stream`` — same as assist, streamed as Server-Sent Events.

    Events: ``delta`` ``{"text": "..."}`` (repeated), then ``done`` ``{}``.
    """

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        instruction = self.text_field("instruction")
        text = self.text_field("text", required=False, limit=MAX_ASSIST_TEXT_CHARS)
        project_id = self.member_project(workspace, request.data.get("project_id"))
        if not load_config().is_configured:
            return Response(
                {"status": "unavailable", "error_code": "AI_NOT_CONFIGURED", "error": "No AI model is configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        chunks = ai_service.assist_stream(
            request.user, workspace, instruction=instruction, text=text, project_id=project_id
        )

        def events():
            for chunk in chunks:
                yield _sse("delta", {"text": chunk})
            yield _sse("done", {})

        body = events()
        if isinstance(request._request, ASGIRequest):
            # Under ASGI a sync iterator would be buffered completely; pull chunks in a worker thread.
            body = _async_iter(body)
        response = StreamingHttpResponse(body, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # disable proxy buffering (nginx)
        return response


class AIProjectReportEndpoint(AIBaseView):
    """``POST P/ai/report`` — AI status report for a project, stored as a reviewable answer."""

    def post(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        self.require_human()
        self.require(project.workspace_id, project.id, Capability.PROJECT_READ)
        instruction = self.text_field("instruction", required=False)
        proposal, result = ai_service.project_report(request.user, project, instruction=instruction)
        return Response(
            serialize_proposal(proposal), status=status.HTTP_201_CREATED if result.ok else status.HTTP_200_OK
        )


class AIUsageEndpoint(AIBaseView):
    """``GET W/ai/usage?days=30`` — AI calls and tokens of the workspace (workspace admins)."""

    def get(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require(workspace.id, None, Capability.WORKSPACE_ADMIN, enabled=False)
        try:
            days = int(request.query_params.get("days") or 30)
        except ValueError:
            raise ValidationFailed("days must be a number", detail={"field": "days"})
        return Response(usage_service.summary(workspace.id, days=days))


class AIReindexEndpoint(AIBaseView):
    """``POST W/ai/reindex`` — rebuild the semantic index of the workspace (workspace admins)."""

    def post(self, request, slug):
        workspace = self.get_workspace(slug)
        self.require_human()
        self.require(workspace.id, None, Capability.WORKSPACE_ADMIN, enabled=False)
        from ..tasks import ai_refresh_embeddings

        ai_refresh_embeddings.delay(str(workspace.id))
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)
