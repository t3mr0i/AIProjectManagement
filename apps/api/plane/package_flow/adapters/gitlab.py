# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GitLab adapter (GitLab.com and self-managed; REST API v4, webhooks).

Webhook authentication: GitLab sends the configured secret token verbatim in
``X-Gitlab-Token``; it is compared in constant time.

Delivery id: ``Idempotency-Key`` (GitLab ≥ 17.x, stable across retries) or
``X-Gitlab-Event-UUID``; otherwise :func:`fallback_event_id` over
project/object/updated_at/action.

Not verified against a live GitLab instance in this repository; payload
shapes follow the public webhook documentation and are covered by fixtures.
"""

from urllib.parse import quote

from .base import (
    CHECK,
    DEPLOYMENT,
    MR_CLOSED,
    MR_MERGED,
    MR_OPENED,
    MR_UPDATED,
    PARTIAL,
    PUSH,
    RELEASE,
    REQUIRES_CONFIGURATION,
    SUPPORTED,
    UNKNOWN,
    UNSUPPORTED,
    Adapter,
    CapabilityDeclaration,
    ci_status,
    constant_time_equals,
    fallback_event_id,
    lower_headers,
    parse_references,
    parse_revert,
    parse_time,
)

PREMIUM_EDITIONS = {"premium", "ultimate", "ee_premium", "ee_ultimate"}


class GitLabAdapter(Adapter):
    provider = "gitlab"
    display_name = "GitLab"
    kind = "git"
    safe_headers = (
        "x-gitlab-event",
        "x-gitlab-event-uuid",
        "x-gitlab-webhook-uuid",
        "idempotency-key",
        "x-gitlab-instance",
    )

    def declare(self, *, instance_type="", edition=""):
        edition_l = (edition or "").lower()
        approval_level = SUPPORTED if edition_l in PREMIUM_EDITIONS else PARTIAL
        return CapabilityDeclaration(
            provider=self.provider,
            display_name=self.display_name,
            kind=self.kind,
            instance_type=instance_type,
            edition=edition,
            capabilities={
                "read_projects": SUPPORTED,
                "read_work_items": PARTIAL,
                "write_work_items": UNSUPPORTED,
                "read_repository": SUPPORTED,
                "write_spec_branch": REQUIRES_CONFIGURATION,
                "read_merge_requests": SUPPORTED,
                "read_checks": SUPPORTED,
                "read_deployments": SUPPORTED,
                "receive_events": SUPPORTED,
                "verify_human_approval": approval_level,
                "request_merge": SUPPORTED,
                "acl_discovery": PARTIAL,
                "reconcile": SUPPORTED,
            },
            editions=["free", "premium", "ultimate"],
            instance_types=["cloud", "self_managed", "dedicated"],
            min_requirements=(
                "GitLab 16.0+ REST API v4; token with read_api (merge additionally needs api scope). "
                "Merge-approval rules require Premium/Ultimate; Free only offers protected branches."
            ),
            auth_methods=["personal_access_token", "project_access_token", "group_access_token", "oauth2"],
            webhook_auth="X-Gitlab-Token shared secret (constant-time compare)",
            rate_limits=(
                "GitLab.com: authenticated API ~2,000 requests/min per user; self-managed limits "
                "are set by the instance admin. HTTP 429 + RateLimit-* headers."
            ),
            event_types=[
                "Merge Request Hook",
                "Pipeline Hook",
                "Job Hook",
                "Push Hook",
                "Deployment Hook",
                "Release Hook",
            ],
            field_mapping={
                "merge_request.id": "object_attributes.iid (project-scoped)",
                "merge_request.head_sha": "object_attributes.last_commit.id",
                "merge_request.merged_commit_sha": "merge_commit_sha | squash_commit_sha (fast-forward)",
                "check.status": "object_attributes.status",
                "deployment.environment": "environment",
            },
            notes=[
                "Cloud and self-managed editions must be tested separately (PRD §12.2).",
                "A platform approval alone does not protect an unprotected target branch.",
            ],
        )

    # -- inbound -------------------------------------------------------------
    def verify_webhook(self, headers, body, secret):
        if not secret:
            return False
        return constant_time_equals(lower_headers(headers).get("x-gitlab-token"), secret)

    def delivery_id(self, headers, payload):
        h = lower_headers(headers)
        explicit = h.get("idempotency-key") or h.get("x-gitlab-event-uuid")
        if explicit:
            return f"gitlab:{explicit}"
        attrs = payload.get("object_attributes") or {}
        object_id = attrs.get("id") or payload.get("deployment_id") or payload.get("checkout_sha")
        return fallback_event_id(
            self.provider,
            payload.get("object_kind"),
            f"{(payload.get('project') or {}).get('id')}:{object_id}",
            attrs.get("updated_at") or payload.get("status_changed_at") or payload.get("after"),
            attrs.get("action") or attrs.get("status") or payload.get("status"),
        )

    def normalize(self, headers, payload):
        kind = payload.get("object_kind") or payload.get("event_type") or ""
        project = payload.get("project") or {}
        repo_id = str(project.get("id") or payload.get("project_id") or "")
        repo_path = project.get("path_with_namespace") or ""
        delivery = self.delivery_id(headers, payload)
        events = []
        if kind == "merge_request":
            events.append(self._mr(payload, repo_id, repo_path, delivery))
        elif kind == "pipeline":
            attrs = payload.get("object_attributes") or {}
            mr = payload.get("merge_request") or {}
            events.append(
                self._event(
                    CHECK,
                    delivery,
                    raw_type="Pipeline Hook",
                    occurred_at=parse_time(attrs.get("finished_at") or attrs.get("created_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=attrs.get("sha") or "",
                    source_branch=attrs.get("ref") or "",
                    mr_external_id=str(mr.get("iid") or ""),
                    check_name=attrs.get("name") or "pipeline",
                    check_kind="build",
                    check_status=ci_status(attrs.get("status")),
                    check_id=f"pipeline:{attrs.get('id')}",
                    url=attrs.get("url") or "",
                )
            )
        elif kind == "build":
            name = payload.get("build_name") or "job"
            events.append(
                self._event(
                    CHECK,
                    delivery,
                    raw_type="Job Hook",
                    occurred_at=parse_time(payload.get("build_finished_at") or payload.get("build_started_at")),
                    repository_external_id=repo_id or str(payload.get("project_id") or ""),
                    repository_path=repo_path,
                    head_sha=payload.get("sha") or "",
                    source_branch=payload.get("ref") or "",
                    check_name=name,
                    check_kind="test" if "test" in name.lower() else ("lint" if "lint" in name.lower() else "build"),
                    check_status=ci_status(payload.get("build_status")),
                    check_id=f"job:{payload.get('build_id')}",
                )
            )
        elif kind == "push":
            commits = [
                {"sha": c.get("id"), "message": c.get("message") or "", "timestamp": c.get("timestamp")}
                for c in payload.get("commits") or []
            ]
            branch = (payload.get("ref") or "").replace("refs/heads/", "")
            events.append(
                self._event(
                    PUSH,
                    delivery,
                    raw_type="Push Hook",
                    occurred_at=parse_time(commits[-1]["timestamp"]) if commits else None,
                    repository_external_id=repo_id or str(payload.get("project_id") or ""),
                    repository_path=repo_path,
                    source_branch=branch,
                    head_sha=payload.get("after") or payload.get("checkout_sha") or "",
                    commits=commits,
                    correlation=parse_references(branch, *[c["message"] for c in commits]),
                )
            )
        elif kind == "deployment":
            status = str(payload.get("status") or "").lower()
            events.append(
                self._event(
                    DEPLOYMENT,
                    delivery,
                    raw_type="Deployment Hook",
                    occurred_at=parse_time(payload.get("status_changed_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=payload.get("sha") or "",
                    source_branch=payload.get("ref") or "",
                    environment=payload.get("environment") or "",
                    deployment_id=str(payload.get("deployment_id") or ""),
                    deployment_status="success" if status == "success" else status,
                    url=payload.get("deployable_url") or "",
                )
            )
        elif kind == "release":
            commit = payload.get("commit") or {}
            events.append(
                self._event(
                    RELEASE,
                    delivery,
                    raw_type="Release Hook",
                    occurred_at=parse_time(payload.get("released_at") or payload.get("created_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=commit.get("id") or "",
                    release_tag=payload.get("tag") or "",
                    url=payload.get("url") or "",
                )
            )
        else:
            events.append(self._event(UNKNOWN, delivery, raw_type=str(kind), repository_external_id=repo_id))
        return self.split_multi(events, delivery)

    def _mr(self, payload, repo_id, repo_path, delivery):
        attrs = payload.get("object_attributes") or {}
        action = attrs.get("action") or ""
        state = attrs.get("state") or ""
        last_commit = attrs.get("last_commit") or {}
        if state == "merged" or action == "merge":
            kind, mr_state = MR_MERGED, "merged"
        elif state == "closed" or action == "close":
            kind, mr_state = MR_CLOSED, "closed"
        elif action == "open":
            kind, mr_state = MR_OPENED, "open"
        else:
            kind, mr_state = MR_UPDATED, "open"
        squash = bool(attrs.get("squash"))
        merged_sha = ""
        method = ""
        if mr_state == "merged":
            merged_sha = attrs.get("merge_commit_sha") or attrs.get("squash_commit_sha") or ""
            if squash:
                method = "squash"
            elif attrs.get("merge_commit_sha"):
                method = "merge"
            else:
                method = "fast_forward"
                merged_sha = merged_sha or last_commit.get("id") or ""
        title = attrs.get("title") or ""
        description = attrs.get("description") or ""
        reverts_mr, reverts_sha = parse_revert(title, description)
        commits = []
        if last_commit.get("id"):
            commits.append(
                {
                    "sha": last_commit.get("id"),
                    "message": last_commit.get("message") or "",
                    "timestamp": last_commit.get("timestamp"),
                }
            )
        return self._event(
            kind,
            delivery,
            raw_type=f"Merge Request Hook:{action}",
            occurred_at=parse_time(attrs.get("updated_at") or attrs.get("merged_at")),
            repository_external_id=str(attrs.get("target_project_id") or repo_id),
            repository_path=repo_path,
            mr_external_id=str(attrs.get("iid") or ""),
            mr_title=title,
            mr_description=description,
            mr_state=mr_state,
            source_branch=attrs.get("source_branch") or "",
            target_branch=attrs.get("target_branch") or "",
            head_sha=last_commit.get("id") or "",
            merged_commit_sha=merged_sha,
            merge_method=method,
            url=attrs.get("url") or "",
            commits=commits,
            reverts_mr_external_id=reverts_mr,
            reverts_commit_sha=reverts_sha,
            correlation=parse_references(attrs.get("source_branch"), title, description),
        )

    # -- outbound ------------------------------------------------------------
    def _api(self, ctx):
        return ctx.instance_url.rstrip("/") + "/api/v4"

    def auth_headers(self, ctx):
        return {"PRIVATE-TOKEN": ctx.token} if ctx.token else {}

    def _project(self, repo):
        return quote(str(repo.external_id or repo.path_with_namespace), safe="")

    def fetch_merge_request(self, ctx, repo, mr_id):
        resp = self._get(f"{self._api(ctx)}/projects/{self._project(repo)}/merge_requests/{quote(str(mr_id))}", ctx)
        if not resp.ok:
            return {"ok": False, "status": resp.status}
        body = resp.body or {}
        diff_refs = body.get("diff_refs") or {}
        state = body.get("state")
        return {
            "ok": True,
            "head_sha": body.get("sha") or diff_refs.get("head_sha") or "",
            "target_sha": diff_refs.get("start_sha") or "",
            "state": "open" if state == "opened" else state,
            "target_branch": body.get("target_branch") or "",
        }

    def merge(self, ctx, repo, mr_id, *, sha, squash=None):
        payload = {"sha": sha}
        if squash is not None:
            payload["squash"] = bool(squash)
        resp = self.transport.request(
            "PUT",
            f"{self._api(ctx)}/projects/{self._project(repo)}/merge_requests/{quote(str(mr_id))}/merge",
            headers=self.auth_headers(ctx),
            json=payload,
        )
        body = resp.body if isinstance(resp.body, dict) else {}
        return {
            "accepted": resp.ok,
            "status": resp.status,
            # GitLab answers 409 when ``sha`` no longer matches the source branch head.
            "head_mismatch": resp.status == 409,
            "state": body.get("state", ""),
            "merged_commit_sha": body.get("merge_commit_sha") or body.get("squash_commit_sha") or "",
        }

    def fetch_branch_protection(self, ctx, repo, branch):
        resp = self._get(
            f"{self._api(ctx)}/projects/{self._project(repo)}/protected_branches/{quote(branch, safe='')}", ctx
        )
        if resp.status == 404:
            protected = False
        elif resp.ok:
            protected = True
        else:
            protected = None
        requires_approval = None
        rules = self._get(f"{self._api(ctx)}/projects/{self._project(repo)}/approval_rules", ctx)
        if rules.ok and isinstance(rules.body, list):
            requires_approval = any((r.get("approvals_required") or 0) > 0 for r in rules.body)
        return {"protected": protected, "requires_approval": requires_approval}

    def fetch_repository(self, ctx, repo):
        resp = self._get(f"{self._api(ctx)}/projects/{self._project(repo)}", ctx)
        if not resp.ok:
            return {"ok": False, "status": resp.status}
        body = resp.body or {}
        branch = body.get("default_branch") or "main"
        head = ""
        commit = self._get(
            f"{self._api(ctx)}/projects/{self._project(repo)}/repository/commits/{quote(branch, safe='')}", ctx
        )
        if commit.ok and isinstance(commit.body, dict):
            head = commit.body.get("id") or ""
        return {
            "ok": True,
            "external_id": str(body.get("id") or repo.external_id),
            "path_with_namespace": body.get("path_with_namespace") or repo.path_with_namespace,
            "default_branch": branch,
            "head_commit": head,
        }

    def list_tree(self, ctx, repo, commit):
        resp = self._get(
            f"{self._api(ctx)}/projects/{self._project(repo)}/repository/tree",
            ctx,
            params={"ref": commit, "recursive": "true", "per_page": 100},
        )
        if not resp.ok or not isinstance(resp.body, list):
            return []
        return [item.get("path") for item in resp.body if item.get("type") == "blob"]

    def list_merge_requests(self, ctx, repo, *, updated_after=None, limit=20):
        params = {"order_by": "updated_at", "sort": "desc", "per_page": limit, "scope": "all"}
        if updated_after:
            params["updated_after"] = updated_after.isoformat()
        resp = self._get(f"{self._api(ctx)}/projects/{self._project(repo)}/merge_requests", ctx, params=params)
        if not resp.ok or not isinstance(resp.body, list):
            return []
        events = []
        for mr in resp.body:
            attrs = {
                "iid": mr.get("iid"),
                "id": mr.get("id"),
                "title": mr.get("title"),
                "description": mr.get("description"),
                "state": mr.get("state"),
                "action": "merge" if mr.get("state") == "merged" else "update",
                "source_branch": mr.get("source_branch"),
                "target_branch": mr.get("target_branch"),
                "last_commit": {"id": mr.get("sha")},
                "merge_commit_sha": mr.get("merge_commit_sha"),
                "squash_commit_sha": mr.get("squash_commit_sha"),
                "squash": mr.get("squash"),
                "updated_at": mr.get("updated_at"),
                "url": mr.get("web_url"),
                "target_project_id": mr.get("target_project_id") or repo.external_id,
            }
            ev_id = fallback_event_id(
                self.provider,
                "merge_request",
                f"{repo.external_id}:{mr.get('iid')}",
                mr.get("updated_at"),
                mr.get("state"),
            )
            events.append(
                self._mr({"object_attributes": attrs}, str(repo.external_id), repo.path_with_namespace, ev_id)
            )
        return events

    def contains_commit(self, ctx, repo, ancestor, descendant):
        if not ancestor or not descendant:
            return None
        if ancestor == descendant:
            return True
        resp = self._get(
            f"{self._api(ctx)}/projects/{self._project(repo)}/repository/merge_base",
            ctx,
            params=[("refs[]", ancestor), ("refs[]", descendant)],
        )
        if not resp.ok or not isinstance(resp.body, dict):
            return None
        return (resp.body.get("id") or "") == ancestor
