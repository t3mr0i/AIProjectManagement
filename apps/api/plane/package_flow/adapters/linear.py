# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Linear adapter (tracker profile; GraphQL API, webhooks).

Webhook authentication: ``Linear-Signature`` = hex HMAC-SHA256 of the raw body
with the webhook signing secret (constant-time compare).
Delivery id: ``Linear-Delivery`` header; fallback hash of issue id +
``updatedAt`` + action.

A Linear agent feature is not assumed for the core (PRD §12.2).
"""

from .base import (
    ISSUE_UPDATED,
    PARTIAL,
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

# Linear priority integers → Plane priorities (0 = no priority).
PRIORITY_MAP = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}
REVERSE_PRIORITY = {v: k for k, v in PRIORITY_MAP.items()}
GRAPHQL_URL = "https://api.linear.app/graphql"
ISSUE_UPDATE = "mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input) { success } }"


class LinearAdapter(Adapter):
    provider = "linear"
    display_name = "Linear"
    kind = "tracker"
    safe_headers = ("linear-delivery", "linear-event")

    def declare(self, *, instance_type="", edition=""):
        return CapabilityDeclaration(
            provider=self.provider,
            display_name=self.display_name,
            kind=self.kind,
            instance_type=instance_type or "cloud",
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
                "receive_events": SUPPORTED,
                "verify_human_approval": UNSUPPORTED,
                "request_merge": UNSUPPORTED,
                "acl_discovery": PARTIAL,
                "reconcile": PARTIAL,
            },
            editions=["free", "basic", "business", "enterprise"],
            instance_types=["cloud"],
            min_requirements="Linear GraphQL API with OAuth app or personal API key; webhook with signing secret.",
            auth_methods=["oauth2", "api_key"],
            webhook_auth="Linear-Signature: hex HMAC-SHA256 over the raw body",
            rate_limits=(
                "Request- and complexity-based limits per API key/app; HTTP 400/429 RATELIMITED with reset headers."
            ),
            event_types=["Issue:create", "Issue:update", "Issue:remove", "Comment:create"],
            field_mapping={
                "priority": "data.priority 0..4 → none|urgent|high|medium|low",
                "title": "data.title",
                "status": "data.state.name (observation only)",
            },
            notes=["Agent features of Linear are not a prerequisite."],
        )

    def verify_webhook(self, headers, body, secret):
        if not secret:
            return False
        sig = lower_headers(headers).get("linear-signature")
        return constant_time_equals(sig, hmac_sha256_hex(secret, body))

    def delivery_id(self, headers, payload):
        h = lower_headers(headers)
        if h.get("linear-delivery"):
            return f"linear:{h['linear-delivery']}"
        data = payload.get("data") or {}
        return fallback_event_id(
            self.provider, payload.get("type"), data.get("id"), data.get("updatedAt"), payload.get("action")
        )

    def normalize(self, headers, payload):
        delivery = self.delivery_id(headers, payload)
        if payload.get("type") != "Issue" or payload.get("action") not in ("create", "update"):
            return [self._event(UNKNOWN, delivery, raw_type=f"{payload.get('type')}:{payload.get('action')}")]
        data = payload.get("data") or {}
        values = {
            "priority": PRIORITY_MAP.get(data.get("priority")) if data.get("priority") is not None else None,
            "title": data.get("title"),
            "status": (data.get("state") or {}).get("name"),
        }
        updated_from = payload.get("updatedFrom") or {}
        linear_to_canonical = {"priority": "priority", "title": "title", "stateId": "status"}
        changed = [linear_to_canonical[k] for k in updated_from if k in linear_to_canonical]
        if changed:
            values = {k: v for k, v in values.items() if k in changed}
        values = {k: v for k, v in values.items() if v is not None}
        return [
            self._event(
                ISSUE_UPDATED,
                delivery,
                raw_type=f"Issue:{payload.get('action')}",
                occurred_at=parse_time(data.get("updatedAt") or payload.get("createdAt")),
                external_issue_id=str(data.get("id") or ""),
                external_issue_key=data.get("identifier") or "",
                fields=values,
                field_changed=changed,
                url=payload.get("url") or data.get("url") or "",
            )
        ]

    # -- outbound (bounded write-back, I12) -----------------------------------
    def auth_headers(self, ctx):
        # API keys are sent verbatim; OAuth tokens as Bearer.
        if not ctx.token:
            return {}
        return {"Authorization": ctx.token if ctx.token.startswith("lin_api_") else f"Bearer {ctx.token}"}

    def update_work_item(self, ctx, external_id, fields, *, op_id=""):
        data = {}
        if fields.get("title"):
            data["title"] = fields["title"]
        if fields.get("priority") in REVERSE_PRIORITY:
            data["priority"] = REVERSE_PRIORITY[fields["priority"]]
        if not data:
            return {"ok": True, "status": 204, "pushed": {}}
        resp = self.transport.request(
            "POST",
            GRAPHQL_URL,
            headers={**self.auth_headers(ctx), "Content-Type": "application/json"},
            json={"query": ISSUE_UPDATE, "variables": {"id": str(external_id), "input": data}},
        )
        body = resp.body if isinstance(resp.body, dict) else {}
        success = bool(((body.get("data") or {}).get("issueUpdate") or {}).get("success"))
        return {"ok": resp.ok and success and not body.get("errors"), "status": resp.status, "pushed": data}
