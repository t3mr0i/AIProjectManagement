# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Structured export (FR-I06, FR-B09, FR-I08).

* Only projects the requester can currently read are exported.
* Native IDs are kept (``workItemId == issue_id``); revisions use the
  package-revision contract 1.1.0.
* External tracker mappings live in a separate ``externalMappings`` section,
  so disconnecting a tracker never changes core IDs.
* DM content is only included if explicitly requested (``direct_messages``)
  and only for DMs the requester participates in.
* Bundles are persisted as ``ExportJob`` rows with ``expires_at`` and are
  deleted by the ``exports`` retention category.
"""

import os
from datetime import timedelta

from django.utils import timezone

from plane.db.models import Issue, Project

from ..capabilities import accessible_project_ids, has_capability
from ..errors import DomainError, NotFound, ValidationFailed
from ..models import (
    Capability,
    Conversation,
    Decision,
    DiagramDocument,
    ExportJob,
    ExternalLink,
    Message,
    PackageProfile,
    PackageRevision,
    UploadRecord,
)
from .search import my_dm_conversation_ids

SCHEMA_VERSION = "1.1.0"
INCLUDE_ALL = ("packages", "revisions", "decisions", "sources", "artifacts", "external_mappings")
INCLUDE_OPTIONAL = ("direct_messages",)
TTL_DAYS = int(os.environ.get("PACKAGE_FLOW_EXPORT_TTL_DAYS", "7"))


class ExportExpired(DomainError):
    status_code = 410
    code = "EXPORT_EXPIRED"


def _iso(value):
    return value.isoformat() if value else None


def _id(value):
    return str(value) if value else None


def _revision_contract(rev):
    try:
        from ..serializers_packages import revision_contract

        return revision_contract(rev)
    except Exception:  # serializer owned by the package workstream; minimal fallback
        return {
            "schemaVersion": SCHEMA_VERSION,
            "id": str(rev.id),
            "workItemId": str(rev.issue_id),
            "projectId": str(rev.project_id),
            "workspaceId": str(rev.workspace_id),
            "number": rev.number,
            "title": rev.title,
            "contentHash": rev.content_hash,
        }


def _message(m):
    return {
        "id": str(m.id),
        "conversationId": str(m.conversation_id),
        "authorId": _id(m.author_id),
        "authorKind": m.author_kind,
        "body": m.body,
        "version": m.version,
        "createdAt": _iso(m.created_at),
    }


def build_bundle(user, workspace, *, project_ids=None, include=None):
    include = list(include or INCLUDE_ALL)
    unknown = [i for i in include if i not in INCLUDE_ALL + INCLUDE_OPTIONAL]
    if unknown:
        raise ValidationFailed(f"Unknown export sections: {', '.join(unknown)}")
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    if project_ids:
        wanted = [str(p) for p in project_ids]
        if any(p not in readable for p in wanted):
            raise NotFound("Project not found")
    else:
        wanted = sorted(readable)
    projects = list(Project.objects.filter(id__in=wanted, workspace=workspace, deleted_at__isnull=True))
    pids = [p.id for p in projects]
    bundle = {
        "schemaVersion": SCHEMA_VERSION,
        "exportedAt": _iso(timezone.now()),
        "workspaceId": str(workspace.id),
        "requestedBy": str(user.id),
        "include": include,
        "projects": [{"projectId": str(p.id), "name": p.name, "identifier": p.identifier} for p in projects],
    }
    profiles = {
        pr.issue_id: pr for pr in PackageProfile.objects.filter(project_id__in=pids, issue__deleted_at__isnull=True)
    }
    issues = list(Issue.objects.filter(id__in=list(profiles), project_id__in=pids).select_related("state", "project"))

    if "packages" in include:
        bundle["packages"] = [
            {
                "workItemId": str(i.id),
                "projectId": str(i.project_id),
                "workspaceId": str(i.workspace_id),
                "identifier": f"{i.project.identifier}-{i.sequence_id}",
                "title": i.name,
                "priority": i.priority,
                "nativeState": {"id": _id(i.state_id), "group": i.state.group if i.state_id else None},
                "profile": {
                    "profileKind": profiles[i.id].profile_kind,
                    "packageType": profiles[i.id].package_type,
                    "intent": profiles[i.id].intent,
                    "outcome": profiles[i.id].outcome,
                    "nonGoals": profiles[i.id].non_goals,
                    "criteria": profiles[i.id].criteria,
                    "approvedRevisionId": _id(profiles[i.id].approved_revision_id),
                    "version": profiles[i.id].version,
                },
            }
            for i in issues
        ]
    if "revisions" in include:
        revs = PackageRevision.objects.filter(project_id__in=pids, issue__deleted_at__isnull=True).order_by(
            "issue_id", "number"
        )
        bundle["revisions"] = [_revision_contract(r) for r in revs]
    if "decisions" in include:
        bundle["decisions"] = [
            {
                "id": str(d.id),
                "projectId": _id(d.project_id),
                "workItemId": _id(d.issue_id),
                "title": d.title,
                "text": d.text,
                "rationale": d.rationale,
                "status": d.status,
                "kind": d.kind,
                "confirmedBy": _id(d.confirmed_by_id),
                "confirmedAt": _iso(d.confirmed_at),
                "sourceSnapshot": d.source_snapshot if "sources" in include else None,
            }
            for d in Decision.objects.filter(project_id__in=pids).order_by("created_at")
        ]
    contains_private = False
    if "sources" in include:
        convs = Conversation.objects.filter(project_id__in=pids).exclude(kind=Conversation.Kind.DIRECT)
        bundle["sources"] = {
            "conversations": [
                {
                    "id": str(c.id),
                    "kind": c.kind,
                    "projectId": _id(c.project_id),
                    "workItemId": _id(c.issue_id),
                    "title": c.title,
                }
                for c in convs
            ],
            "messages": [_message(m) for m in Message.objects.filter(conversation__in=convs).order_by("created_at")],
        }
        if "direct_messages" in include:
            # Only DMs the requester participates in, and only on explicit request.
            dms = Conversation.objects.filter(id__in=my_dm_conversation_ids(user, workspace.id))
            bundle["sources"]["directMessages"] = [
                {
                    "conversationId": str(c.id),
                    "messages": [_message(m) for m in Message.objects.filter(conversation=c).order_by("created_at")],
                }
                for c in dms
            ]
            contains_private = bool(dms)
    elif "direct_messages" in include:
        raise ValidationFailed("direct_messages requires the sources section")
    if "artifacts" in include:
        bundle["artifacts"] = {
            "uploads": [
                {
                    "id": str(u.id),
                    "assetId": str(u.asset_id),
                    "projectId": _id(u.project_id),
                    "workItemId": _id(u.issue_id),
                    "name": (u.asset.attributes or {}).get("name"),
                    "detectedMime": u.detected_mime,
                    "formatSupport": u.format_support,
                }
                # Quarantined/pending uploads are not exported (FR-C05).
                for u in UploadRecord.objects.filter(
                    project_id__in=pids, scan_status="clean", asset__is_deleted=False
                ).select_related("asset")
            ],
            "diagrams": [
                {
                    "id": str(d.id),
                    "projectId": _id(d.project_id),
                    "workItemId": _id(d.issue_id),
                    "name": d.name,
                    "diagramType": d.diagram_type,
                    "version": d.version,
                    "semantic": d.semantic,
                    "layout": d.layout,
                }
                for d in DiagramDocument.objects.filter(project_id__in=pids)
            ],
        }
    if "external_mappings" in include:
        # Separate section: a tracker disconnect changes mapping state, never core IDs.
        bundle["externalMappings"] = [
            {
                "workItemId": str(link.issue_id),
                "connectionId": str(link.connection_id),
                "provider": link.connection.provider,
                "connectionStatus": link.connection.status,
                "objectType": link.object_type,
                "externalId": link.external_id,
                "externalKey": link.external_key,
                "url": link.url,
                "representsPackage": link.represents_package,
                "syncState": link.sync_state,
                "removed": link.deleted_at is not None,
            }
            for link in ExternalLink.all_objects.filter(
                project_id__in=pids, issue__deleted_at__isnull=True
            ).select_related("connection")
        ]
    return bundle, contains_private, [str(p) for p in pids]


def create(user, workspace, *, project_ids=None, include=None):
    bundle, private, pids = build_bundle(user, workspace, project_ids=project_ids, include=include)
    now = timezone.now()
    return ExportJob.objects.create(
        workspace=workspace,
        requested_by=user,
        scope={"project_ids": pids, "include": bundle["include"]},
        content=bundle,
        contains_private=private,
        expires_at=now + timedelta(days=TTL_DAYS),
    )


def _is_admin(user, workspace):
    return has_capability(user, workspace.id, None, Capability.WORKSPACE_ADMIN)


def visible_jobs(user, workspace):
    qs = ExportJob.objects.filter(workspace=workspace)
    if not _is_admin(user, workspace):
        qs = qs.filter(requested_by=user)
    return list(qs.order_by("-created_at")[:100])


def get_for(user, workspace, job_id):
    job = ExportJob.objects.filter(id=job_id, workspace=workspace).first()
    if job is None:
        raise NotFound("Export not found")
    is_owner = job.requested_by_id == user.id
    if not is_owner and not _is_admin(user, workspace):
        raise NotFound("Export not found")
    if job.expires_at <= timezone.now():
        raise ExportExpired("Export has expired")
    # Revoked access also revokes access to older exports of that scope (FR-I07).
    readable = {str(p) for p in accessible_project_ids(user, workspace.id)}
    scope_ok = all(p in readable for p in job.scope.get("project_ids", []))
    # Admins never receive another person's private DM content (PRD §5.2).
    withheld = not scope_ok or (not is_owner and job.contains_private)
    return job, withheld


def serialize(job, *, with_content=False, withheld=False):
    data = {
        "id": str(job.id),
        "requested_by": _id(job.requested_by_id),
        "scope": job.scope,
        "status": job.status,
        "contains_private": job.contains_private,
        "created_at": job.created_at,
        "expires_at": job.expires_at,
    }
    if with_content:
        data["content_withheld"] = withheld
        data["bundle"] = None if withheld else job.content
    return data


def purge_expired(workspace, now=None, cutoff=None):
    now = now or timezone.now()
    qs = ExportJob.all_objects.filter(workspace=workspace)
    expired = qs.filter(expires_at__lte=now)
    n, _ = expired.delete()
    if cutoff is not None:
        m, _ = ExportJob.all_objects.filter(workspace=workspace, created_at__lt=cutoff).delete()
        n += m
    return n
