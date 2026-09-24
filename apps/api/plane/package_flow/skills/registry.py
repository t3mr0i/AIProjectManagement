# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Versioned, administratively approved product skills (PRD §14.4).

Skills describe desired agent behaviour; they are **not** a security boundary.
Only skills whose content hash matches the approved manifest are served to
agents/runners. A repository cannot add platform rights by shipping a new
skill file: repository-provided skills are never loaded from here.
"""

import hashlib
import json
import pathlib

SKILLS_DIR = pathlib.Path(__file__).resolve().parent
MANIFEST = SKILLS_DIR / "manifest.json"


def content_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text())


def approved_skills():
    """Return [{name, version, sha256, text}] for skills matching the approved manifest.

    A skill whose file changed after approval is withheld (status: changed)
    until an administrator re-approves it by updating the manifest.
    """
    result = []
    for entry in load_manifest()["skills"]:
        path = SKILLS_DIR / entry["name"] / "SKILL.md"
        if not path.exists():
            result.append({**entry, "status": "missing"})
            continue
        actual = content_hash(path)
        if not entry.get("approved") or actual != entry["sha256"]:
            result.append({**entry, "status": "changed" if entry.get("approved") else "unapproved"})
            continue
        result.append({**entry, "status": "approved", "text": path.read_text()})
    return result
