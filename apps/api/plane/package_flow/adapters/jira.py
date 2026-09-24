# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira adapter (tracker profile; Jira Cloud and Data Center are separate profiles).

Webhook authentication — documented assumption: the webhook is registered
with a shared secret and Jira sends ``X-Hub-Signature: sha256=<hex>`` (HMAC-
SHA256 over the raw body), as Jira Cloud does for admin-registered webhooks
with a secret. Jira Data Center deployments without signing support must put
a reverse proxy in front that adds the same header; unsigned deliveries are
rejected (401). JWT-authenticated Connect app webhooks are not supported.

Delivery id: ``X-Atlassian-Webhook-Identifier`` (stable across retries);
otherwise the deterministic hash of issue id + ``fields.updated`` + event +
changelog id.

Git capabilities are ``unsupported``: Jira is a tracker, not a code host.
"""

from urllib.parse import quote

from .base import (
    ISSUE_UPDATED,
    PARTIAL,
    REQUIRES_CONFIGURATION,
    SUPPORTED,
    UNKNOWN,
    UNSUPPORTED,
    Adapter,
    CapabilityDeclaration,
    constant_time_equals,
    fallback_event_id,
    hmac_sha256_hex,
    lower_headers,
    parse_time,
)

# Jira priority names → Plane priorities.
PRIORITY_MAP = {
    "highest": "urgent",
    "blocker": "urgent",
    "critical": "urgent",
    "high": "high",
    "major": "high",
    "medium": "medium",
    "low": "low",
    "minor": "low",
    "lowest": "low",
    "trivial": "low",
}

FIELD_MAP = {"priority": "priority", "summary": "title", "status": "status"}


# Plane priority -> Jira priority name (``none`` is never pushed).
REVERSE_PRIORITY = {"urgent": "Highest", "high": "High", "medium": "Medium", "low": "Low"}


def map_priority(name):
    if not name:
        return None
    return PRIORITY_MAP.get(str(name).strip().lower(), "none")


class JiraAdapter(Adapter):
    provider = "jira"
    display_name = "Jira"
    kind = "tracker"
    safe_headers = ("x-atlassian-webhook-identifier", "x-atlassian-webhook-retry")

    def declare(self, *, instance_type="", edition=""):
        return CapabilityDeclaration(
            provider=self.provider,
            display_name=self.display_name,
            kind=self.kind,
            instance_type=instance_type,
            edition=edition,
            capabilities={
                "read_projects": SUPPORTED,
                "read_work_items": SUPPORTED,
                "write_work_items": PARTIAL,
                "read_repository": UNSUPPORTED,
                "write_spec_branch": UNSUPPORTED,
                "read_merge_requests": UNSUPPORTED,
                "read_checks": UNSUPPORTED,
                "read_deployments": UNSUPPORTED,
                "receive_events": REQUIRES_CONFIGURATION,
                "verify_human_approval": UNSUPPORTED,
                "request_merge": UNSUPPORTED,
                "acl_discovery": PARTIAL,
                "reconcile": PARTIAL,
            },
            editions=["cloud", "data_center"],
            instance_types=["cloud", "data_center"],
            min_requirements=(
                "Jira Cloud REST v3 or Data Center REST v2 (separate profiles). Webhook with shared secret "
                "(X-Hub-Signature); Data Center requires a signing proxy. Field mapping per project."
            ),
            auth_methods=["oauth2_3lo", "api_token_basic", "personal_access_token_dc"],
            webhook_auth="X-Hub-Signature: sha256=<HMAC-SHA256 hex> (shared secret; documented assumption)",
            rate_limits=(
                "Jira Cloud: cost/points-based limits, HTTP 429 with Retry-After; Data Center: admin-configured."
            ),
            event_types=["jira:issue_created", "jira:issue_updated", "comment_created"],
            field_mapping={
                "priority": "fields.priority.name → urgent|high|medium|low|none",
                "title": "fields.summary",
                "status": "fields.status.name (observation only; never an execution approval)",
            },
            notes=["Not a complete workflow replacement (PRD §12.2).", "Write-back limited to mapped fields."],
        )

    def verify_webhook(self, headers, body, secret):
        if not secret:
            return False
        sig = lower_headers(headers).get("x-hub-signature") or ""
        if not sig.startswith("sha256="):
            return False
        return constant_time_equals(sig[len("sha256=") :], hmac_sha256_hex(secret, body))

    def delivery_id(self, headers, payload):
        h = lower_headers(headers)
        if h.get("x-atlassian-webhook-identifier"):
            return f"jira:{h['x-atlassian-webhook-identifier']}"
        issue = payload.get("issue") or {}
        return fallback_event_id(
            self.provider,
            "issue",
            issue.get("id"),
            (issue.get("fields") or {}).get("updated") or payload.get("timestamp"),
            f"{payload.get('webhookEvent')}:{(payload.get('changelog') or {}).get('id')}",
        )

    def normalize(self, headers, payload):
        delivery = self.delivery_id(headers, payload)
        event = payload.get("webhookEvent") or ""
        issue = payload.get("issue") or {}
        if not event.startswith("jira:issue_") or not issue:
            return [self._event(UNKNOWN, delivery, raw_type=event)]
        fields = issue.get("fields") or {}
        values = {
            "priority": map_priority((fields.get("priority") or {}).get("name")),
            "title": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
        }
        changelog = payload.get("changelog") or {}
        changed = [FIELD_MAP[i.get("field")] for i in changelog.get("items") or [] if i.get("field") in FIELD_MAP]
        if changed:
            values = {k: v for k, v in values.items() if k in changed}
        values = {k: v for k, v in values.items() if v is not None}
        occurred = parse_time(fields.get("updated")) or parse_time(payload.get("timestamp"))
        return [
            self._event(
                ISSUE_UPDATED,
                delivery,
                raw_type=event,
                occurred_at=occurred,
                external_issue_id=str(issue.get("id") or ""),
                external_issue_key=issue.get("key") or "",
                fields=values,
                field_changed=changed,
                url=issue.get("self") or "",
            )
        ]

    # -- outbound (bounded write-back, I12) -----------------------------------
    def auth_headers(self, ctx):
        if not ctx.token:
            return {}
        # Cloud: "email:api_token" -> Basic; Data Center PAT -> Bearer.
        if ":" in ctx.token:
            import base64

            return {"Authorization": "Basic " + base64.b64encode(ctx.token.encode()).decode("ascii")}
        return {"Authorization": f"Bearer {ctx.token}"}

    def update_work_item(self, ctx, external_id, fields, *, op_id=""):
        payload, pushed = {}, {}
        if fields.get("title"):
            payload["summary"] = fields["title"]
            pushed["title"] = fields["title"]
        if fields.get("priority") in REVERSE_PRIORITY:
            payload["priority"] = {"name": REVERSE_PRIORITY[fields["priority"]]}
            pushed["priority"] = payload["priority"]["name"]
        if not payload:
            return {"ok": True, "status": 204, "pushed": {}}
        api = "3" if (ctx.instance_type or "cloud") == "cloud" else "2"
        resp = self.transport.request(
            "PUT",
            f"{ctx.instance_url.rstrip('/')}/rest/api/{api}/issue/{quote(str(external_id), safe='')}",
            headers={**self.auth_headers(ctx), "Content-Type": "application/json"},
            json={"fields": payload},
        )
        return {"ok": resp.ok, "status": resp.status, "pushed": pushed}
