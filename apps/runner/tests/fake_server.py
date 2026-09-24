# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Minimal in-process fake of the package-flow runner contract (API.md §3).

Implements just enough server behaviour to test the runner: atomic claims
with fencing counters, lease expiry, runs with run tokens, cancellation,
manifest, action gate (allowedActions + allowedPaths), events and evidence.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from project_hub_runner.manifest import canonical_hash
from project_hub_runner.policy import path_matches

P = r"/api/workspaces/(?P<slug>[^/]+)/projects/(?P<pid>[^/]+)/package-flow"
R = r"/api/package-flow"


class Reject(Exception):
    def __init__(self, status: int, code: str, detail: dict | None = None):
        super().__init__(code)
        self.status, self.code, self.detail = status, code, detail or {}


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class FakeServer:
    def __init__(self):
        self.lock = threading.Lock()
        self.runner_tokens = {"tok-A": "runner-A", "tok-B": "runner-B", "tok-C": "runner-C"}
        self.claims: dict[str, dict[str, Any]] = {}
        self.fencing: dict[str, int] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self.idem: dict[str, tuple[int, Any]] = {}
        self.fail_next: list[int] = []  # statuses to return for the next N requests (e.g. 503)
        self.workspace_id = str(uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.issue_id = str(uuid.uuid4())
        self.manifest_overrides: dict[str, Any] = {}
        self.httpd: ThreadingHTTPServer | None = None

    # --------------------------------------------------------------- knobs

    def add_approval(
        self,
        binding_id: str,
        base_commit: str,
        allowed_paths: list[str],
        allowed_actions: list[str] | None = None,
        checks: list[dict] | None = None,
        state: str = "approved",
        max_seconds: int = 600,
        max_spend_minor: int = 0,
    ) -> str:
        aid = str(uuid.uuid4())
        self.approvals[aid] = {
            "id": aid,
            "state": state,
            "revision_id": str(uuid.uuid4()),
            "revision_hash": "a" * 64,
            "binding_id": binding_id,
            "base_commit": base_commit,
            "allowed_paths": allowed_paths,
            "allowed_actions": allowed_actions
            or ["prepare_worktree", "edit_allowed_files", "run_allowed_checks", "create_commit", "push_work_branch"],
            "checks": checks or [],
            "max_seconds": max_seconds,
            "max_spend_minor": max_spend_minor,
        }
        return aid

    def expire_claim(self, claim_id: str) -> None:
        with self.lock:
            self.claims[claim_id]["expires"] = time.time() - 1

    def cancel(self, run_id: str) -> None:
        with self.lock:
            self.runs[run_id]["status"] = "cancelled"
            self.runs[run_id]["cancel_requested_at"] = iso(datetime.now(timezone.utc))

    # ------------------------------------------------------------- helpers

    def _unit(self, issue: str, binding: str | None) -> str:
        return f"{issue}:{binding or 'none'}"

    def _live(self, claim: dict) -> bool:
        if claim["status"] == "active" and claim["expires"] < time.time():
            claim["status"] = "expired"
        return claim["status"] == "active"

    def _fence(self, claim_id: str, token: Any) -> dict:
        claim = self.claims.get(claim_id)
        if claim is None:
            raise Reject(404, "NOT_FOUND")
        if not self._live(claim):
            raise Reject(409, "LEASE_EXPIRED")
        if token != claim["fencing_token"] or self.fencing[claim["unit"]] != token:
            raise Reject(409, "STALE_FENCING_TOKEN")
        return claim

    def _run_auth(self, run_id: str, headers, body: dict | None, need_fence: bool = True) -> dict:
        run = self.runs.get(run_id)
        if run is None:
            raise Reject(404, "NOT_FOUND")
        if headers.get("X-Run-Token") != run["run_token"]:
            raise Reject(401, "RUN_TOKEN_INVALID")
        if run["status"] == "cancelled":
            raise Reject(409, "RUN_CANCELLED")
        if need_fence:
            token = (body or {}).get("fencing_token")
            # Fencing is checked against the claim that owns the unit NOW (AC06).
            claim = self.claims[run["claim_id"]]
            if not self._live(claim):
                raise Reject(409, "LEASE_EXPIRED")
            if token != claim["fencing_token"] or self.fencing[claim["unit"]] != token:
                raise Reject(409, "STALE_FENCING_TOKEN")
        return run

    def manifest_for(self, run: dict) -> dict:
        a = self.approvals[run["approval_id"]]
        now = datetime.now(timezone.utc)
        m = {
            "schemaVersion": "1.1.0",
            "runId": run["id"],
            "workspaceId": self.workspace_id,
            "projectId": self.project_id,
            "workItemId": self.issue_id,
            "revisionId": a["revision_id"],
            "revisionHash": a["revision_hash"],
            "revisionState": a["state"],
            "policyVersion": "policy-1",
            # Same shape as plane/package_flow/services/execution.py::build_manifest
            "approvalId": a["id"],
            "expiresAt": iso(now + timedelta(hours=1)),
            "claimId": run["claim_id"],
            "fencingToken": self.claims[run["claim_id"]]["fencing_token"],
            "repositoryScope": [
                {
                    "bindingId": a["binding_id"],
                    "baseCommit": a["base_commit"],
                    "targetBranch": "main",
                    "allowedPaths": a["allowed_paths"],
                }
            ],
            "allowedActions": a["allowed_actions"],
            "limits": {"maxSeconds": a["max_seconds"], "maxSpendMinor": a["max_spend_minor"], "currency": "EUR"},
            "checks": a["checks"],
            "intent": {"title": "Add feature", "intent": "Implement the feature", "criteria": [{"text": "works"}]},
        }
        m.update(self.manifest_overrides)
        return m

    # ------------------------------------------------------------- routing

    def handle(self, method: str, path: str, headers, body: dict | None) -> tuple[int, Any]:
        self.requests.append((method, path))
        if self.fail_next:
            return self.fail_next.pop(0), {"error": "unavailable"}
        auth = headers.get("Authorization", "")
        runner = self.runner_tokens.get(auth[len("Runner ") :]) if auth.startswith("Runner ") else None
        if runner is None:
            raise Reject(401, "UNAUTHENTICATED")
        key = headers.get("Idempotency-Key")
        if method == "POST" and key and key in self.idem:
            return self.idem[key]
        with self.lock:
            result = self._route(method, path, headers, body or {}, runner)
        if method == "POST" and key:
            self.idem[key] = result
        return result

    def _route(self, method, path, headers, body, runner):
        m = re.fullmatch(P + r"/work-items/(?P<iid>[^/]+)/claims", path)
        if m and method == "POST":
            unit = self._unit(m["iid"], body.get("repository_binding_id"))
            exclusive = body.get("exclusive", True)
            for c in self.claims.values():
                if c["unit"] == unit and self._live(c) and (c["exclusive"] or exclusive):
                    raise Reject(409, "CLAIM_HELD", {"holder": c["runner"]})
            self.fencing[unit] = self.fencing.get(unit, 0) + 1
            cid = str(uuid.uuid4())
            lease = int(body.get("lease_seconds", 300))
            self.claims[cid] = {
                "id": cid,
                "unit": unit,
                "exclusive": exclusive,
                "fencing_token": self.fencing[unit],
                "expires": time.time() + lease,
                "status": "active",
                "runner": runner,
                "lease": lease,
            }
            return 201, {
                "id": cid,
                "fencing_token": self.fencing[unit],
                "lease_expires_at": iso(datetime.now(timezone.utc) + timedelta(seconds=lease)),
                "lease_seconds": lease,
            }
        m = re.fullmatch(R + r"/claims/(?P<cid>[^/]+)/heartbeat", path)
        if m and method == "POST":
            claim = self._fence(m["cid"], body.get("fencing_token"))
            claim["expires"] = time.time() + claim["lease"]
            cancel = any(r["claim_id"] == claim["id"] and r["status"] == "cancelled" for r in self.runs.values())
            claim["lease"] = int(body.get("lease_seconds") or claim["lease"])
            claim["expires"] = time.time() + claim["lease"]
            return 200, {"id": claim["id"], "lease_seconds": claim["lease"], "cancel_requested": cancel}
        m = re.fullmatch(R + r"/claims/(?P<cid>[^/]+)/release", path)
        if m and method == "POST":
            claim = self._fence(m["cid"], body.get("fencing_token"))
            claim["status"] = "released"
            return 200, {"status": "released"}
        m = re.fullmatch(P + r"/work-items/(?P<iid>[^/]+)/runs", path)
        if m and method == "GET":
            return 200, [
                {k: v for k, v in r.items() if k != "run_token"} for r in self.runs.values() if r["issue"] == m["iid"]
            ]
        if m and method == "POST":
            approval = self.approvals.get(body.get("approval_id"))
            if approval is None or approval["state"] != "approved":
                raise Reject(422, "REVISION_NOT_APPROVED")
            claim = self.claims.get(body.get("claim_id"))
            if claim is None or not self._live(claim):
                raise Reject(409, "CLAIM_INVALID")
            rid = str(uuid.uuid4())
            self.runs[rid] = {
                "id": rid,
                "issue": m["iid"],
                "status": "claimed",
                "run_token": "rt-" + uuid.uuid4().hex,
                "claim_id": claim["id"],
                "approval_id": approval["id"],
                "mode": body.get("mode"),
                "cancel_requested_at": None,
            }
            run = {k: v for k, v in self.runs[rid].items() if k != "run_token"}
            return 201, {"run": run, "run_token": self.runs[rid]["run_token"]}
        m = re.fullmatch(R + r"/runs/(?P<rid>[^/]+)/manifest", path)
        if m and method == "GET":
            run = self._run_auth(m["rid"], headers, None, need_fence=False)
            m = self.manifest_for(run)
            return 200, {"manifest": m, "manifest_hash": canonical_hash(m)}
        m = re.fullmatch(R + r"/runs/(?P<rid>[^/]+)/(?P<kind>events|actions|evidence)", path)
        if m and method == "POST":
            run = self._run_auth(m["rid"], headers, body)
            if m["kind"] == "events":
                self.events.append({"run_id": run["id"], **body})
                status_map = {"started": "running", "waiting": "waiting", "finished": "finished", "failed": "failed"}
                if body.get("type") in status_map:
                    run["status"] = status_map[body["type"]]
                return 201, {"ok": True}
            if m["kind"] == "evidence":
                if body.get("result") not in ("passed", "failed", "not_run", "unknown"):
                    raise Reject(422, "VALIDATION_FAILED")
                self.evidence.append({"run_id": run["id"], **body})
                return 201, {"ok": True}
            a = self.approvals[run["approval_id"]]
            action = body.get("action")
            paths = (body.get("detail") or {}).get("paths") or []
            accepted, reason = True, ""
            if action not in a["allowed_actions"]:
                accepted, reason = False, "ACTION_NOT_ALLOWED"
            elif paths and not all(path_matches(p, a["allowed_paths"]) for p in paths):
                accepted, reason = False, "PATH_NOT_ALLOWED"
            elif action == "run_allowed_checks" and (body.get("detail") or {}).get("check") not in {
                c["name"] for c in a["checks"]
            }:
                accepted, reason = False, "CHECK_NOT_ALLOWED"
            self.actions.append({"run_id": run["id"], "action": action, "accepted": accepted, "detail": body})
            if not accepted:
                raise Reject(409, reason)
            return 200, {"accepted": True}
        m = re.fullmatch(R + r"/runner/me", path)
        if m:
            return 200, {"runner": runner}
        raise Reject(404, "NOT_FOUND")

    # -------------------------------------------------------------- server

    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def _do(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"null") if length else None
                try:
                    status, payload = fake.handle(method, self.path, self.headers, body)
                except Reject as r:
                    status, payload = r.status, {"error": r.code.lower(), "code": r.code, "detail": r.detail}
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                self._do("GET")

            def do_POST(self):  # noqa: N802
                self._do("POST")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    # ------------------------------------------------------------ queries

    def accepted(self, action: str) -> list[dict]:
        return [a for a in self.actions if a["action"] == action and a["accepted"]]

    def event_types(self, run_id: str | None = None) -> list[str]:
        return [e["type"] for e in self.events if run_id is None or e["run_id"] == run_id]
