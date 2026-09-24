# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""OpenSpec export/import for packages (FR-W08, FR-W09, FR-G02, PRD §12.4, INV-02).

* Export renders the working draft (or a named revision) onto the last synced
  git snapshot, so unknown blocks survive. Export requires the caller's
  ``expected_base_commit`` to equal the synced base: a moved head yields
  ``409 SPEC_BASE_MOVED`` — never a force push. Export never creates an
  ExecutionApproval or a run: document publication != execution approval.
* Import runs a three-way merge (base / platform draft / git). A clean merge
  creates a new *working* revision (origin ``openspec_import``) and leaves
  ``approved_revision`` untouched, so a running run keeps its approved
  revision (FR-W09). A conflict sets ``state=conflict`` and returns
  ``409 SPEC_CONFLICT`` with base/platform/git versions per block (AC07).
"""

import hashlib
import json

from django.db import transaction
from django.db.models import Max

from ..errors import Conflict, NotFound, ValidationFailed
from ..models import PackageProfile, PackageRevision, RepositoryBinding, SpecSyncState
from ..openspec import LossyExportError, apply_fields, extract_fields, merge_documents, parse_files, render_files
from ..openspec.document import Document
from ..openspec.manifest import ManifestMismatch, build_manifest, change_id_for, validate_manifest
from . import events

CONTENT_FIELDS = ("intent", "outcome", "non_goals", "scope", "criteria", "decisions", "artifacts")
MAX_FILES = 200
MAX_TOTAL_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_files(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data.get("files", {}) if isinstance(data, dict) else {}


def _dump_files(files: dict) -> str:
    return json.dumps({"files": files}, sort_keys=True, ensure_ascii=False)


def require_profile(issue) -> PackageProfile:
    profile = PackageProfile.objects.filter(issue_id=issue.id, deleted_at__isnull=True).first()
    if profile is None:
        raise NotFound("Work item has no package profile", code="NO_PROFILE")
    return profile


def _fields_of(source) -> dict:
    return {
        "intent": source.intent or "",
        "outcome": source.outcome or "",
        "scope": dict(source.scope or {}),
        "criteria": list(source.criteria or []),
    }


def _capability_default(issue) -> str:
    return (getattr(issue.project, "identifier", "") or "package").lower()


def _spec_path(state, issue, manifest=None) -> str:
    if state is not None and state.spec_path:
        return state.spec_path
    change_id = (manifest or {}).get("changeId") or change_id_for(issue)
    return f"openspec/changes/{change_id}"


def _state_for(issue, binding) -> SpecSyncState:
    state = SpecSyncState.objects.filter(issue_id=issue.id, repository_binding=binding, deleted_at__isnull=True).first()
    if state is None:
        state = SpecSyncState(issue=issue, repository_binding=binding, spec_path=_spec_path(None, issue))
    return state


def _binding(issue, binding_id, *, required):
    if not binding_id:
        if required:
            raise ValidationFailed("repository_binding_id is required", detail={"field": "repository_binding_id"})
        return None
    binding = (
        RepositoryBinding.objects.filter(
            id=binding_id, workspace_id=issue.workspace_id, deleted_at__isnull=True, is_active=True
        )
        .filter(project_id__in=[issue.project_id])
        .first()
    ) or RepositoryBinding.objects.filter(
        id=binding_id, workspace_id=issue.workspace_id, project__isnull=True, deleted_at__isnull=True, is_active=True
    ).first()
    if binding is None:
        raise NotFound("Repository binding not found")
    return binding


def _revision_hash(issue, content: dict) -> str:
    desc = _sha((issue.description_html or "").strip())
    return _sha(_canonical({"content": content, "title": issue.name or "", "native_description_sha256": desc}))


def create_import_revision(issue, profile, principal, fields: dict, *, source_versions: dict):
    """Create a new immutable working revision with origin ``openspec_import``.

    Local helper (does not depend on the package service): number = max + 1,
    content hash = sha256 over the canonical content fields. ``approved_revision``
    is never changed here (FR-W09).
    """
    content = {
        "intent": fields.get("intent", profile.intent) or "",
        "outcome": fields.get("outcome", profile.outcome) or "",
        "non_goals": list(profile.non_goals or []),
        "scope": dict(fields.get("scope", profile.scope) or {}),
        "criteria": list(fields.get("criteria", profile.criteria) or []),
        "decisions": [],
        "artifacts": [],
        "profile_kind": profile.profile_kind,
        "package_type": profile.package_type,
    }
    previous = profile.working_revision
    if previous is not None:
        content["decisions"] = list(previous.decisions or [])
        content["artifacts"] = [a for a in previous.artifacts or [] if a.get("type") != "openspec"]
    content["artifacts"].append({"type": "openspec", **source_versions.get("openspec", {})})
    number = (PackageRevision.objects.filter(issue_id=issue.id).aggregate(n=Max("number"))["n"] or 0) + 1
    revision = PackageRevision.objects.create(
        issue=issue,
        number=number,
        title=issue.name,
        intent=content["intent"],
        outcome=content["outcome"],
        non_goals=content["non_goals"],
        scope=content["scope"],
        criteria=content["criteria"],
        decisions=content["decisions"],
        artifacts=content["artifacts"],
        profile_kind=content["profile_kind"],
        package_type=content["package_type"],
        content_hash=_revision_hash(issue, content),
        based_on=previous,
        origin="openspec_import",
        source_versions=source_versions,
        created_by=principal.user,
    )
    events.emit(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue_id=issue.id,
        event_type="package.revision.created",
        aggregate_type="package",
        aggregate_id=issue.id,
        actor_kind=principal.kind,
        actor_id=principal.id,
        deduplication_key=f"package.revision.created:{revision.id}",
        payload={
            "revisionId": str(revision.id),
            "number": number,
            "contentHash": revision.content_hash,
            "origin": "openspec_import",
        },
        summary=f"Revision {number} imported from OpenSpec",
    )
    return revision


def _validate_files(files) -> dict:
    if not isinstance(files, dict) or not files:
        raise ValidationFailed("files must be a non-empty object {path: text}", detail={"field": "files"})
    if len(files) > MAX_FILES:
        raise ValidationFailed("too many files", detail={"field": "files", "max": MAX_FILES})
    total = 0
    for path, text in files.items():
        if not isinstance(path, str) or not isinstance(text, str):
            raise ValidationFailed("files must map string paths to string content", detail={"field": "files"})
        if ".." in path.replace("\\", "/").split("/"):
            raise ValidationFailed("path traversal is not allowed", detail={"field": "files", "path": path})
        total += len(text.encode("utf-8"))
    if total > MAX_TOTAL_BYTES:
        raise ValidationFailed("spec content too large", detail={"field": "files", "max_bytes": MAX_TOTAL_BYTES})
    return files


def _platform_document(state, issue, fields: dict) -> Document:
    base_doc = parse_files(_load_files(state.base_content)) if state and state.base_content else Document()
    return base_doc, apply_fields(base_doc, fields, title=issue.name, default_capability=_capability_default(issue))


# ---------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------
def serialize_state(state: SpecSyncState, *, include_content=False) -> dict:
    body = {
        "id": str(state.id) if not state._state.adding else None,
        "work_item_id": str(state.issue_id),
        "repository_binding_id": str(state.repository_binding_id) if state.repository_binding_id else None,
        "spec_path": state.spec_path,
        "state": state.state,
        "base_commit": state.base_commit,
        "published_commit": state.published_commit,
        "published_revision_id": str(state.published_revision_id) if state.published_revision_id else None,
        "conflict": state.conflict or {},
        "updated_at": state.updated_at.isoformat() if getattr(state, "updated_at", None) else None,
    }
    if include_content:
        body["base_files"] = _load_files(state.base_content)
        body["platform_files"] = _load_files(state.platform_content)
        body["git_files"] = _load_files(state.git_content)
    return body


def get_spec_state(issue) -> dict:
    profile = require_profile(issue)
    states = SpecSyncState.objects.filter(issue_id=issue.id, deleted_at__isnull=True).order_by("created_at")
    return {
        "work_item_id": str(issue.id),
        "working_revision_id": str(profile.working_revision_id) if profile.working_revision_id else None,
        "approved_revision_id": str(profile.approved_revision_id) if profile.approved_revision_id else None,
        "states": [serialize_state(s) for s in states],
    }


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def export_spec(issue, principal, *, repository_binding_id, expected_base_commit, revision_id=None) -> dict:
    profile = require_profile(issue)
    binding = _binding(issue, repository_binding_id, required=True)
    expected = (expected_base_commit or "").strip()
    with transaction.atomic():
        state = _state_for(issue, binding)
        if not state._state.adding:
            state = SpecSyncState.objects.select_for_update().get(pk=state.pk)
        if state.state == "conflict":
            raise Conflict(
                "Resolve the open spec conflict before exporting",
                code="SPEC_CONFLICT",
                detail={"conflicts": state.conflict.get("blocks", [])},
            )
        if (state.base_commit or "") != expected:
            # Git head moved since the caller's view: no force push, re-import first.
            raise Conflict(
                "Spec branch head moved; import the new commit first (no force push)",
                code="SPEC_BASE_MOVED",
                detail={"expected_base_commit": expected, "actual_base_commit": state.base_commit or ""},
            )
        if revision_id:
            revision = PackageRevision.objects.filter(
                id=revision_id, issue_id=issue.id, deleted_at__isnull=True
            ).first()
            if revision is None:
                raise NotFound("Revision not found")
            fields, published = _fields_of(revision), revision
        else:
            fields, published = _fields_of(profile), profile.working_revision
        change_id = state.spec_path.rsplit("/", 1)[-1] if state.spec_path else change_id_for(issue)
        manifest = build_manifest(
            issue=issue,
            revision_id=published.id if published else None,
            change_id=change_id,
            criteria=fields["criteria"],
        )
        _, doc = _platform_document(state, issue, fields)
        doc = apply_fields(doc, {}, manifest=manifest)
        try:
            files = render_files(doc)
        except LossyExportError as exc:
            raise ValidationFailed(
                "Export blocked: it would drop unknown OpenSpec content",
                code="SPEC_EXPORT_LOSSY",
                detail={"blocks": exc.blocks},
            )
        digest = _sha(_canonical(files))
        state.spec_path = state.spec_path or _spec_path(None, issue)
        state.platform_content = _dump_files(files)
        state.published_revision = published
        # Placeholder until the adapter reports the created commit (explicit publication binds both).
        state.published_commit = f"pending:{digest[:12]}"
        state.state = "clean" if files == _load_files(state.git_content) else "ahead"
        state.conflict = {}
        state.save()
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="spec.exported",
            aggregate_type="package",
            aggregate_id=issue.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            payload={
                "specPath": state.spec_path,
                "repositoryBindingId": str(binding.id),
                "baseCommit": state.base_commit,
                "revisionId": str(published.id) if published else None,
                "contentSha256": digest,
            },
            summary=f"OpenSpec exported to {state.spec_path}",
        )
        events.audit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            actor=principal.user,
            actor_kind=principal.kind,
            action="spec.exported",
            target_type="spec_sync_state",
            target_id=state.id,
            detail={"base_commit": state.base_commit, "content_sha256": digest},
        )
    return {
        "spec_path": state.spec_path,
        "branch": binding.specs_branch or binding.default_branch,
        "expected_base_commit": state.base_commit,
        "files": {f"{state.spec_path}/{path}": text for path, text in files.items()},
        "manifest": manifest,
        "published_revision_id": str(published.id) if published else None,
        "published_commit": state.published_commit,
        "force_push": False,
        # Publication of a document is not an execution approval (INV-02, PRD §12.4).
        "execution_approved": False,
        "state": serialize_state(state),
    }


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
def import_spec(
    issue, principal, *, files=None, content=None, commit, repository_binding_id=None, resolutions=None
) -> dict:
    profile = require_profile(issue)
    binding = _binding(issue, repository_binding_id, required=False)
    if files is None and content is not None:
        if not isinstance(content, str):
            raise ValidationFailed("content must be a string", detail={"field": "content"})
        files = {"proposal.md": content}
    files = _validate_files(files)
    commit = (commit or "").strip()
    if not commit:
        raise ValidationFailed("commit is required", detail={"field": "commit"})
    if resolutions is not None and (
        not isinstance(resolutions, dict) or any(v not in ("platform", "git") for v in resolutions.values())
    ):
        raise ValidationFailed("resolutions must map block ids to 'platform' or 'git'", detail={"field": "resolutions"})

    with transaction.atomic():
        profile = PackageProfile.objects.select_for_update().get(pk=profile.pk)
        state = _state_for(issue, binding)
        if not state._state.adding:
            state = SpecSyncState.objects.select_for_update().get(pk=state.pk)
        prefix = state.spec_path if not state._state.adding else ""
        git_doc = parse_files(files, change_prefix=prefix)
        try:
            validate_manifest(git_doc.manifest(), issue)
        except ManifestMismatch as exc:
            raise ValidationFailed(
                "Spec manifest belongs to another package",
                code="SPEC_MANIFEST_MISMATCH",
                detail={"field": exc.field, "expected": exc.expected, "actual": exc.actual},
            )
        if state._state.adding:
            state.spec_path = _spec_path(None, issue, git_doc.manifest())
        git_files = render_files(git_doc, allow_lossy=True)
        base_doc, platform_doc = _platform_document(state, issue, _fields_of(profile))
        result = merge_documents(base_doc, platform_doc, git_doc, resolutions)
        state.git_content = _dump_files(git_files)

        if not result.is_clean:
            state.state = "conflict"
            state.conflict = {"commit": commit, "blocks": result.conflicts}
            state.save()
            events.emit(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                issue_id=issue.id,
                event_type="spec.imported",
                aggregate_type="package",
                aggregate_id=issue.id,
                actor_kind=principal.kind,
                actor_id=principal.id,
                payload={"commit": commit, "result": "conflict", "blocks": [c["block_id"] for c in result.conflicts]},
                summary="OpenSpec import conflicts with the platform draft",
            )
            # Returned (not raised) so the conflict state is committed; the view answers 409.
            return {"conflict": True, "state": serialize_state(state), "conflicts": result.conflicts}

        merged = result.document
        new_fields = extract_fields(merged)
        for criterion in new_fields["criteria"]:
            criterion.setdefault("required", True)
        current = _fields_of(profile)
        changed = _canonical(_comparable(current)) != _canonical(_comparable(new_fields))
        revision = None
        if changed or profile.working_revision_id is None:
            scope = dict(profile.scope or {})
            scope.pop("impact", None)
            scope.pop("tasks", None)
            scope.update(new_fields["scope"])
            new_fields["scope"] = scope
            revision = create_import_revision(
                issue,
                profile,
                principal,
                new_fields,
                source_versions={
                    "openspec": {
                        "commit": commit,
                        "spec_path": state.spec_path,
                        "repository_binding_id": str(binding.id) if binding else None,
                        "files_sha256": _sha(_canonical(git_files)),
                    },
                    "profile_version": profile.version,
                },
            )
            profile.intent = new_fields["intent"]
            profile.outcome = new_fields["outcome"]
            profile.scope = scope
            profile.criteria = new_fields["criteria"]
            profile.working_revision = revision
            profile.version = (profile.version or 0) + 1
            # approved_revision is deliberately untouched (FR-W09).
            profile.save(
                update_fields=["intent", "outcome", "scope", "criteria", "working_revision", "version", "updated_at"]
            )
        merged_files = render_files(merged, allow_lossy=True)
        state.base_commit = commit
        state.base_content = _dump_files(git_files)
        state.platform_content = _dump_files(merged_files)
        state.state = "clean" if merged_files == git_files else "ahead"
        state.conflict = {}
        state.save()
        events.emit(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            event_type="spec.imported",
            aggregate_type="package",
            aggregate_id=issue.id,
            actor_kind=principal.kind,
            actor_id=principal.id,
            payload={
                "commit": commit,
                "result": "merged",
                "revisionId": str(revision.id) if revision else None,
                "takenFromPlatform": result.taken_from_platform,
                "takenFromGit": result.taken_from_git,
            },
            summary="OpenSpec imported" + (" as new working revision" if revision else " (no content change)"),
        )
    return {
        "conflict": False,
        "revision_id": str(revision.id) if revision else None,
        "revision_created": revision is not None,
        "working_revision_id": str(profile.working_revision_id) if profile.working_revision_id else None,
        "approved_revision_id": str(profile.approved_revision_id) if profile.approved_revision_id else None,
        "taken_from_platform": result.taken_from_platform,
        "taken_from_git": result.taken_from_git,
        "state": serialize_state(state),
    }


def _comparable(fields: dict) -> dict:
    """Compare only what OpenSpec carries (ids, text, names, scenarios) — not UI-only keys."""
    criteria = [
        {
            "id": c.get("id"),
            "text": c.get("text", ""),
            **({"requirement": c["requirement"]} if c.get("requirement") else {}),
            **({"scenarios": c["scenarios"]} if "scenarios" in c else {}),
        }
        for c in fields.get("criteria") or []
    ]
    scope = fields.get("scope") or {}
    return {
        "intent": fields.get("intent") or "",
        "outcome": fields.get("outcome") or "",
        "impact": scope.get("impact", ""),
        "tasks": [{"id": t.get("id"), "text": t.get("text")} for t in scope.get("tasks") or []],
        "criteria": criteria,
    }
