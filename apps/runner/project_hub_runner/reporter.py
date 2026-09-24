# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run events and evidence (J05, FR-G07, INV-08, skill package-handoff).

* Events: ``started``, coarse ``progress`` (phase changes, throttled — not
  every tool call), ``waiting``, ``question``, ``finished``, ``failed``.
* Evidence trust classes:
  - ``runner_reported``: a check the runner itself executed. ``passed`` only
    if it actually ran and exited 0; otherwise ``failed`` / ``timed_out`` /
    ``not_run``. A missing check is never reported as passed.
  - ``local_self_report``: a claim made by the developer or the agent
    (e.g. "I ran the tests in my IDE"). Stored as a claim (result ``unknown``).
  The server decides the final trust class from the runner kind (a ``local``
  runner's evidence is always ``local_self_report``); the runner may only ask
  for a *lower* class, never a higher one.
* If the server is unreachable an event is kept locally as *unsent* — the
  runner never invents a server status (FR-G07, AC32).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .errors import ApiError, FencingLost, RunCancelled, ServerUnreachable, stop_reason

TRUST_RUNNER = "runner_reported"
TRUST_SELF = "local_self_report"
EVENT_TYPES = ("started", "progress", "waiting", "question", "finished", "failed")


@dataclass
class CheckResult:
    name: str
    command: list[str]
    executed: bool
    exit_code: int | None
    timed_out: bool = False
    duration_s: float = 0.0
    output_tail: str = ""
    reason: str = ""

    @property
    def result(self) -> str:
        if not self.executed:
            return "not_run"
        if self.timed_out:
            return "timed_out"
        if self.exit_code == 0:
            return "passed"
        return "failed"

    @property
    def evidence_result(self) -> str:
        """Server vocabulary (Evidence.Result): passed | failed | not_run | unknown."""
        return "failed" if self.result == "timed_out" else self.result


class Reporter:
    def __init__(
        self,
        client,
        run_id: str,
        run_token: str,
        claim,
        stop,
        progress_interval: float = 30.0,
        clock=time.monotonic,
    ):
        self.client = client
        self.run_id = run_id
        self.run_token = run_token
        self.claim = claim
        self.stop = stop
        self.progress_interval = progress_interval
        self._clock = clock
        self._last_progress_at: float | None = None
        self._last_phase: str | None = None
        self.sent: list[dict[str, Any]] = []
        self.unsent: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        # Set once the manifest is known; links evidence to the repository binding (FR-G08).
        self.binding_id: str | None = None

    # ---------------------------------------------------------------- events

    def _send(self, kind: str, payload: dict[str, Any], best_effort: bool = False) -> bool:
        record = {"kind": kind, "payload": payload, "at": time.time()}
        try:
            if kind == "event":
                self.client.post_event(
                    self.run_id, self.run_token, payload["type"], self.claim.fencing_token, payload.get("detail")
                )
            else:
                self.client.post_evidence(self.run_id, self.run_token, payload)
        except FencingLost as exc:
            self.stop.trigger(exc.code)
            record["error"] = exc.code
            self.unsent.append(record)
            if best_effort:
                return False
            raise
        except RunCancelled as exc:
            self.stop.trigger(stop_reason(exc))
            record["error"] = exc.code
            self.unsent.append(record)
            if best_effort:
                return False
            raise
        except (ServerUnreachable, ApiError) as exc:
            record["error"] = getattr(exc, "code", None) or str(exc)
            self.unsent.append(record)
            return False
        self.sent.append(record)
        return True

    def event(self, event_type: str, detail: dict[str, Any] | None = None, best_effort: bool = False) -> bool:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type}")
        return self._send("event", {"type": event_type, "detail": detail or {}}, best_effort=best_effort)

    def started(self, detail: dict[str, Any] | None = None) -> bool:
        return self.event("started", detail)

    def progress(self, phase: str, message: str = "", force: bool = False) -> bool:
        """Coarse progress: only on phase change or after ``progress_interval`` seconds."""
        now = self._clock()
        due = self._last_progress_at is None or now - self._last_progress_at >= self.progress_interval
        if not force and phase == self._last_phase and not due:
            return False
        self._last_phase, self._last_progress_at = phase, now
        return self.event("progress", {"phase": phase, "message": message[:500]})

    def waiting(self, reason: str, detail: dict[str, Any] | None = None) -> bool:
        return self.event("waiting", {"reason": reason, **(detail or {})}, best_effort=True)

    def question(self, text: str, detail: dict[str, Any] | None = None) -> bool:
        return self.event("question", {"text": text[:4000], **(detail or {})})

    def finished(self, detail: dict[str, Any] | None = None) -> bool:
        return self.event("finished", detail, best_effort=True)

    def failed(self, reason: str, detail: dict[str, Any] | None = None) -> bool:
        return self.event("failed", {"reason": reason, **(detail or {})}, best_effort=True)

    # -------------------------------------------------------------- evidence

    def check_evidence(self, check: CheckResult, commit_sha: str | None) -> bool:
        payload = {
            "fencing_token": self.claim.fencing_token,
            "kind": "check",
            "name": check.name,
            "trust": TRUST_RUNNER,
            "result": check.evidence_result,
            "executed": check.executed,
            "exit_code": check.exit_code,
            "commit_sha": commit_sha,
            "detail": {
                "local_result": check.result,
                "timed_out": check.timed_out,
                "executed": check.executed,
                "exit_code": check.exit_code,
                "command": check.command,
                "duration_s": round(check.duration_s, 3),
                "output_tail": check.output_tail[-2000:],
                "reason": check.reason,
            },
        }
        if self.binding_id:
            payload["repository_binding_id"] = self.binding_id
        self.evidence.append(payload)
        return self._send("evidence", payload, best_effort=True)

    def self_report(self, claim_text: str, commit_sha: str | None, detail: dict[str, Any] | None = None) -> bool:
        payload = {
            "fencing_token": self.claim.fencing_token,
            "kind": "self_report",
            "name": "developer_claim",
            "trust": TRUST_SELF,
            # A claim is not a result: never "passed" (server vocabulary: "unknown").
            "result": "unknown",
            "executed": False,
            "commit_sha": commit_sha,
            "detail": {"text": claim_text[:4000], "claim": True, **(detail or {})},
        }
        if self.binding_id:
            payload["repository_binding_id"] = self.binding_id
        self.evidence.append(payload)
        return self._send("evidence", payload, best_effort=True)
