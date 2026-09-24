# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GitHub adapter (github.com and GitHub Enterprise Server; REST v3, webhooks).

Plane upstream already ships GitHub models (``GithubRepository``,
``GithubRepositorySync``, ``GithubIssueSync``, ``GithubCommentSync``) for its
legacy importer. This adapter does not replace them: it only covers the
package-flow delivery signals (PRs, checks, deployments) and declares issue
sync as ``partial`` (upstream importer) / write as ``unsupported``.

Webhook authentication: ``X-Hub-Signature-256: sha256=<hex HMAC-SHA256(body)>``.
Delivery id: ``X-GitHub-Delivery`` (kept on redelivery).
Rollback signal: a deployment whose ``task`` is ``deploy:rollback`` or whose
``payload.rollback`` is truthy (convention — GitHub has no native rollback flag).
"""

import re
from urllib.parse import quote, urlparse

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
    hmac_sha256_hex,
    lower_headers,
    parse_references,
    parse_revert,
    parse_time,
    strip_ref,
)

PAID_EDITIONS = {"team", "enterprise", "enterprise_cloud", "enterprise_server", "ghes"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GitHubAdapter(Adapter):
    provider = "github"
    display_name = "GitHub"
    kind = "git"
    safe_headers = ("x-github-event", "x-github-delivery", "x-github-hook-id")

    def declare(self, *, instance_type="", edition=""):
        approval = SUPPORTED if (edition or "").lower() in PAID_EDITIONS else PARTIAL
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
                "verify_human_approval": approval,
                "request_merge": SUPPORTED,
                "acl_discovery": PARTIAL,
                "reconcile": SUPPORTED,
            },
            editions=["free", "team", "enterprise_cloud", "enterprise_server"],
            instance_types=["cloud", "enterprise_server"],
            min_requirements=(
                "GitHub App or fine-grained token with pull_requests, checks, deployments read; "
                "contents:write for merge; administration:read to verify branch protection. "
                "Branch protection on private repos needs a paid plan."
            ),
            auth_methods=["github_app", "fine_grained_token", "oauth"],
            webhook_auth="X-Hub-Signature-256 HMAC-SHA256 over the raw body",
            rate_limits=(
                "REST: 5,000 requests/hour per user token (higher for GitHub Apps on Enterprise "
                "Cloud); secondary rate limits apply. HTTP 403/429 with Retry-After."
            ),
            event_types=["pull_request", "check_run", "workflow_run", "status", "push", "deployment_status", "release"],
            field_mapping={
                "merge_request.id": "pull_request.number",
                "merge_request.head_sha": "pull_request.head.sha",
                "merge_request.merged_commit_sha": "pull_request.merge_commit_sha (squash commit for squash merges)",
                "check.status": "check_run.conclusion | workflow_run.conclusion | status.state",
                "deployment.environment": "deployment_status.environment",
            },
            notes=[
                "Upstream Plane GitHub importer models exist; issue sync is not driven by this adapter.",
            ],
        )

    # -- inbound -------------------------------------------------------------
    def verify_webhook(self, headers, body, secret):
        if not secret:
            return False
        sig = lower_headers(headers).get("x-hub-signature-256") or ""
        if not sig.startswith("sha256="):
            return False
        return constant_time_equals(sig[len("sha256=") :], hmac_sha256_hex(secret, body))

    def delivery_id(self, headers, payload):
        h = lower_headers(headers)
        if h.get("x-github-delivery"):
            return f"github:{h['x-github-delivery']}"
        pr = payload.get("pull_request") or {}
        return fallback_event_id(
            self.provider,
            h.get("x-github-event"),
            f"{(payload.get('repository') or {}).get('id')}:{pr.get('number') or payload.get('after') or ''}",
            pr.get("updated_at") or payload.get("updated_at"),
            payload.get("action"),
        )

    def normalize(self, headers, payload):
        h = lower_headers(headers)
        gh_event = h.get("x-github-event") or ""
        repo = payload.get("repository") or {}
        repo_id = str(repo.get("id") or "")
        repo_path = repo.get("full_name") or ""
        delivery = self.delivery_id(headers, payload)
        events = []
        if gh_event == "pull_request":
            events.append(
                self._pr(payload.get("pull_request") or {}, payload.get("action") or "", repo_id, repo_path, delivery)
            )
        elif gh_event in ("check_run", "workflow_run"):
            obj = payload.get(gh_event) or {}
            prs = obj.get("pull_requests") or []
            if obj.get("status") == "completed":
                status = ci_status(obj.get("conclusion"))
            else:
                status = ci_status(obj.get("status"))
            name = obj.get("name") or gh_event
            events.append(
                self._event(
                    CHECK,
                    delivery,
                    raw_type=gh_event,
                    occurred_at=parse_time(obj.get("completed_at") or obj.get("updated_at") or obj.get("started_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=obj.get("head_sha") or "",
                    source_branch=obj.get("head_branch") or "",
                    mr_external_id=str(prs[0].get("number")) if prs else "",
                    check_name=name,
                    check_kind="test" if "test" in name.lower() else "build",
                    check_status=status,
                    check_id=f"{gh_event}:{obj.get('id')}",
                    url=obj.get("html_url") or "",
                )
            )
        elif gh_event == "status":
            events.append(
                self._event(
                    CHECK,
                    delivery,
                    raw_type="status",
                    occurred_at=parse_time(payload.get("updated_at") or payload.get("created_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=payload.get("sha") or "",
                    check_name=payload.get("context") or "status",
                    check_status=ci_status(payload.get("state")),
                    check_id=f"status:{payload.get('id')}",
                    url=payload.get("target_url") or "",
                )
            )
        elif gh_event == "push":
            commits = [
                {"sha": c.get("id"), "message": c.get("message") or "", "timestamp": c.get("timestamp")}
                for c in payload.get("commits") or []
            ]
            branch = strip_ref(payload.get("ref"))
            events.append(
                self._event(
                    PUSH,
                    delivery,
                    raw_type="push",
                    occurred_at=parse_time(commits[-1]["timestamp"]) if commits else None,
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    source_branch=branch,
                    head_sha=payload.get("after") or "",
                    commits=commits,
                    correlation=parse_references(branch, *[c["message"] for c in commits]),
                )
            )
        elif gh_event == "deployment_status":
            ds = payload.get("deployment_status") or {}
            dep = payload.get("deployment") or {}
            dep_payload = dep.get("payload") if isinstance(dep.get("payload"), dict) else {}
            state = str(ds.get("state") or "").lower()
            events.append(
                self._event(
                    DEPLOYMENT,
                    delivery,
                    raw_type="deployment_status",
                    occurred_at=parse_time(ds.get("updated_at") or ds.get("created_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=dep.get("sha") or "",
                    source_branch=dep.get("ref") or "",
                    environment=ds.get("environment") or dep.get("environment") or "",
                    deployment_id=str(dep.get("id") or ""),
                    deployment_status="success" if state == "success" else state,
                    is_rollback=bool(dep.get("task") == "deploy:rollback" or dep_payload.get("rollback")),
                    url=ds.get("target_url") or ds.get("log_url") or "",
                )
            )
        elif gh_event == "release" and payload.get("action") in ("published", "released"):
            rel = payload.get("release") or {}
            target = rel.get("target_commitish") or ""
            events.append(
                self._event(
                    RELEASE,
                    delivery,
                    raw_type="release",
                    occurred_at=parse_time(rel.get("published_at") or rel.get("created_at")),
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=target if _SHA_RE.match(target) else "",
                    source_branch="" if _SHA_RE.match(target) else target,
                    release_tag=rel.get("tag_name") or "",
                    url=rel.get("html_url") or "",
                )
            )
        else:
            events.append(self._event(UNKNOWN, delivery, raw_type=gh_event, repository_external_id=repo_id))
        return self.split_multi(events, delivery)

    def _pr(self, pr, action, repo_id, repo_path, delivery):
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        if pr.get("merged"):
            kind, state = MR_MERGED, "merged"
        elif pr.get("state") == "closed" or action == "closed":
            kind, state = MR_CLOSED, "closed"
        elif action == "opened":
            kind, state = MR_OPENED, "open"
        else:
            kind, state = MR_UPDATED, "open"
        title, body = pr.get("title") or "", pr.get("body") or ""
        reverts_mr, reverts_sha = parse_revert(title, body)
        return self._event(
            kind,
            delivery,
            raw_type=f"pull_request:{action}",
            occurred_at=parse_time(pr.get("merged_at") if state == "merged" else pr.get("updated_at")),
            repository_external_id=str((base.get("repo") or {}).get("id") or repo_id),
            repository_path=repo_path,
            mr_external_id=str(pr.get("number") or ""),
            mr_title=title,
            mr_description=body,
            mr_state=state,
            source_branch=head.get("ref") or "",
            target_branch=base.get("ref") or "",
            head_sha=head.get("sha") or "",
            target_sha=base.get("sha") or "",
            merged_commit_sha=(pr.get("merge_commit_sha") or "") if state == "merged" else "",
            merge_method="unknown" if state == "merged" else "",
            url=pr.get("html_url") or "",
            reverts_mr_external_id=reverts_mr,
            reverts_commit_sha=reverts_sha,
            correlation=parse_references(head.get("ref"), title, body),
        )

    # -- outbound ------------------------------------------------------------
    def _api(self, ctx):
        host = urlparse(ctx.instance_url or "https://github.com").netloc
        if host in ("github.com", "www.github.com", "api.github.com", ""):
            return "https://api.github.com"
        return ctx.instance_url.rstrip("/") + "/api/v3"

    def auth_headers(self, ctx):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if ctx.token:
            headers["Authorization"] = f"Bearer {ctx.token}"
        return headers

    def _repo(self, ctx, repo):
        if repo.path_with_namespace:
            return f"{self._api(ctx)}/repos/{repo.path_with_namespace}"
        return f"{self._api(ctx)}/repositories/{quote(str(repo.external_id))}"

    def fetch_merge_request(self, ctx, repo, mr_id):
        resp = self._get(f"{self._repo(ctx, repo)}/pulls/{quote(str(mr_id))}", ctx)
        if not resp.ok:
            return {"ok": False, "status": resp.status}
        body = resp.body or {}
        state = "merged" if body.get("merged") else ("open" if body.get("state") == "open" else "closed")
        return {
            "ok": True,
            "head_sha": (body.get("head") or {}).get("sha") or "",
            "target_sha": (body.get("base") or {}).get("sha") or "",
            "state": state,
            "target_branch": (body.get("base") or {}).get("ref") or "",
        }

    def merge(self, ctx, repo, mr_id, *, sha, squash=None):
        payload = {"sha": sha}
        if squash is not None:
            payload["merge_method"] = "squash" if squash else "merge"
        resp = self.transport.request(
            "PUT",
            f"{self._repo(ctx, repo)}/pulls/{quote(str(mr_id))}/merge",
            headers=self.auth_headers(ctx),
            json=payload,
        )
        body = resp.body if isinstance(resp.body, dict) else {}
        return {
            "accepted": resp.ok and bool(body.get("merged", True)),
            "status": resp.status,
            "head_mismatch": resp.status == 409,
            "state": "merged" if body.get("merged") else "",
            "merged_commit_sha": body.get("sha") or "",
        }

    def fetch_branch_protection(self, ctx, repo, branch):
        resp = self._get(f"{self._repo(ctx, repo)}/branches/{quote(branch, safe='')}/protection", ctx)
        if resp.status == 404:
            return {"protected": False, "requires_approval": False}
        if not resp.ok:
            return {"protected": None, "requires_approval": None}
        reviews = (resp.body or {}).get("required_pull_request_reviews") or {}
        return {"protected": True, "requires_approval": (reviews.get("required_approving_review_count") or 0) > 0}

    def fetch_repository(self, ctx, repo):
        resp = self._get(self._repo(ctx, repo), ctx)
        if not resp.ok:
            return {"ok": False, "status": resp.status}
        body = resp.body or {}
        branch = body.get("default_branch") or "main"
        full = body.get("full_name") or repo.path_with_namespace
        commit = self._get(f"{self._api(ctx)}/repos/{full}/commits/{quote(branch, safe='')}", ctx)
        head = commit.body.get("sha", "") if commit.ok and isinstance(commit.body, dict) else ""
        return {
            "ok": True,
            "external_id": str(body.get("id") or repo.external_id),
            "path_with_namespace": full,
            "default_branch": branch,
            "head_commit": head,
        }

    def list_tree(self, ctx, repo, commit):
        resp = self._get(f"{self._repo(ctx, repo)}/git/trees/{quote(commit)}", ctx, params={"recursive": "1"})
        if not resp.ok or not isinstance(resp.body, dict):
            return []
        return [item.get("path") for item in resp.body.get("tree") or [] if item.get("type") == "blob"]

    def list_merge_requests(self, ctx, repo, *, updated_after=None, limit=20):
        resp = self._get(
            f"{self._repo(ctx, repo)}/pulls",
            ctx,
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": limit},
        )
        if not resp.ok or not isinstance(resp.body, list):
            return []
        events = []
        for pr in resp.body:
            updated = parse_time(pr.get("updated_at"))
            if updated_after and updated and updated < updated_after:
                continue
            ev_id = fallback_event_id(
                self.provider,
                "pull_request",
                f"{repo.external_id}:{pr.get('number')}",
                pr.get("updated_at"),
                pr.get("state"),
            )
            pr = dict(pr)
            pr["merged"] = bool(pr.get("merged_at"))
            events.append(self._pr(pr, "poll", str(repo.external_id), repo.path_with_namespace, ev_id))
        return events

    def contains_commit(self, ctx, repo, ancestor, descendant):
        if not ancestor or not descendant:
            return None
        if ancestor == descendant:
            return True
        resp = self._get(f"{self._repo(ctx, repo)}/compare/{quote(ancestor)}...{quote(descendant)}", ctx)
        if not resp.ok or not isinstance(resp.body, dict):
            return None
        return resp.body.get("status") in ("ahead", "identical")
