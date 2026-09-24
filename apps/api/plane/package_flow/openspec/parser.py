# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Parse an OpenSpec change folder into an ordered block document (FR-W08).

Guarantees:
* ``"".join(block.raw for block in file_blocks) == original_file_text`` for
  every file, so unknown sections survive byte-for-byte.
* Block ids are stable and derived from structure, not position:
  ``proposal.md#why``, ``specs/auth/spec.md#req:C-1`` (criterion marker) or
  ``specs/auth/spec.md#req:added:two-factor-login`` (no marker).
* Headings inside fenced code blocks are not treated as boundaries.
"""

import json
import re

from .document import MANIFEST_FILE, Block, Document

KNOWN_PROPOSAL_SECTIONS = {
    "why": "why",
    "what changes": "what_changes",
    "impact": "impact",
}
REQ_SECTION_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\s*$", re.I)
REQ_HEADING_RE = re.compile(r"^###\s+Requirement:\s*(.*?)\s*$")
SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(.*?)\s*$")
MARKER_RE = re.compile(r"^\s*<!--\s*ph:criterion\s+id=([A-Za-z0-9_.:\-]+)\s*-->\s*$")
SPEC_PATH_RE = re.compile(r"^specs/([^/]+)/spec\.md$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
PROSE_RE = re.compile(r"^(\n*)(.*?)(\n*)$", re.S)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def file_rank(path: str):
    """Stable file order: proposal, tasks, design, specs, others, manifest."""
    if path == "proposal.md":
        return (0, path)
    if path == "tasks.md":
        return (1, path)
    if path == "design.md":
        return (2, path)
    if SPEC_PATH_RE.match(path):
        return (3, path)
    if path == MANIFEST_FILE:
        return (9, path)
    return (5, path)


def _split(text: str, is_boundary):
    """Split into segments at boundary lines, ignoring fenced code. Returns list of (heading_or_None, raw)."""
    segments = []
    current = []
    heading = None
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if FENCE_RE.match(stripped):
            in_fence = not in_fence
        elif not in_fence and is_boundary(stripped):
            if current or heading is not None:
                segments.append((heading, "".join(current)))
            current = [line]
            heading = stripped
            continue
        current.append(line)
    if current or heading is not None:
        segments.append((heading, "".join(current)))
    return segments


class _Ids:
    def __init__(self):
        self.seen = {}

    def make(self, base: str) -> str:
        n = self.seen.get(base, 0) + 1
        self.seen[base] = n
        return base if n == 1 else f"{base}~{n}"


def _prose_block(block_id, path, kind, heading, raw, extra=None):
    heading_line = raw.splitlines(keepends=True)[0]
    body = raw[len(heading_line) :]
    lead, text, trail = PROSE_RE.match(body).groups()
    content = {"heading": heading.lstrip("#").strip(), "text": text}
    if extra:
        content.update(extra)
    return Block(
        id=block_id,
        file=path,
        kind=kind,
        raw=raw,
        content=content,
        original=dict(content),
        fmt={"heading": heading_line, "lead": lead, "trail": trail},
    )


def _verbatim(block_id, path, kind, raw, content=None):
    content = content or {}
    return Block(id=block_id, file=path, kind=kind, raw=raw, content=content, original=dict(content))


def _parse_proposal(path, text, ids):
    blocks = []
    for heading, raw in _split(text, lambda line: line.startswith("## ")):
        if heading is None:
            blocks.append(_verbatim(ids.make(f"{path}#preamble"), path, "preamble", raw))
            continue
        title = heading[3:].strip()
        kind = KNOWN_PROPOSAL_SECTIONS.get(title.lower())
        if kind:
            blocks.append(_prose_block(ids.make(f"{path}#{kind}"), path, kind, heading, raw))
        else:
            blocks.append(
                _verbatim(ids.make(f"{path}#section:{slugify(title)}"), path, "unknown", raw, {"heading": title})
            )
    return blocks


def _parse_tasks(path, text, ids):
    blocks = []
    for heading, raw in _split(text, lambda line: line.startswith("## ")):
        if heading is None:
            blocks.append(_verbatim(ids.make(f"{path}#preamble"), path, "preamble", raw))
            continue
        title = heading[3:].strip()
        blocks.append(_prose_block(ids.make(f"{path}#tasks:{slugify(title)}"), path, "tasks", heading, raw))
    return blocks


def _parse_requirement(raw, heading):
    name = REQ_HEADING_RE.match(heading).group(1)
    lines = raw.splitlines(keepends=True)[1:]
    parts = []  # [(heading or None, [lines])]
    current_heading, current = None, []
    in_fence = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if FENCE_RE.match(stripped):
            in_fence = not in_fence
        elif not in_fence and stripped.startswith("#### "):
            parts.append((current_heading, current))
            current_heading, current = stripped, []
            continue
        current.append(line)
    parts.append((current_heading, current))

    criterion_id, has_marker = None, False
    body_lines = []
    for line in parts[0][1]:
        match = MARKER_RE.match(line.rstrip("\r\n"))
        if match and not has_marker:
            criterion_id, has_marker = match.group(1), True
            continue
        body_lines.append(line)
    body = "".join(body_lines).strip("\r\n")
    scenarios, unknown_parts = [], []
    for part_heading, part_lines in parts[1:]:
        match = SCENARIO_RE.match(part_heading)
        if match:
            scenarios.append({"name": match.group(1), "text": "".join(part_lines).strip("\r\n")})
        else:
            unknown_parts.append(part_heading + "\n" + "".join(part_lines))
    return name, criterion_id, has_marker, body, scenarios, unknown_parts


def _parse_spec(path, text, ids):
    capability = SPEC_PATH_RE.match(path).group(1)
    blocks = []
    # Two-level split: first by "##", then requirement sections by "###".
    for heading, raw in _split(text, lambda line: line.startswith("## ")):
        if heading is None:
            blocks.append(_verbatim(ids.make(f"{path}#preamble"), path, "preamble", raw))
            continue
        section = REQ_SECTION_RE.match(heading)
        if not section:
            title = heading[3:].strip()
            blocks.append(
                _verbatim(ids.make(f"{path}#section:{slugify(title)}"), path, "unknown", raw, {"heading": title})
            )
            continue
        op = section.group(1).upper()
        sub = _split(raw, lambda line: line.startswith("### "))
        for sub_heading, sub_raw in sub:
            if sub_heading is None:
                blocks.append(
                    _verbatim(ids.make(f"{path}#section:{op.lower()}"), path, "req_section", sub_raw, {"op": op})
                )
                continue
            if not REQ_HEADING_RE.match(sub_heading):
                title = sub_heading[4:].strip()
                blocks.append(
                    _verbatim(
                        ids.make(f"{path}#sub:{op.lower()}:{slugify(title)}"),
                        path,
                        "unknown",
                        sub_raw,
                        {"heading": title},
                    )
                )
                continue
            name, cid, has_marker, body, scenarios, unknown_parts = _parse_requirement(sub_raw, sub_heading)
            if cid:
                block_id = ids.make(f"{path}#req:{cid}")
            else:
                cid = f"{capability}:{slugify(name)}"
                block_id = ids.make(f"{path}#req:{op.lower()}:{slugify(name)}")
            content = {
                "name": name,
                "criterion_id": cid,
                "has_marker": has_marker,
                "operation": op,
                "capability": capability,
                "body": body,
                "scenarios": scenarios,
            }
            blocks.append(
                Block(
                    id=block_id,
                    file=path,
                    kind="requirement",
                    raw=sub_raw,
                    content=content,
                    original=json.loads(json.dumps(content)),
                    unknown_parts=unknown_parts,
                )
            )
    return blocks


def _parse_manifest(path, text, ids):
    try:
        content = json.loads(text)
        if not isinstance(content, dict):
            raise ValueError
    except ValueError:
        # Unparseable manifest is preserved verbatim, never silently rewritten.
        return [_verbatim(ids.make(f"{path}#file"), path, "unknown_file", text)]
    return [Block(id=f"{path}#manifest", file=path, kind="manifest", raw=text, content=content, original=content)]


def normalize_path(path: str, change_prefix: str = "") -> str:
    path = path.replace("\\", "/").lstrip("/")
    if change_prefix and path.startswith(change_prefix.rstrip("/") + "/"):
        path = path[len(change_prefix.rstrip("/")) + 1 :]
    match = re.match(r"^openspec/changes/[^/]+/(.*)$", path)
    if match:
        path = match.group(1)
    return path


def parse_files(files: dict, change_prefix: str = "") -> Document:
    """Parse ``{path: text}`` of one change folder into a ``Document``."""
    normalized = {normalize_path(p, change_prefix): t for p, t in (files or {}).items()}
    blocks = []
    for path in sorted(normalized, key=file_rank):
        text = normalized[path]
        if text is None:
            continue
        ids = _Ids()
        if path == "proposal.md":
            blocks += _parse_proposal(path, text, ids)
        elif path == "tasks.md":
            blocks += _parse_tasks(path, text, ids)
        elif SPEC_PATH_RE.match(path):
            blocks += _parse_spec(path, text, ids)
        elif path == MANIFEST_FILE:
            blocks += _parse_manifest(path, text, ids)
        else:
            blocks.append(_verbatim(f"{path}#file", path, "unknown_file", text))
        if text == "":
            # Keep empty files present in the roundtrip.
            if not any(b.file == path for b in blocks):
                blocks.append(_verbatim(f"{path}#file", path, "unknown_file", ""))
    return Document(blocks=blocks)
