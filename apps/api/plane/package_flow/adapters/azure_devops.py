# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Azure DevOps adapter (Services and Server are separate profiles).

Webhook authentication: service-hook subscriptions are configured with basic
authentication; the connection's webhook secret is ``"<user>:<password>"`` and
the ``Authorization: Basic …`` header is compared in constant time.

Delivery id: the service-hook event ``id`` (kept on retry of the same
notification); otherwise the deterministic hash of resource id + revision/
date + eventType.

Honest limits: human-approval verification depends on branch policies that
differ between Services and Server versions → ``requires_configuration``.
Classic release deployments map only when the Git artifact version is present.
"""

import base64
from urllib.parse import quote

from .base import (
    CHECK,
    DEPLOYMENT,
    ISSUE_UPDATED,
    MR_CLOSED,
    MR_MERGED,
    MR_OPENED,
    MR_UPDATED,
    PARTIAL,
    PUSH,
    REQUIRES_CONFIGURATION,
    SUPPORTED,
    UNKNOWN,
    Adapter,
    CapabilityDeclaration,
    ci_status,
    constant_time_equals,
    fallback_event_id,
    lower_headers,
    parse_references,
    parse_revert,
    parse_time,
    strip_ref,
)

PRIORITY_MAP = {1: "urgent", 2: "high", 3: "medium", 4: "low"}


def _field_new(fields, name):
    value = (fields or {}).get(name)
    if isinstance(value, dict):
        return value.get("newValue")
    return value


class AzureDevOpsAdapter(Adapter):
    provider = "azure_devops"
    display_name = "Azure DevOps"
    kind = "git"
    safe_headers = ()

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
                "read_repository": SUPPORTED,
                "write_spec_branch": REQUIRES_CONFIGURATION,
                "read_merge_requests": SUPPORTED,
                "read_checks": SUPPORTED,
                "read_deployments": PARTIAL,
                "receive_events": REQUIRES_CONFIGURATION,
                "verify_human_approval": REQUIRES_CONFIGURATION,
                "request_merge": SUPPORTED,
                "acl_discovery": PARTIAL,
                "reconcile": PARTIAL,
            },
            editions=["services", "server_2022"],
            instance_types=["cloud", "server"],
            min_requirements=(
                "Azure DevOps Services REST 7.1 or Server 2022; PAT with Code (read/write), Build (read), "
                "Work Items (read). Service-hook subscriptions with basic auth per event type."
            ),
            auth_methods=["personal_access_token", "entra_id_oauth"],
            webhook_auth="Service hook basic auth (Authorization: Basic) compared in constant time",
            rate_limits=(
                "Global consumption limit (TSTU per 5-minute window); HTTP "
                "429 with Retry-After / X-RateLimit-* headers."
            ),
            event_types=[
                "git.pullrequest.created",
                "git.pullrequest.updated",
                "git.pullrequest.merged",
                "git.push",
                "build.complete",
                "ms.vss-release.deployment-completed-event",
                "workitem.updated",
            ],
            field_mapping={
                "merge_request.id": "resource.pullRequestId",
                "merge_request.head_sha": "resource.lastMergeSourceCommit.commitId",
                "merge_request.merged_commit_sha": "resource.lastMergeCommit.commitId",
                "priority": "Microsoft.VSTS.Common.Priority 1..4 → urgent|high|medium|low",
                "title": "System.Title",
                "status": "System.State (observation only)",
            },
            notes=["Services vs Server policies and versions must be verified separately (PRD §12.2)."],
        )

    def verify_webhook(self, headers, body, secret):
        if not secret or ":" not in secret:
            return False
        expected = "Basic " + base64.b64encode(secret.encode("utf-8")).decode("ascii")
        return constant_time_equals(lower_headers(headers).get("authorization"), expected)

    def delivery_id(self, headers, payload):
        if payload.get("id"):
            return f"azure:{payload['id']}"
        res = payload.get("resource") or {}
        return fallback_event_id(
            self.provider,
            payload.get("eventType"),
            res.get("pullRequestId") or res.get("workItemId") or res.get("id"),
            res.get("rev") or res.get("revisedDate") or payload.get("createdDate"),
            payload.get("eventType"),
        )

    def normalize(self, headers, payload):
        delivery = self.delivery_id(headers, payload)
        et = payload.get("eventType") or ""
        res = payload.get("resource") or {}
        repo = res.get("repository") or {}
        repo_id = str(repo.get("id") or "")
        repo_path = f"{(repo.get('project') or {}).get('name', '')}/{repo.get('name', '')}".strip("/")
        occurred = parse_time(payload.get("createdDate"))
        events = []
        if et.startswith("git.pullrequest."):
            status = res.get("status")
            if status == "completed":
                kind, state = MR_MERGED, "merged"
            elif status == "abandoned":
                kind, state = MR_CLOSED, "closed"
            elif et == "git.pullrequest.created":
                kind, state = MR_OPENED, "open"
            else:
                kind, state = MR_UPDATED, "open"
            title, desc = res.get("title") or "", res.get("description") or ""
            src = strip_ref(res.get("sourceRefName"))
            strategy = ((res.get("completionOptions") or {}).get("mergeStrategy") or "").lower()
            reverts_mr, reverts_sha = parse_revert(title, desc)
            events.append(
                self._event(
                    kind,
                    delivery,
                    raw_type=et,
                    occurred_at=parse_time(res.get("closedDate")) or occurred,
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    mr_external_id=str(res.get("pullRequestId") or ""),
                    mr_title=title,
                    mr_description=desc,
                    mr_state=state,
                    source_branch=src,
                    target_branch=strip_ref(res.get("targetRefName")),
                    head_sha=(res.get("lastMergeSourceCommit") or {}).get("commitId") or "",
                    target_sha=(res.get("lastMergeTargetCommit") or {}).get("commitId") or "",
                    merged_commit_sha=((res.get("lastMergeCommit") or {}).get("commitId") or "")
                    if state == "merged"
                    else "",
                    merge_method=("squash" if strategy == "squash" else (strategy or "merge"))
                    if state == "merged"
                    else "",
                    url=res.get("url") or "",
                    reverts_mr_external_id=reverts_mr,
                    reverts_commit_sha=reverts_sha,
                    correlation=parse_references(src, title, desc),
                )
            )
        elif et == "git.push":
            commits = [
                {
                    "sha": c.get("commitId"),
                    "message": c.get("comment") or "",
                    "timestamp": (c.get("committer") or {}).get("date"),
                }
                for c in res.get("commits") or []
            ]
            ref = (res.get("refUpdates") or [{}])[0]
            branch = strip_ref(ref.get("name"))
            events.append(
                self._event(
                    PUSH,
                    delivery,
                    raw_type=et,
                    occurred_at=parse_time(res.get("date")) or occurred,
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    source_branch=branch,
                    head_sha=ref.get("newObjectId") or "",
                    commits=commits,
                    correlation=parse_references(branch, *[c["message"] for c in commits]),
                )
            )
        elif et == "build.complete":
            name = (res.get("definition") or {}).get("name") or "build"
            events.append(
                self._event(
                    CHECK,
                    delivery,
                    raw_type=et,
                    occurred_at=parse_time(res.get("finishTime")) or occurred,
                    repository_external_id=repo_id,
                    repository_path=repo_path,
                    head_sha=res.get("sourceVersion") or "",
                    source_branch=strip_ref(res.get("sourceBranch")),
                    check_name=name,
                    check_kind="test" if "test" in name.lower() else "build",
                    check_status=ci_status(res.get("result")),
                    check_id=f"build:{res.get('id')}",
                    url=res.get("url") or "",
                )
            )
        elif et == "ms.vss-release.deployment-completed-event":
            env = res.get("environment") or {}
            dep = res.get("deployment") or {}
            sha, repo_ext = "", repo_id
            for artifact in (dep.get("release") or {}).get("artifacts") or []:
                ref = artifact.get("definitionReference") or {}
                if (ref.get("repository") or {}).get("id"):
                    repo_ext = str(ref["repository"]["id"])
                if (ref.get("sourceVersion") or {}).get("id"):
                    sha = ref["sourceVersion"]["id"]
                    break
            status = str(env.get("status") or dep.get("deploymentStatus") or "").lower()
            events.append(
                self._event(
                    DEPLOYMENT,
                    delivery,
                    raw_type=et,
                    occurred_at=parse_time(dep.get("completedOn")) or occurred,
                    repository_external_id=repo_ext,
                    head_sha=sha,
                    environment=env.get("name") or "",
                    deployment_id=str(dep.get("id") or ""),
                    deployment_status="success" if status in ("succeeded", "success") else status,
                )
            )
        elif et == "workitem.updated":
            fields = res.get("fields") or {}
            revision_fields = (res.get("revision") or {}).get("fields") or {}
            changed, values = [], {}
            prio = _field_new(fields, "Microsoft.VSTS.Common.Priority")
            if prio is not None:
                changed.append("priority")
                values["priority"] = PRIORITY_MAP.get(int(prio), "none")
            title = _field_new(fields, "System.Title")
            if title is not None:
                changed.append("title")
                values["title"] = title
            state = _field_new(fields, "System.State")
            if state is not None:
                changed.append("status")
                values["status"] = state
            events.append(
                self._event(
                    ISSUE_UPDATED,
                    delivery,
                    raw_type=et,
                    occurred_at=parse_time(res.get("revisedDate"))
                    or parse_time(revision_fields.get("System.ChangedDate"))
                    or occurred,
                    external_issue_id=str(res.get("workItemId") or (res.get("revision") or {}).get("id") or ""),
                    fields=values,
                    field_changed=changed,
                    url=res.get("url") or "",
                )
            )
        else:
            events.append(self._event(UNKNOWN, delivery, raw_type=et, repository_external_id=repo_id))
        return self.split_multi(events, delivery)

    # -- outbound ------------------------------------------------------------
    def auth_headers(self, ctx):
        if not ctx.token:
            return {}
        return {"Authorization": "Basic " + base64.b64encode(f":{ctx.token}".encode()).decode("ascii")}

    def _repo_url(self, ctx, repo):
        project = (repo.path_with_namespace or "").split("/")[0]
        base = ctx.instance_url.rstrip("/")
        return f"{base}/{quote(project)}/_apis/git/repositories/{quote(str(repo.external_id))}"

    def fetch_merge_request(self, ctx, repo, mr_id):
        resp = self._get(
            f"{self._repo_url(ctx, repo)}/pullrequests/{quote(str(mr_id))}", ctx, params={"api-version": "7.1"}
        )
        if not resp.ok:
            return {"ok": False, "status": resp.status}
        body = resp.body or {}
        status = body.get("status")
        return {
            "ok": True,
            "head_sha": (body.get("lastMergeSourceCommit") or {}).get("commitId") or "",
            "target_sha": (body.get("lastMergeTargetCommit") or {}).get("commitId") or "",
            "state": "merged" if status == "completed" else ("closed" if status == "abandoned" else "open"),
            "target_branch": strip_ref(body.get("targetRefName")),
        }

    def merge(self, ctx, repo, mr_id, *, sha, squash=None):
        payload = {"status": "completed", "lastMergeSourceCommit": {"commitId": sha}}
        if squash is not None:
            payload["completionOptions"] = {"mergeStrategy": "squash" if squash else "noFastForward"}
        resp = self.transport.request(
            "PATCH",
            f"{self._repo_url(ctx, repo)}/pullrequests/{quote(str(mr_id))}?api-version=7.1",
            headers=self.auth_headers(ctx),
            json=payload,
        )
        return {
            "accepted": resp.ok,
            "status": resp.status,
            "head_mismatch": resp.status == 409,
            "state": "",
            "merged_commit_sha": "",
        }

    def fetch_branch_protection(self, ctx, repo, branch):
        project = (repo.path_with_namespace or "").split("/")[0]
        resp = self._get(
            f"{ctx.instance_url.rstrip('/')}/{quote(project)}/_apis/policy/configurations",
            ctx,
            params={
                "repositoryId": repo.external_id,
                "refName": f"refs/heads/{branch}",
                "api-version": "7.1-preview.1",
            },
        )
        if not resp.ok or not isinstance(resp.body, dict):
            return {"protected": None, "requires_approval": None}
        policies = [p for p in resp.body.get("value") or [] if p.get("isEnabled") and p.get("isBlocking")]
        reviewers = [p for p in policies if "reviewer" in ((p.get("type") or {}).get("displayName") or "").lower()]
        return {"protected": bool(policies), "requires_approval": bool(reviewers)}
