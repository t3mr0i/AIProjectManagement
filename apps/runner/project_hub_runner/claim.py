# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Atomic claim, lease heartbeat and fencing (FR-G04, AC05, AC06).

* The claim is acquired atomically by the server (``POST P/work-items/{id}/claims``);
  a second exclusive claim gets ``409 CLAIM_HELD``.
* A :class:`Supervisor` thread renews the lease with the fencing token and
  (optionally) polls for cancellation of the run.
* On ``LEASE_EXPIRED`` / ``STALE_FENCING_TOKEN`` / cancellation the shared
  :class:`StopSignal` is triggered: the policy gate refuses every further
  action locally and the agent subprocess is killed (AC06, FR-G06).
* If the server is unreachable, the runner cannot prove it still owns the
  lease. Once the locally tracked lease deadline passes, it stops as if the
  lease had expired (conservative; never "assume still owner").
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import ApiError, FencingLost, RunCancelled, RunnerError, ServerUnreachable, stop_reason

# Server clamps leases to this range (package_flow/services/execution.py).
MIN_LEASE_SECONDS, MAX_LEASE_SECONDS = 30, 3600


class StopSignal:
    """Process-wide "stop all further actions" flag with callbacks."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.reason: str | None = None
        self._callbacks: list[Callable[[str], None]] = []

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def on_stop(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            already = self._event.is_set()
            if not already:
                self._callbacks.append(callback)
        if already:
            callback(self.reason or "stopped")

    def remove(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def trigger(self, reason: str) -> bool:
        """Set the flag; returns True if this call was the one that stopped."""
        with self._lock:
            if self._event.is_set():
                return False
            self.reason = reason
            self._event.set()
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(reason)
            except Exception as exc:  # noqa: BLE001 - never let a callback mask the stop
                print(f"warning: stop callback failed: {exc}", file=sys.stderr)
        return True


@dataclass
class ClaimHandle:
    id: str
    fencing_token: int
    lease_expires_at: str
    lease_seconds: int
    project_id: str
    work_item_id: str
    binding_id: str | None = None
    exclusive: bool = True
    # Monotonic deadline until which we *know* the lease is valid.
    local_deadline: float = field(default=0.0, compare=False)

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fencing_token": self.fencing_token,
            "lease_expires_at": self.lease_expires_at,
            "lease_seconds": self.lease_seconds,
            "project_id": self.project_id,
            "work_item_id": self.work_item_id,
            "binding_id": self.binding_id,
            "exclusive": self.exclusive,
        }

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> ClaimHandle:
        return cls(
            id=data["id"],
            fencing_token=int(data["fencing_token"]),
            lease_expires_at=data.get("lease_expires_at", ""),
            lease_seconds=int(data.get("lease_seconds") or 300),
            project_id=data["project_id"],
            work_item_id=data["work_item_id"],
            binding_id=data.get("binding_id"),
            exclusive=bool(data.get("exclusive", True)),
            local_deadline=time.monotonic() + 1.0,
        )


def acquire_claim(
    client,
    project_id: str,
    work_item_id: str,
    binding_id: str | None = None,
    exclusive: bool = True,
    lease_seconds: int = 300,
    approval_id: str | None = None,
) -> ClaimHandle:
    """Atomically claim a package/repo unit. Raises ClaimHeld if someone else owns it (AC05)."""
    lease_seconds = max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, int(lease_seconds)))
    sent_at = time.monotonic()
    resp = client.create_claim(project_id, work_item_id, binding_id, exclusive, lease_seconds, approval_id=approval_id)
    if not isinstance(resp, dict) or "id" not in resp or "fencing_token" not in resp:
        raise RunnerError(f"unexpected claim response: {resp!r}")
    granted = int(resp.get("lease_seconds") or lease_seconds)
    return ClaimHandle(
        id=str(resp["id"]),
        fencing_token=int(resp["fencing_token"]),
        lease_expires_at=str(resp.get("lease_expires_at") or ""),
        lease_seconds=granted,
        project_id=project_id,
        work_item_id=work_item_id,
        binding_id=binding_id,
        exclusive=exclusive,
        # measured from *before* the request: conservative
        local_deadline=sent_at + granted,
    )


def heartbeat_once(client, claim: ClaimHandle) -> dict[str, Any]:
    sent_at = time.monotonic()
    resp = client.heartbeat(claim.id, claim.fencing_token, claim.lease_seconds) or {}
    claim.lease_expires_at = str(resp.get("lease_expires_at") or claim.lease_expires_at)
    claim.local_deadline = sent_at + int(resp.get("lease_seconds") or claim.lease_seconds)
    return resp


def release_claim(client, claim: ClaimHandle) -> bool:
    try:
        client.release(claim.id, claim.fencing_token)
        return True
    except (FencingLost, ApiError, ServerUnreachable) as exc:
        print(f"note: claim release not confirmed ({exc}); the lease will expire server-side", file=sys.stderr)
        return False


class Supervisor(threading.Thread):
    """Background heartbeat + cancel watcher for one claim (and optionally one run)."""

    def __init__(
        self,
        client,
        claim: ClaimHandle,
        stop: StopSignal,
        interval: float | None = None,
        cancel_check: Callable[[], bool] | None = None,
        log: Callable[[str], None] | None = None,
    ):
        super().__init__(name=f"ph-heartbeat-{claim.id[:8]}", daemon=True)
        self.client = client
        self.claim = claim
        self.stop = stop
        self.interval = interval if interval and interval > 0 else max(1.0, claim.lease_seconds / 3.0)
        self.cancel_check = cancel_check
        self._halt = threading.Event()
        self.log = log or (lambda msg: print(msg, file=sys.stderr))
        self.beats = 0
        self.last_error: str | None = None

    def halt(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.wait(self.interval):
            if self.stop.is_set():
                return
            self.tick()

    def tick(self) -> None:
        try:
            resp = heartbeat_once(self.client, self.claim)
            self.beats += 1
            self.last_error = None
            if resp.get("cancel_requested") or resp.get("run_status") == "cancelled":
                self._trigger_stop("cancelled")
                return
        except FencingLost as exc:
            self._trigger_stop(exc.code)
            return
        except RunCancelled as exc:
            self._trigger_stop(stop_reason(exc))
            return
        except (ServerUnreachable, ApiError) as exc:
            self.last_error = str(exc)
            if isinstance(exc, ApiError) and exc.status in (401, 403):
                self._trigger_stop(f"unauthorized ({exc.code})")
                return
            if time.monotonic() >= self.claim.local_deadline:
                self._trigger_stop("lease_unconfirmed")
                return
        if self.cancel_check is not None:
            try:
                if self.cancel_check():
                    self._trigger_stop("cancelled")
            except RunCancelled:
                self._trigger_stop("cancelled")
            except (ServerUnreachable, ApiError) as exc:
                self.last_error = str(exc)

    def _trigger_stop(self, reason: str) -> None:
        if self.stop.trigger(reason):
            self.log(f"STOP: {reason} — no further actions will be taken for claim {self.claim.id}")
