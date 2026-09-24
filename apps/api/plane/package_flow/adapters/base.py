# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider adapter contract (PRD §12.1/§12.2, FR-I02, FR-G10).

An adapter

* declares its capabilities honestly — one of ``supported``, ``partial``,
  ``unsupported``, ``requires_configuration`` for each of the 13 capabilities
  of PRD §12.1, together with editions, instance types, minimum requirements,
  auth method, rate limits, event types and field mapping. A provider name is
  never a capability promise.
* verifies webhook authenticity (``verify_webhook``) with a constant-time
  comparison against the connection's secret,
* normalizes provider payloads into :class:`NormalizedEvent` records with a
  stable ``external_event_id`` (provider delivery id; if the provider sends
  none, a documented deterministic hash — see :func:`fallback_event_id`),
* performs outbound HTTP only through an injectable :class:`HttpTransport`.
  Tests inject fakes; nothing in this package opens a socket on import.

Adapters never write to the database. Services own persistence.
"""

import hashlib
import hmac
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Capability model (PRD §12.1)
# ---------------------------------------------------------------------------

CAPABILITIES = (
    "read_projects",
    "read_work_items",
    "write_work_items",
    "read_repository",
    "write_spec_branch",
    "read_merge_requests",
    "read_checks",
    "read_deployments",
    "receive_events",
    "verify_human_approval",
    "request_merge",
    "acl_discovery",
    "reconcile",
)

SUPPORTED = "supported"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"
REQUIRES_CONFIGURATION = "requires_configuration"
LEVELS = (SUPPORTED, PARTIAL, UNSUPPORTED, REQUIRES_CONFIGURATION)


@dataclass
class CapabilityDeclaration:
    provider: str
    display_name: str
    kind: str  # git | tracker
    capabilities: dict
    editions: list = field(default_factory=list)
    instance_types: list = field(default_factory=list)
    min_requirements: str = ""
    auth_methods: list = field(default_factory=list)
    webhook_auth: str = ""
    rate_limits: str = ""
    event_types: list = field(default_factory=list)
    field_mapping: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    instance_type: str = ""
    edition: str = ""

    def __post_init__(self):
        missing = [c for c in CAPABILITIES if c not in self.capabilities]
        if missing:
            raise ValueError(f"{self.provider}: capability declaration incomplete: {missing}")
        bad = {k: v for k, v in self.capabilities.items() if v not in LEVELS}
        if bad:
            raise ValueError(f"{self.provider}: invalid capability levels {bad}")

    def level(self, capability: str) -> str:
        return self.capabilities.get(capability, UNSUPPORTED)

    def is_supported(self, capability: str) -> bool:
        return self.level(capability) == SUPPORTED

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Normalized event record
# ---------------------------------------------------------------------------

# Normalized kinds. The ingress/processor only understands these.
MR_OPENED = "mr.opened"
MR_UPDATED = "mr.updated"
MR_MERGED = "mr.merged"
MR_CLOSED = "mr.closed"
CHECK = "check"  # pipeline / check run / build result
DEPLOYMENT = "deployment"
RELEASE = "release"
PUSH = "push"
ISSUE_UPDATED = "issue.updated"
UNKNOWN = "unknown"

MR_KINDS = {MR_OPENED, MR_UPDATED, MR_MERGED, MR_CLOSED}


@dataclass
class NormalizedEvent:
    provider: str
    kind: str
    external_event_id: str
    occurred_at: Optional[datetime] = None
    raw_type: str = ""
    # repository scope
    repository_external_id: str = ""
    repository_path: str = ""
    # merge request
    mr_external_id: str = ""
    mr_title: str = ""
    mr_description: str = ""
    mr_state: str = ""  # open | merged | closed
    source_branch: str = ""
    target_branch: str = ""
    head_sha: str = ""
    target_sha: str = ""
    merged_commit_sha: str = ""
    merge_method: str = ""  # merge | squash | rebase
    url: str = ""
    # commits (push / MR): [{"sha", "message", "timestamp"}]
    commits: list = field(default_factory=list)
    # check / pipeline
    check_name: str = ""
    check_status: str = ""  # passed | failed | running | cancelled | unknown
    check_kind: str = "build"  # build | test | lint
    check_id: str = ""
    # deployment / release
    environment: str = ""
    deployment_id: str = ""
    deployment_status: str = ""  # success | failed | running | cancelled
    is_rollback: bool = False
    release_tag: str = ""
    # revert (a merged MR that reverts another MR/commit)
    reverts_mr_external_id: str = ""
    reverts_commit_sha: str = ""
    # tracker issue update
    external_issue_id: str = ""
    external_issue_key: str = ""
    fields: dict = field(default_factory=dict)
    field_changed: list = field(default_factory=list)
    operation_correlation: str = ""
    # correlation hints parsed from branch/title/description/commits
    correlation: list = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat() if self.occurred_at else None
        return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_PH_RE = re.compile(r"\bPH-(" + UUID_RE + r")\b")
_WORK_ITEM_RE = re.compile(r"\bwork[-_ ]?item(?:[-_ ]?id)?\s*[:=/#]\s*(" + UUID_RE + r")", re.IGNORECASE)
# Plane sequence reference e.g. ``ABC-12`` (identifier 1..12 alnum, starting with a letter).
_SEQ_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{0,11})-(\d{1,9})(?![0-9])")
_REVERT_MR_RE = re.compile(r"reverts\s+(?:merge\s+request|pull\s+request)\s*[!#](\d+)", re.IGNORECASE)
_REVERT_COMMIT_RE = re.compile(r"reverts\s+commit\s+([0-9a-f]{7,64})", re.IGNORECASE)


def parse_references(*texts) -> list:
    """Extract work-item correlation hints.

    Recognized forms (in order of reliability):
    * ``PH-<uuid>`` and ``workItemId: <uuid>`` / ``work-item/<uuid>`` → native issue UUID
    * ``ABC-12`` → Plane project identifier + sequence id (case-insensitive,
      resolved only against projects the repository is bound to).
    """
    refs, seen = [], set()
    for text in texts:
        if not text:
            continue
        for rx in (_PH_RE, _WORK_ITEM_RE):
            for m in rx.finditer(text):
                key = ("uuid", m.group(1).lower())
                if key not in seen:
                    seen.add(key)
                    refs.append({"type": "uuid", "value": m.group(1).lower()})
        for m in _SEQ_RE.finditer(text):
            ident = m.group(1).upper()
            if ident == "PH":
                continue
            key = ("sequence", ident, int(m.group(2)))
            if key not in seen:
                seen.add(key)
                refs.append({"type": "sequence", "identifier": ident, "sequence": int(m.group(2))})
    return refs


def parse_revert(*texts):
    """Return (reverted_mr_id, reverted_commit_sha) found in a revert MR title/description."""
    mr_id, sha = "", ""
    for text in texts:
        if not text:
            continue
        m = _REVERT_MR_RE.search(text)
        if m and not mr_id:
            mr_id = m.group(1)
        m = _REVERT_COMMIT_RE.search(text)
        if m and not sha:
            sha = m.group(1).lower()
    return mr_id, sha


def fallback_event_id(provider: str, object_kind: str, object_id, updated_at, action: str) -> str:
    """Deterministic substitute when a provider sends no delivery id (MIGRATION §4).

    ``sha256(provider | object_kind | object_id | updated_at | action)``. The same
    provider object state therefore always yields the same id, so a redelivery
    is recognized as duplicate while a real later change (new ``updated_at``)
    is a new event. Timestamps alone are never used.
    """
    raw = "|".join(str(x or "") for x in (provider, object_kind, object_id, updated_at, action))
    return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def lower_headers(headers) -> dict:
    if headers is None:
        return {}
    return {str(k).lower(): v for k, v in dict(headers).items()}


def parse_time(value) -> Optional[datetime]:
    """Parse provider timestamps (ISO-8601, GitLab ``2024-01-01 10:00:00 UTC``, epoch ms)."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 10**11 else float(value)
        return datetime.fromtimestamp(seconds, tz=dt_timezone.utc)
    text = str(value).strip()
    if text.endswith(" UTC"):
        text = text[:-4].replace(" ", "T") + "+00:00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)


def hmac_sha256_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def constant_time_equals(a, b) -> bool:
    if a is None or b is None:
        return False
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


def ci_status(value) -> str:
    """Map provider CI/check results onto passed|failed|running|cancelled|unknown."""
    v = str(value or "").lower()
    if v in ("success", "succeeded", "passed", "pass", "completed_success"):
        return "passed"
    if v in ("failed", "failure", "error", "timed_out", "action_required", "partiallysucceeded"):
        return "failed"
    if v in ("running", "pending", "queued", "in_progress", "created", "waiting", "preparing", "inprogress"):
        return "running"
    if v in ("canceled", "cancelled", "skipped", "stale", "neutral", "manual"):
        return "cancelled"
    return "unknown"


# ---------------------------------------------------------------------------
# Outbound HTTP transport (injectable)
# ---------------------------------------------------------------------------


class TransportError(Exception):
    """Network failure / provider unreachable. Never carries credentials."""


class CapabilityUnsupported(Exception):
    """Raised when an adapter is asked for an operation it does not declare."""

    def __init__(self, provider, capability):
        super().__init__(f"{provider} does not support {capability}")
        self.provider = provider
        self.capability = capability


@dataclass
class HttpResponse:
    status: int
    body: Any = None
    headers: dict = field(default_factory=dict)

    @property
    def ok(self):
        return 200 <= self.status < 300


class HttpTransport:
    """Minimal interface. Implementations must never log the Authorization header."""

    def request(self, method, url, *, headers=None, params=None, json=None, timeout=None) -> HttpResponse:
        raise NotImplementedError


class RequestsTransport(HttpTransport):
    """Default transport: ``requests`` with explicit connect/read timeouts."""

    def __init__(self, timeout=(5, 20)):
        self.timeout = timeout

    def request(self, method, url, *, headers=None, params=None, json=None, timeout=None) -> HttpResponse:
        import requests

        try:
            resp = requests.request(
                method, url, headers=headers or {}, params=params, json=json, timeout=timeout or self.timeout
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            raise TransportError(f"{method} {url.split('?')[0]} failed: {type(exc).__name__}") from None
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return HttpResponse(status=resp.status_code, body=body, headers=dict(resp.headers))


_transport_override = None


def default_transport() -> HttpTransport:
    return _transport_override or RequestsTransport()


@contextmanager
def override_transport(transport):
    """Test hook: route every adapter created inside the block through ``transport``."""
    global _transport_override
    previous = _transport_override
    _transport_override = transport
    try:
        yield transport
    finally:
        _transport_override = previous


@dataclass
class ProviderContext:
    """What an adapter needs for outbound calls; built by the service from a connection row."""

    instance_url: str
    token: str = ""
    instance_type: str = "cloud"
    edition: str = ""


@dataclass
class RepoRef:
    external_id: str
    path_with_namespace: str = ""


# ---------------------------------------------------------------------------
# Adapter base
# ---------------------------------------------------------------------------


class Adapter:
    provider = ""
    display_name = ""
    kind = "git"
    # Headers that may be persisted with an inbound event (never auth/signature headers).
    safe_headers: tuple = ()

    def __init__(self, transport: Optional[HttpTransport] = None):
        self.transport = transport or default_transport()

    # -- declaration ---------------------------------------------------------
    def declare(self, *, instance_type: str = "", edition: str = "") -> CapabilityDeclaration:
        raise NotImplementedError

    # -- inbound -------------------------------------------------------------
    def verify_webhook(self, headers, body: bytes, secret: str) -> bool:
        raise NotImplementedError

    def delivery_id(self, headers, payload) -> str:
        raise NotImplementedError

    def normalize(self, headers, payload) -> list:
        raise NotImplementedError

    def persistable_headers(self, headers) -> dict:
        h = lower_headers(headers)
        return {k: h[k] for k in self.safe_headers if k in h}

    # -- outbound (optional) -------------------------------------------------
    def _unsupported(self, capability):
        raise CapabilityUnsupported(self.provider, capability)

    def fetch_merge_request(self, ctx: ProviderContext, repo: RepoRef, mr_id: str) -> dict:
        """Return ``{"head_sha", "target_sha", "state"}`` from the provider (fresh read)."""
        self._unsupported("read_merge_requests")

    def merge(self, ctx: ProviderContext, repo: RepoRef, mr_id: str, *, sha: str, squash=None) -> dict:
        """Request a merge guarded by ``sha`` (provider rejects if the head moved)."""
        self._unsupported("request_merge")

    def fetch_branch_protection(self, ctx: ProviderContext, repo: RepoRef, branch: str) -> dict:
        """Return ``{"protected": bool|None, "requires_approval": bool|None}``."""
        self._unsupported("verify_human_approval")

    def fetch_repository(self, ctx: ProviderContext, repo: RepoRef) -> dict:
        """Return ``{"external_id", "path_with_namespace", "default_branch", "head_commit"}``."""
        self._unsupported("read_repository")

    def list_tree(self, ctx: ProviderContext, repo: RepoRef, commit: str) -> list:
        self._unsupported("read_repository")

    def list_merge_requests(self, ctx: ProviderContext, repo: RepoRef, *, updated_after=None, limit=20) -> list:
        """Return normalized MR events (pull-based; used for preview and reconciliation)."""
        self._unsupported("read_merge_requests")

    def contains_commit(self, ctx: ProviderContext, repo: RepoRef, ancestor: str, descendant: str):
        """``True``/``False`` if ``ancestor`` is contained in ``descendant``; ``None`` if unknown."""
        return None

    # -- helpers -------------------------------------------------------------
    def _get(self, url, ctx, params=None):
        return self.transport.request("GET", url, headers=self.auth_headers(ctx), params=params)

    def auth_headers(self, ctx: ProviderContext) -> dict:
        return {}

    def _event(self, kind, external_event_id, **kwargs) -> NormalizedEvent:
        return NormalizedEvent(provider=self.provider, kind=kind, external_event_id=external_event_id, **kwargs)

    @staticmethod
    def split_multi(events, delivery_id):
        """Give each normalized event of one delivery a stable, distinct id."""
        if len(events) <= 1:
            for ev in events:
                ev.external_event_id = delivery_id
            return events
        for idx, ev in enumerate(events):
            ev.external_event_id = f"{delivery_id}#{idx}"
        return events


def strip_ref(ref: str) -> str:
    ref = ref or ""
    for prefix in ("refs/heads/", "refs/tags/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref
