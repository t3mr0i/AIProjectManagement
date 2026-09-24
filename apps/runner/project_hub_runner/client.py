# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""HTTP client for the package-flow runner contract (docs/project-hub/API.md §3).

This is the ONLY module that knows URL paths and headers. If the server
contract changes, adjust :class:`Paths` and the thin endpoint methods here.

Behaviour:

* outbound-only HTTP(S) via :mod:`urllib` (the runner never listens);
* ``Authorization: Runner <token>`` on every call, ``X-Run-Token`` on run-scoped calls;
* per-request timeout; retries with exponential backoff **only** for network
  errors and 5xx — never for 4xx (a 409 STALE_FENCING_TOKEN must not be retried);
* every write carries an ``Idempotency-Key`` that is reused across retries,
  so a retried write never creates a second claim/run/event (INV-07);
* error bodies are mapped to typed exceptions (:mod:`.errors`).
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from . import __version__
from .errors import ConfigError, ServerError, ServerUnreachable, error_for

USER_AGENT = f"project-hub-runner/{__version__}"


@dataclass(frozen=True)
class Paths:
    """URL templates. ``P``/``W``/``R`` prefixes as in API.md."""

    workspace_prefix: str = "/api/workspaces/{slug}/package-flow"
    project_prefix: str = "/api/workspaces/{slug}/projects/{project_id}/package-flow"
    runner_prefix: str = "/api/package-flow"

    def W(self, slug: str) -> str:  # noqa: N802 - mirrors API.md notation
        return self.workspace_prefix.format(slug=quote(slug, safe=""))

    def P(self, slug: str, project_id: str) -> str:  # noqa: N802
        return self.project_prefix.format(slug=quote(slug, safe=""), project_id=quote(project_id, safe=""))

    def R(self) -> str:  # noqa: N802
        return self.runner_prefix


def _q(value: str) -> str:
    return quote(str(value), safe="")


class Client:
    def __init__(
        self,
        server: str,
        workspace: str,
        token: str,
        timeout: float = 15.0,
        retries: int = 3,
        backoff: float = 0.5,
        paths: Paths | None = None,
        sleep=time.sleep,
    ):
        if not server.lower().startswith(("https://", "http://")):
            raise ConfigError(f"server URL must be http(s): {server!r}")
        self.server = server.rstrip("/")
        self.workspace = workspace
        self._token = token
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff = backoff
        self.paths = paths or Paths()
        self._sleep = sleep

    @classmethod
    def from_config(cls, cfg, **kw) -> Client:
        return cls(cfg.server, cfg.workspace, cfg.token, timeout=cfg.request_timeout, **kw)

    # ------------------------------------------------------------------ core

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        run_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        url = self.server + path
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Runner {self._token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if run_token:
            headers["X-Run-Token"] = run_token
        if method.upper() != "GET":
            headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())

        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt:
                delay = self.backoff * (2 ** (attempt - 1))
                self._sleep(delay + random.uniform(0, delay / 2))
            req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - scheme checked in __init__
                    raw = resp.read()
                    return _decode(raw)
            except urllib.error.HTTPError as exc:
                raw = b""
                try:
                    raw = exc.read()
                except OSError:
                    pass
                err = error_for(exc.code, _decode(raw))
                if exc.code >= 500 and not _is_terminal_code(err.code):
                    last_exc = err
                    continue
                raise err from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_exc = exc
                continue
        if isinstance(last_exc, ServerError):
            raise last_exc
        raise ServerUnreachable(f"{method} {path}: {last_exc}") from last_exc

    # --------------------------------------------------------------- runners

    def whoami(self) -> Any:
        # Not (yet) part of API.md §3: proposed ``GET R/runner/me``. Callers treat NotFound as "not supported".
        return self.request("GET", f"{self.paths.R()}/runner/me")

    # ---------------------------------------------------------------- claims

    def create_claim(
        self,
        project_id: str,
        issue_id: str,
        repository_binding_id: str | None = None,
        exclusive: bool = True,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"exclusive": bool(exclusive), "lease_seconds": int(lease_seconds)}
        if repository_binding_id:
            body["repository_binding_id"] = repository_binding_id
        path = f"{self.paths.P(self.workspace, project_id)}/work-items/{_q(issue_id)}/claims"
        return self.request("POST", path, body, idempotency_key=idempotency_key)

    def heartbeat(self, claim_id: str, fencing_token: int) -> dict[str, Any]:
        path = f"{self.paths.R()}/claims/{_q(claim_id)}/heartbeat"
        return self.request("POST", path, {"fencing_token": fencing_token}) or {}

    def release(self, claim_id: str, fencing_token: int) -> dict[str, Any]:
        path = f"{self.paths.R()}/claims/{_q(claim_id)}/release"
        return self.request("POST", path, {"fencing_token": fencing_token}) or {}

    # ------------------------------------------------------------------ runs

    def start_run(
        self,
        project_id: str,
        issue_id: str,
        approval_id: str,
        claim_id: str,
        mode: str = "agent",
        agent_adapter: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"approval_id": approval_id, "claim_id": claim_id, "mode": mode}
        if agent_adapter:
            body["agent_adapter"] = agent_adapter
        path = f"{self.paths.P(self.workspace, project_id)}/work-items/{_q(issue_id)}/runs"
        return self.request("POST", path, body, idempotency_key=idempotency_key)

    def list_runs(self, project_id: str, issue_id: str) -> list[dict[str, Any]]:
        path = f"{self.paths.P(self.workspace, project_id)}/work-items/{_q(issue_id)}/runs"
        data = self.request("GET", path)
        if isinstance(data, dict):
            data = data.get("results") or data.get("runs") or []
        return list(data or [])

    def get_manifest(self, run_id: str, run_token: str) -> Any:
        return self.request("GET", f"{self.paths.R()}/runs/{_q(run_id)}/manifest", run_token=run_token)

    def post_event(
        self, run_id: str, run_token: str, event_type: str, fencing_token: int, detail: dict[str, Any] | None = None
    ) -> Any:
        body = {"type": event_type, "fencing_token": fencing_token, "detail": detail or {}}
        return self.request("POST", f"{self.paths.R()}/runs/{_q(run_id)}/events", body, run_token=run_token)

    def request_action(
        self, run_id: str, run_token: str, action: str, fencing_token: int, detail: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = {"action": action, "fencing_token": fencing_token, "detail": detail or {}}
        return self.request("POST", f"{self.paths.R()}/runs/{_q(run_id)}/actions", body, run_token=run_token) or {}

    def post_evidence(self, run_id: str, run_token: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", f"{self.paths.R()}/runs/{_q(run_id)}/evidence", payload, run_token=run_token)


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"error": raw[:500].decode("utf-8", "replace")}


def _is_terminal_code(code: str) -> bool:
    """Domain codes are never retried even if a proxy wraps them in a 5xx."""
    return not code.startswith("HTTP_") and code not in ("SERVER_ERROR", "INTERNAL_ERROR")
