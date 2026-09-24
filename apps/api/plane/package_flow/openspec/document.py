# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Block document model shared by parser, renderer and merge.

A ``Document`` is an ordered list of ``Block`` objects. Every block keeps the
exact source bytes (``raw``) it was parsed from. A block whose structured
``content`` still equals the ``original`` parse result is emitted verbatim, so
an unmodified import -> export roundtrip is byte-identical (FR-W08). Only
blocks that were actually edited are re-rendered from structured content.

Block kinds:
* ``preamble``      text before the first ``##`` heading of a file
* ``why`` / ``what_changes`` / ``impact``   known proposal sections
* ``req_section``   ``## ADDED|MODIFIED|REMOVED|RENAMED Requirements`` header
* ``requirement``   ``### Requirement: ...`` incl. ``#### Scenario:`` blocks
* ``tasks``         one ``##`` section of ``tasks.md``
* ``manifest``      ``project-hub.json``
* ``unknown``       any other section — preserved verbatim, never re-rendered
* ``unknown_file``  any other file in the change folder — preserved verbatim
"""

import copy
import json
from dataclasses import dataclass, field
from typing import Optional

PROSE_KINDS = {"why", "what_changes", "impact", "tasks"}
KNOWN_EDITABLE_KINDS = PROSE_KINDS | {"requirement", "manifest"}
VERBATIM_KINDS = {"preamble", "req_section", "unknown", "unknown_file"}
MANIFEST_FILE = "project-hub.json"


@dataclass
class Block:
    id: str
    file: str
    kind: str
    raw: str = ""
    content: dict = field(default_factory=dict)
    # Structured content as parsed; ``None`` for blocks created by the platform.
    original: Optional[dict] = None
    # Unmodelled sub-parts of a known block (e.g. ``#### Notes`` inside a requirement).
    unknown_parts: list = field(default_factory=list)
    # Whitespace framing of prose blocks: {"heading": "## Why\n", "lead": "\n", "trail": "\n\n"}
    fmt: dict = field(default_factory=dict)

    @property
    def is_modified(self) -> bool:
        return self.original is None or self.content != self.original

    def text(self) -> str:
        if not self.is_modified:
            return self.raw
        return render_block(self)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "kind": self.kind,
            "raw": self.raw,
            "content": self.content,
            "original": self.original,
            "unknown_parts": self.unknown_parts,
            "fmt": self.fmt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            id=data["id"],
            file=data["file"],
            kind=data["kind"],
            raw=data.get("raw", ""),
            content=data.get("content") or {},
            original=data.get("original"),
            unknown_parts=list(data.get("unknown_parts") or []),
            fmt=dict(data.get("fmt") or {}),
        )


@dataclass
class Document:
    blocks: list = field(default_factory=list)
    # Blocks removed by platform edits; used to detect lossy exports (AC08).
    removed: list = field(default_factory=list)

    def get(self, block_id: str) -> Optional[Block]:
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def ids(self) -> list:
        return [b.id for b in self.blocks]

    def files(self) -> list:
        seen = []
        for block in self.blocks:
            if block.file not in seen:
                seen.append(block.file)
        return seen

    def blocks_of(self, file: str) -> list:
        return [b for b in self.blocks if b.file == file]

    def manifest(self) -> dict:
        block = self.get(f"{MANIFEST_FILE}#manifest")
        return dict(block.content) if block else {}

    def copy(self) -> "Document":
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return {"blocks": [b.to_dict() for b in self.blocks]}

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "Document":
        if not data:
            return cls()
        return cls(blocks=[Block.from_dict(b) for b in data.get("blocks", [])])


def render_block(block: Block) -> str:
    """Canonical rendering of an edited block (unmodified blocks use ``raw``)."""
    if block.kind in VERBATIM_KINDS:
        return block.raw
    if block.kind in PROSE_KINDS:
        heading = block.fmt.get("heading") or f"## {block.content.get('heading', '')}\n"
        if not heading.endswith("\n"):
            heading += "\n"
        text = block.content.get("text", "")
        lead = block.fmt.get("lead", "\n")
        trail = block.fmt.get("trail", "")
        if text and not trail:
            trail = "\n\n"
        elif text and not trail.startswith("\n"):
            trail = "\n" + trail
        if not text:
            return heading + lead
        return heading + lead + text + trail
    if block.kind == "requirement":
        c = block.content
        out = [f"### Requirement: {c.get('name', '')}\n"]
        if c.get("has_marker") and c.get("criterion_id"):
            out.append(f"<!-- ph:criterion id={c['criterion_id']} -->\n")
        if c.get("body"):
            out.append(c["body"] + "\n")
        out.append("\n")
        for scenario in c.get("scenarios") or []:
            out.append(f"#### Scenario: {scenario.get('name', '')}\n")
            if scenario.get("text"):
                out.append(scenario["text"] + "\n")
            out.append("\n")
        return "".join(out)
    if block.kind == "manifest":
        return json.dumps(block.content, indent=2, sort_keys=True) + "\n"
    return block.raw
