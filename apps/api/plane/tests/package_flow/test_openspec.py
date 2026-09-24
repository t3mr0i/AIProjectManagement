# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure unit tests for the OpenSpec adapter (FR-W08, AC07, AC08, PF08)."""

import pytest

from plane.package_flow.openspec import (
    LossyExportError,
    apply_fields,
    extract_fields,
    merge_documents,
    parse_files,
    render_files,
)
from plane.package_flow.openspec.document import Document

PROPOSAL = """# Change: Add two-factor authentication

## Why
Accounts are compromised through reused passwords.

## What Changes
- Add OTP second factor on login
- **BREAKING** legacy token login removed

## Rollout Notes
Custom team section — unknown to the adapter.
```md
## Not a heading inside a fence
```

## Impact
- Affected specs: auth
- Affected code: apps/api/auth
"""

SPEC = """# Delta for Auth

## ADDED Requirements
### Requirement: Two-Factor Authentication
<!-- ph:criterion id=C-1 -->
The system MUST require a second factor during login.

#### Scenario: OTP required
- **WHEN** a user submits valid credentials
- **THEN** an OTP challenge is required

### Requirement: Recovery Codes
<!-- ph:criterion id=C-2 -->
The system SHALL issue ten recovery codes.

#### Scenario: Codes shown once
- **WHEN** 2FA is enabled
- **THEN** recovery codes are shown exactly once

#### Notes
Internal note block that the adapter does not model.

## MODIFIED Requirements
### Requirement: Session Timeout
Sessions SHALL expire after 30 minutes.

#### Scenario: Idle session
- **WHEN** idle for 30 minutes
- **THEN** the session ends

## Open Questions
- Should SMS be supported?
"""

TASKS = """# Tasks

## 1. Implementation
- [ ] 1.1 Add OTP secret storage
- [x] 1.2 Add verification endpoint
"""

DESIGN = "# Design\n\nUnknown file kept verbatim.\r\nWith CRLF line.\r\n"

MANIFEST = '{\n  "workItemId": "00000000-0000-0000-0000-000000000001",\n  "readableKey": "WEB-1"\n}\n'


def files():
    return {
        "proposal.md": PROPOSAL,
        "tasks.md": TASKS,
        "design.md": DESIGN,
        "specs/auth/spec.md": SPEC,
        "project-hub.json": MANIFEST,
    }


@pytest.mark.unit
class TestParseRender:
    def test_pf08_roundtrip_and_layout_diff_keep_blocks(self):
        """Unmodified import -> export is byte-identical, incl. unknown blocks and files."""
        doc = parse_files(files())
        assert render_files(doc) == files()
        # Serialization through JSON storage keeps the roundtrip lossless.
        again = Document.from_dict(doc.to_dict())
        assert render_files(again) == files()

    def test_paths_with_change_prefix_are_normalized(self):
        prefixed = {f"openspec/changes/web-1-2fa/{k}": v for k, v in files().items()}
        assert render_files(parse_files(prefixed)) == files()

    def test_known_blocks_and_ids(self):
        doc = parse_files(files())
        ids = doc.ids()
        assert "proposal.md#why" in ids
        assert "proposal.md#section:rollout-notes" in ids
        assert "specs/auth/spec.md#req:C-1" in ids
        assert "specs/auth/spec.md#req:modified:session-timeout" in ids
        assert "specs/auth/spec.md#section:open-questions" in ids
        assert "design.md#file" in ids
        # Heading inside fenced code is not a boundary.
        assert not any("not-a-heading" in i for i in ids)
        assert doc.get("proposal.md#section:rollout-notes").kind == "unknown"

    def test_stable_criterion_ids_preserved(self):
        doc = parse_files(files())
        fields = extract_fields(doc)
        ids = [c["id"] for c in fields["criteria"]]
        assert ids == ["C-1", "C-2", "auth:session-timeout"]
        # Edit C-1 text; C-1 marker survives re-rendering.
        fields["criteria"][0]["text"] = "The system MUST require TOTP as second factor."
        out = render_files(apply_fields(doc, fields))
        assert (
            "<!-- ph:criterion id=C-1 -->\nThe system MUST require TOTP as second factor." in out["specs/auth/spec.md"]
        )
        reparsed = extract_fields(parse_files(out))
        assert [c["id"] for c in reparsed["criteria"]] == ids

    def test_ac08_unknown_blocks_preserved(self):
        """Editing a known section keeps unknown sections byte-identical."""
        doc = parse_files(files())
        fields = extract_fields(doc)
        fields["intent"] = "Reused passwords lead to account takeover."
        out = render_files(apply_fields(doc, fields))
        assert "Reused passwords lead to account takeover." in out["proposal.md"]
        assert "## Rollout Notes\nCustom team section — unknown to the adapter.\n```md\n" in out["proposal.md"]
        assert "## Open Questions\n- Should SMS be supported?\n" in out["specs/auth/spec.md"]
        assert out["design.md"] == DESIGN
        assert out["tasks.md"] == TASKS
        # Only the edited block changed.
        assert (
            out["proposal.md"].replace(
                "Reused passwords lead to account takeover.", "Accounts are compromised through reused passwords."
            )
            == PROPOSAL
        )

    def test_lossy_export_is_blocked(self):
        """Editing a requirement that carries an unknown sub-block blocks export visibly."""
        doc = parse_files(files())
        fields = extract_fields(doc)
        fields["criteria"][1]["text"] = "The system SHALL issue twelve recovery codes."
        edited = apply_fields(doc, fields)
        with pytest.raises(LossyExportError) as exc:
            render_files(edited)
        assert exc.value.blocks[0]["block_id"] == "specs/auth/spec.md#req:C-2"
        assert "#### Notes" in exc.value.blocks[0]["unknown_content"][0]

    def test_removing_block_with_unknown_content_is_blocked(self):
        doc = parse_files(files())
        fields = extract_fields(doc)
        fields["criteria"] = [c for c in fields["criteria"] if c["id"] != "C-2"]
        with pytest.raises(LossyExportError):
            render_files(apply_fields(doc, fields))
        # Removing a plain requirement is allowed.
        fields = extract_fields(doc)
        fields["criteria"] = [c for c in fields["criteria"] if c["id"] != "C-1"]
        out = render_files(apply_fields(doc, fields))
        assert "C-1" not in out["specs/auth/spec.md"]

    def test_new_criterion_gets_marker_in_added_section(self):
        doc = parse_files(files())
        fields = extract_fields(doc)
        fields["criteria"].append({"id": "C-9", "text": "Admins SHALL reset 2FA."})
        out = render_files(apply_fields(doc, fields))
        spec = out["specs/auth/spec.md"]
        assert "<!-- ph:criterion id=C-9 -->" in spec
        assert spec.index("C-9") < spec.index("## MODIFIED Requirements")

    def test_render_from_scratch(self):
        doc = apply_fields(
            Document(),
            {"intent": "Why text", "outcome": "What text", "criteria": [{"id": "c1", "text": "It SHALL work."}]},
            title="New package",
            default_capability="billing",
        )
        out = render_files(doc)
        assert out["proposal.md"].startswith("# Change: New package\n\n## Why\n\nWhy text\n\n## What Changes")
        assert "specs/billing/spec.md" in out
        reparsed = extract_fields(parse_files(out))
        assert reparsed["intent"] == "Why text"
        assert reparsed["criteria"][0]["id"] == "c1"


@pytest.mark.unit
class TestThreeWayMerge:
    def _edit(self, doc, **changes):
        fields = extract_fields(doc)
        fields.update(changes)
        return apply_fields(doc, fields)

    def test_non_overlapping_edits_auto_merge(self):
        base = parse_files(files())
        platform = self._edit(base, intent="Platform why.")
        git_files = files()
        git_files["proposal.md"] = PROPOSAL.replace(
            "- Affected code: apps/api/auth", "- Affected code: apps/api/auth, web"
        )
        git = parse_files(git_files)
        result = merge_documents(base, platform, git)
        assert result.is_clean
        out = render_files(result.document)
        assert "Platform why." in out["proposal.md"]
        assert "apps/api/auth, web" in out["proposal.md"]
        assert "## Rollout Notes" in out["proposal.md"]

    def test_ac07_ui_and_ide_edit_same_section_conflict(self):
        base = parse_files(files())
        platform = self._edit(base, intent="UI version of why.")
        git_files = files()
        git_files["proposal.md"] = PROPOSAL.replace(
            "Accounts are compromised through reused passwords.", "IDE version of why."
        )
        result = merge_documents(base, platform, parse_files(git_files))
        assert not result.is_clean
        assert result.document is None  # no last-write-wins
        conflict = result.conflicts[0]
        assert conflict["block_id"] == "proposal.md#why"
        assert "UI version of why." in conflict["platform"]
        assert "IDE version of why." in conflict["git"]
        assert "Accounts are compromised" in conflict["base"]
        # Explicit resolution is required to merge.
        resolved = merge_documents(base, platform, parse_files(git_files), {"proposal.md#why": "git"})
        assert resolved.is_clean
        assert "IDE version of why." in render_files(resolved.document)["proposal.md"]

    def test_identical_change_on_both_sides_is_clean(self):
        base = parse_files(files())
        platform = self._edit(base, intent="Same.")
        git = parse_files(render_files(platform))
        assert merge_documents(base, platform, git).is_clean

    def test_platform_added_criterion_kept_on_git_edit(self):
        base = parse_files(files())
        fields = extract_fields(base)
        fields["criteria"].append({"id": "C-7", "text": "New from UI."})
        platform = apply_fields(base, fields)
        git_files = files()
        git_files["tasks.md"] = TASKS + "- [ ] 1.3 Docs\n"
        result = merge_documents(base, platform, parse_files(git_files))
        assert result.is_clean
        out = render_files(result.document)
        assert "New from UI." in out["specs/auth/spec.md"]
        assert "1.3 Docs" in out["tasks.md"]
