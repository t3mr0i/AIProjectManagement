# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""``project-hub.json`` manifest inside an OpenSpec change folder (PRD §13.5, FR-G02).

Integration identity is the UUID triple ``workspaceId/projectId/workItemId``
plus ``revisionId``. ``readableKey`` (e.g. ``WEB-12``) is orientation only and
is never used to resolve a package.
"""

import re

MANIFEST_SCHEMA = "project-hub-openspec-manifest/1"


class ManifestMismatch(Exception):
    def __init__(self, field, expected, actual):
        self.field, self.expected, self.actual = field, expected, actual
        super().__init__(f"Manifest {field} does not match this package")


def change_id_for(issue) -> str:
    """Default change id: ``<identifier>-<sequence>-<slug>`` (orientation only)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (issue.name or "").lower()).strip("-")[:40].strip("-") or "package"
    identifier = (getattr(issue.project, "identifier", "") or "pkg").lower()
    return f"{identifier}-{issue.sequence_id}-{slug}"


def build_manifest(*, issue, revision_id=None, change_id: str, criteria=()) -> dict:
    return {
        "schema": MANIFEST_SCHEMA,
        "changeId": change_id,
        "workspaceId": str(issue.workspace_id),
        "projectId": str(issue.project_id),
        "workItemId": str(issue.id),
        "revisionId": str(revision_id) if revision_id else None,
        "readableKey": f"{getattr(issue.project, 'identifier', '')}-{issue.sequence_id}",
        "criteria": sorted(str(c.get("id")) for c in criteria if c.get("id")),
    }


def validate_manifest(manifest: dict, issue) -> None:
    """Reject a manifest that belongs to another package (UUIDs only; readable key ignored)."""
    if not manifest:
        return
    for key, expected in (
        ("workspaceId", str(issue.workspace_id)),
        ("projectId", str(issue.project_id)),
        ("workItemId", str(issue.id)),
    ):
        actual = manifest.get(key)
        if actual and str(actual) != expected:
            raise ManifestMismatch(key, expected, actual)
