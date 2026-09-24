# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Typed runner errors.

Server error bodies look like ``{"error": str, "code": str, "detail"?: {}}``
(docs/project-hub/API.md). :func:`error_for` maps the stable ``code`` to one
of the classes below so callers can react to *meaning* (e.g. "my fencing token
is stale, stop everything") rather than to HTTP status numbers.
"""

from __future__ import annotations

from typing import Any


class RunnerError(Exception):
    """Base class for all runner errors."""

    exit_code = 1


class ConfigError(RunnerError):
    exit_code = 2


class ServerUnreachable(RunnerError):
    """Network failure / timeout after retries. Server state is *unknown* (FR-G07)."""

    exit_code = 6


class ApiError(RunnerError):
    """An error response from the server."""

    def __init__(self, status: int, code: str, message: str = "", detail: dict[str, Any] | None = None):
        super().__init__(f"{status} {code}: {message}" if message else f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail or {}


class ServerError(ApiError):
    """5xx that persisted through all retries."""

    exit_code = 6


class Unauthenticated(ApiError):
    exit_code = 2


class Forbidden(ApiError):
    exit_code = 2


class NotFound(ApiError):
    exit_code = 2


class RateLimited(ApiError):
    pass


class IdempotencyMismatch(ApiError):
    pass


class ExtensionDisabled(Forbidden):
    pass


# --- claims / fencing (FR-G04, AC05, AC06) ---------------------------------


class ClaimHeld(ApiError):
    """Another principal holds the exclusive claim (AC05)."""

    exit_code = 3

    @property
    def holder(self) -> Any:
        return self.detail.get("holder")


class FencingLost(ApiError):
    """Our claim is no longer the valid owner. All further actions MUST stop (AC06)."""

    exit_code = 5


class StaleFencingToken(FencingLost):
    pass


class LeaseExpired(FencingLost):
    pass


class ClaimInvalid(FencingLost):
    pass


# --- run start refusals (INV-01, INV-04, AC01) ------------------------------


class RunRefused(ApiError):
    """The server refused to start a run for this approval/revision."""

    exit_code = 2


class RevisionNotApproved(RunRefused):
    pass


class ApprovalRevoked(RunRefused):
    pass


class ApprovalExpired(RunRefused):
    pass


class NativeSourceChanged(RunRefused):
    pass


class ProjectArchived(RunRefused):
    pass


# --- in-run -----------------------------------------------------------------


class RunCancelled(ApiError):
    """Run was cancelled / its run token is no longer valid (FR-G06)."""

    exit_code = 5


class ActionRejected(ApiError):
    """The server action gate refused a controlled action."""

    exit_code = 4


# --- local (non-HTTP) -------------------------------------------------------


class ManifestInvalid(RunnerError):
    """Manifest missing fields, wrong hash, draft revision, expired approval ... (INV-01)."""

    exit_code = 2


class PolicyViolation(RunnerError):
    """A local policy check refused an action or a produced change (AC27, FR-G06)."""

    exit_code = 4

    def __init__(self, message: str, paths: list[str] | None = None, action: str | None = None):
        super().__init__(message)
        self.paths = list(paths or [])
        self.action = action


class ActionsStopped(RunnerError):
    """The run was stopped (fencing lost, cancelled, timeout); no further actions are allowed."""

    exit_code = 5

    def __init__(self, reason: str):
        super().__init__(f"actions stopped: {reason}")
        self.reason = reason


class BaseMoved(RunnerError):
    """Target head differs from the approved baseCommit and policy requires a decision (INV-04)."""

    exit_code = 3

    def __init__(self, base_commit: str, current_head: str, target_branch: str):
        super().__init__(
            f"target branch {target_branch!r} moved: approved base {base_commit[:12]}, current head {current_head[:12]}"
        )
        self.base_commit = base_commit
        self.current_head = current_head
        self.target_branch = target_branch


class WorkspaceError(RunnerError):
    exit_code = 4


class GitError(RunnerError):
    exit_code = 4


_CODE_MAP: dict[str, type[ApiError]] = {
    "CLAIM_HELD": ClaimHeld,
    "STALE_FENCING_TOKEN": StaleFencingToken,
    "LEASE_EXPIRED": LeaseExpired,
    "CLAIM_INVALID": ClaimInvalid,
    "CLAIM_RELEASED": ClaimInvalid,
    "REVISION_NOT_APPROVED": RevisionNotApproved,
    "REVISION_NOT_READY": RevisionNotApproved,
    "REVISION_STALE": RevisionNotApproved,
    "APPROVAL_REVOKED": ApprovalRevoked,
    "APPROVAL_EXPIRED": ApprovalExpired,
    "NATIVE_SOURCE_CHANGED": NativeSourceChanged,
    "PROJECT_ARCHIVED": ProjectArchived,
    "RUN_CANCELLED": RunCancelled,
    "RUN_TOKEN_EXPIRED": RunCancelled,
    "RUN_TOKEN_INVALID": RunCancelled,
    "RUN_NOT_ACTIVE": RunCancelled,
    "RUNNER_DEACTIVATED": Unauthenticated,
    "ACTION_NOT_ALLOWED": ActionRejected,
    "ACTION_REJECTED": ActionRejected,
    "PATH_NOT_ALLOWED": ActionRejected,
    "BUDGET_EXCEEDED": ActionRejected,
    "TIME_LIMIT_EXCEEDED": ActionRejected,
    "IDEMPOTENCY_MISMATCH": IdempotencyMismatch,
    "EXTENSION_DISABLED": ExtensionDisabled,
}

_STATUS_MAP: dict[int, type[ApiError]] = {
    401: Unauthenticated,
    403: Forbidden,
    404: NotFound,
    429: RateLimited,
}


def error_for(status: int, body: Any) -> ApiError:
    """Build the most specific typed error for a server error response."""
    code, message, detail = f"HTTP_{status}", "", {}
    if isinstance(body, dict):
        code = str(body.get("code") or code)
        message = str(body.get("error") or "")
        raw_detail = body.get("detail")
        detail = raw_detail if isinstance(raw_detail, dict) else ({"detail": raw_detail} if raw_detail else {})
    cls = _CODE_MAP.get(code)
    if cls is None:
        cls = ServerError if status >= 500 else _STATUS_MAP.get(status, ApiError)
    return cls(status, code, message, detail)
