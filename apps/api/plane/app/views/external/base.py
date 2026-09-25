# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python import
import os

# Third party import
import requests

from rest_framework import status
from rest_framework.response import Response

# Module import
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import ProjectLiteSerializer, WorkspaceLiteSerializer
from plane.db.models import Project, Workspace
from plane.license.utils.instance_value import get_configuration_value
from plane.package_flow.ai.config import load_config
from plane.package_flow.services import ai as ai_service

from ..base import BaseAPIView

MAX_PROMPT_CHARS = 40000


def _assist_response(request, slug, *, instruction, text, project_id=None, feature):
    """Upstream AI assistant endpoints, served by the central AI core (timeout, budget, metering)."""
    if not load_config().is_configured:
        return None, Response(
            {"error": "LLM provider API key and model are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    workspace = Workspace.objects.get(slug=slug)
    result = ai_service.assist(
        request.user,
        workspace,
        instruction=instruction,
        text=str(text or "")[:MAX_PROMPT_CHARS],
        project_id=project_id,
        feature=feature,
    )
    if not result.ok or not result.text:
        code = status.HTTP_504_GATEWAY_TIMEOUT if result.status == "timeout" else status.HTTP_500_INTERNAL_SERVER_ERROR
        return None, Response({"error": result.error or "An internal error has occurred."}, status=code)
    return (result, workspace), None


class GPTIntegrationEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        task = request.data.get("task", False)
        if not task:
            return Response({"error": "Task is required"}, status=status.HTTP_400_BAD_REQUEST)
        ok, error = _assist_response(
            request,
            slug,
            instruction=str(task),
            text=request.data.get("prompt") or "",
            project_id=project_id,
            feature="gpt_assistant_project",
        )
        if error is not None:
            return error
        result, workspace = ok
        project = Project.objects.get(pk=project_id)
        return Response(
            {
                "response": result.text,
                "response_html": result.text.replace("\n", "<br/>"),
                "project_detail": ProjectLiteSerializer(project).data,
                "workspace_detail": WorkspaceLiteSerializer(workspace).data,
            },
            status=status.HTTP_200_OK,
        )


class WorkspaceGPTIntegrationEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        task = request.data.get("task", False)
        if not task:
            return Response({"error": "Task is required"}, status=status.HTTP_400_BAD_REQUEST)
        ok, error = _assist_response(
            request,
            slug,
            instruction=str(task),
            text=request.data.get("prompt") or "",
            feature="gpt_assistant_workspace",
        )
        if error is not None:
            return error
        result, _workspace = ok
        return Response(
            {"response": result.text, "response_html": result.text.replace("\n", "<br/>")},
            status=status.HTTP_200_OK,
        )


def _tone_instruction(data):
    """Pages editor tone tasks (``casual_score``/``formal_score`` 0..10)."""
    try:
        casual = int(data.get("casual_score") or 0)
        formal = int(data.get("formal_score") or 0)
    except (TypeError, ValueError):
        casual = formal = 0
    if formal > casual:
        tone = "formal and professional"
    elif casual > formal:
        tone = "casual and friendly"
    else:
        tone = "clear and neutral"
    return (
        f"Rewrite the text in a {tone} tone and fix grammar and spelling. Keep the meaning, the language and "
        "any Markdown structure."
    )


class RephraseGrammarEndpoint(BaseAPIView):
    """``POST workspaces/<slug>/rephrase-grammar/`` — tone/grammar rewrite used by the pages editor."""

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        text = request.data.get("text_input") or ""
        if not str(text).strip():
            return Response({"error": "text_input is required"}, status=status.HTTP_400_BAD_REQUEST)
        ok, error = _assist_response(
            request, slug, instruction=_tone_instruction(request.data), text=text, feature="editor_rephrase"
        )
        if error is not None:
            return error
        result, _workspace = ok
        return Response({"response": result.text}, status=status.HTTP_200_OK)


class UnsplashEndpoint(BaseAPIView):
    def get(self, request):
        (UNSPLASH_ACCESS_KEY,) = get_configuration_value(
            [
                {
                    "key": "UNSPLASH_ACCESS_KEY",
                    "default": os.environ.get("UNSPLASH_ACCESS_KEY"),
                }
            ]
        )
        # Check unsplash access key
        if not UNSPLASH_ACCESS_KEY:
            return Response([], status=status.HTTP_200_OK)

        # Query parameters
        query = request.GET.get("query", False)
        page = request.GET.get("page", 1)
        per_page = request.GET.get("per_page", 20)

        url = (
            f"https://api.unsplash.com/search/photos/?client_id={UNSPLASH_ACCESS_KEY}&query={query}&page=${page}&per_page={per_page}"
            if query
            else f"https://api.unsplash.com/photos/?client_id={UNSPLASH_ACCESS_KEY}&page={page}&per_page={per_page}"
        )

        headers = {"Content-Type": "application/json"}

        resp = requests.get(url=url, headers=headers)
        return Response(resp.json(), status=resp.status_code)
