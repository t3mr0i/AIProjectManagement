# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Principal resolution (INV-03).

A principal's kind is derived from *how* the request authenticated, never
from payload fields. ``actor_kind: human`` in a JSON body is ignored.

* human  — interactive Plane session of a non-bot user
* agent  — runner token, API key, or bot user
* system — internal jobs (never from HTTP)
"""

import hashlib
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from plane.authentication.session import BaseSessionAuthentication


HUMAN = "human"
AGENT = "agent"
SYSTEM = "system"


@dataclass(frozen=True)
class Principal:
    user: object
    kind: str
    runner: Optional[object] = None
    via: str = "session"

    @property
    def is_human(self) -> bool:
        return self.kind == HUMAN

    @property
    def id(self) -> str:
        return str(self.user.id) if self.user is not None else "system"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RunnerTokenAuthentication(authentication.BaseAuthentication):
    """``Authorization: Runner <token>`` — authenticates an external runner as agent."""

    keyword = "Runner"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None
        token = header[len(self.keyword) + 1 :].strip()
        if not token:
            raise AuthenticationFailed("Runner token missing")
        from plane.package_flow.models import RunnerProfile

        runner = (
            RunnerProfile.objects.select_related("owner", "workspace")
            .filter(token_hash=hash_token(token), is_active=True, deleted_at__isnull=True)
            .first()
        )
        if runner is None or not runner.owner.is_active:
            raise AuthenticationFailed("Runner token is not valid")
        RunnerProfile.objects.filter(pk=runner.pk).update(last_seen_at=timezone.now())
        return (runner.owner, runner)

    def authenticate_header(self, request):
        return self.keyword


def resolve_principal(request) -> Principal:
    """Derive the principal kind from the authenticator that succeeded."""
    user = request.user
    authenticator = getattr(request, "successful_authenticator", None)
    from plane.package_flow.models import RunnerProfile

    if isinstance(request.auth, RunnerProfile):
        return Principal(user=user, kind=AGENT, runner=request.auth, via="runner")
    if getattr(user, "is_bot", False):
        return Principal(user=user, kind=AGENT, via="bot")
    if isinstance(authenticator, BaseSessionAuthentication):
        return Principal(user=user, kind=HUMAN, via="session")
    # API keys and anything else are treated as automation, never as a human approval.
    return Principal(user=user, kind=AGENT, via=type(authenticator).__name__ if authenticator else "unknown")
