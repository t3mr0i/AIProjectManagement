# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Generic Git adapter (plain Git remote without hosting/CI API; PRD §12.2).

Only repository/spec roundtrip through an approved Git credential. Without a
hosting or CI API there are **no** claimed review, check or deployment signals:
``read_checks``, ``read_deployments``, ``verify_human_approval`` and
``request_merge`` are ``unsupported``.

Events are optional: a customer-installed ``post-receive`` hook may POST a
push summary signed with ``X-Signature-256: sha256=<hex HMAC-SHA256(body)>``
(``requires_configuration``). Delivery id: ``X-Delivery-Id`` or the
deterministic hash of repository + ref + new head.
"""

from .base import (
    PARTIAL,
    PUSH,
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
    parse_references,
    parse_time,
    strip_ref,
)


class GenericGitAdapter(Adapter):
    provider = "generic_git"
    display_name = "Generic Git"
    kind = "git"
    safe_headers = ("x-delivery-id",)

    def declare(self, *, instance_type="", edition=""):
        return CapabilityDeclaration(
            provider=self.provider,
            display_name=self.display_name,
            kind=self.kind,
            instance_type=instance_type or "self_hosted",
            edition=edition,
            capabilities={
                "read_projects": UNSUPPORTED,
                "read_work_items": UNSUPPORTED,
                "write_work_items": UNSUPPORTED,
                "read_repository": SUPPORTED,
                "write_spec_branch": REQUIRES_CONFIGURATION,
                "read_merge_requests": UNSUPPORTED,
                "read_checks": UNSUPPORTED,
                "read_deployments": UNSUPPORTED,
                "receive_events": REQUIRES_CONFIGURATION,
                "verify_human_approval": UNSUPPORTED,
                "request_merge": UNSUPPORTED,
                "acl_discovery": UNSUPPORTED,
                "reconcile": PARTIAL,
            },
            editions=["any"],
            instance_types=["self_hosted", "cloud"],
            min_requirements="Git smart HTTP/SSH remote and an approved credential; optional signed post-receive hook.",
            auth_methods=["ssh_deploy_key", "https_token"],
            webhook_auth="X-Signature-256: sha256=<HMAC-SHA256 hex> from a customer post-receive hook (optional)",
            rate_limits="Defined by the Git server; no API calls are made by this adapter.",
            event_types=["push"],
            field_mapping={"push.commits": "commits[].{id,message,timestamp}"},
            notes=["Without hosting/CI API there are no claimed review or deployment proofs (PRD §12.2)."],
        )

    def verify_webhook(self, headers, body, secret):
        if not secret:
            return False
        sig = lower_headers(headers).get("x-signature-256") or ""
        if not sig.startswith("sha256="):
            return False
        return constant_time_equals(sig[len("sha256=") :], hmac_sha256_hex(secret, body))

    def delivery_id(self, headers, payload):
        h = lower_headers(headers)
        if h.get("x-delivery-id"):
            return f"git:{h['x-delivery-id']}"
        repo = payload.get("repository") or {}
        return fallback_event_id(
            self.provider, "push", f"{repo.get('id')}:{payload.get('ref')}", payload.get("after"), "push"
        )

    def normalize(self, headers, payload):
        delivery = self.delivery_id(headers, payload)
        if not payload.get("ref") or not payload.get("after"):
            return [self._event(UNKNOWN, delivery, raw_type="unknown")]
        repo = payload.get("repository") or {}
        commits = [
            {"sha": c.get("id"), "message": c.get("message") or "", "timestamp": c.get("timestamp")}
            for c in payload.get("commits") or []
        ]
        branch = strip_ref(payload.get("ref"))
        return [
            self._event(
                PUSH,
                delivery,
                raw_type="push",
                occurred_at=parse_time(commits[-1]["timestamp"]) if commits else None,
                repository_external_id=str(repo.get("id") or ""),
                repository_path=repo.get("path") or "",
                source_branch=branch,
                head_sha=payload.get("after") or "",
                commits=commits,
                correlation=parse_references(branch, *[c["message"] for c in commits]),
            )
        ]
