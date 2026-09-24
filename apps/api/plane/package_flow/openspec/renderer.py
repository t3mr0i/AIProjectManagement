# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Render a block document to OpenSpec files and map it to/from package fields.

* Unmodified blocks are emitted from ``raw`` → unmodified roundtrip is byte-identical.
* Unknown sections/files are never re-rendered; they are always re-emitted verbatim.
* If an edit would drop content we cannot model (unknown sub-parts of an edited
  requirement, removal of a block carrying unknown content), the export is
  blocked with ``LossyExportError`` instead of silently losing data (AC08, FR-W08).

Field mapping (package working draft <-> OpenSpec):
  intent  <-> proposal.md ``## Why``
  outcome <-> proposal.md ``## What Changes``
  scope.impact <-> proposal.md ``## Impact``
  scope.tasks  <-> tasks.md ``##`` sections
  criteria[]   <-> ``### Requirement:`` blocks (stable id via ``<!-- ph:criterion id=... -->``)
"""

import copy

from .document import MANIFEST_FILE, Block, Document
from .parser import file_rank, slugify

PROPOSAL_ORDER = ["preamble", "why", "what_changes", "impact"]
HEADINGS = {"why": "Why", "what_changes": "What Changes", "impact": "Impact"}


class LossyExportError(Exception):
    """Export would lose unknown/unmodelled content; nothing is written."""

    def __init__(self, blocks):
        self.blocks = blocks
        super().__init__("Export would drop unknown OpenSpec content: " + ", ".join(b["block_id"] for b in blocks))


def lossy_blocks(doc: Document) -> list:
    problems = []
    for block in doc.blocks:
        if block.unknown_parts and block.original is not None and block.is_modified:
            problems.append(
                {
                    "block_id": block.id,
                    "reason": "edited block contains unknown sub-sections that cannot be re-rendered",
                    "unknown_content": block.unknown_parts,
                }
            )
    for block in doc.removed:
        if block.kind in ("unknown", "unknown_file") or block.unknown_parts:
            problems.append(
                {
                    "block_id": block.id,
                    "reason": "removing this block would delete unknown content",
                    "unknown_content": block.unknown_parts or [block.raw],
                }
            )
    return problems


def render_files(doc: Document, *, allow_lossy: bool = False) -> dict:
    """Render ``{relative_path: text}``. Raises ``LossyExportError`` unless ``allow_lossy``."""
    if not allow_lossy:
        problems = lossy_blocks(doc)
        if problems:
            raise LossyExportError(problems)
    files = {}
    for path in sorted(doc.files(), key=file_rank):
        files[path] = "".join(block.text() for block in doc.blocks_of(path))
    return files


# ---------------------------------------------------------------------------
# Document -> package fields
# ---------------------------------------------------------------------------


def _task_items(text: str) -> list:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.lower().startswith("- [x]"):
            items.append({"done": stripped[3].lower() == "x", "text": stripped[5:].strip()})
    return items


def extract_fields(doc: Document) -> dict:
    """Map known blocks to package working-draft fields. Unknown blocks are not fields."""
    fields = {"intent": "", "outcome": "", "scope": {}, "criteria": []}
    tasks = []
    for block in doc.blocks:
        c = block.content
        if block.kind == "why":
            fields["intent"] = c.get("text", "")
        elif block.kind == "what_changes":
            fields["outcome"] = c.get("text", "")
        elif block.kind == "impact":
            fields["scope"]["impact"] = c.get("text", "")
        elif block.kind == "tasks":
            tasks.append(
                {
                    "id": block.id,
                    "heading": c.get("heading", ""),
                    "text": c.get("text", ""),
                    "items": _task_items(c.get("text", "")),
                }
            )
        elif block.kind == "requirement":
            fields["criteria"].append(
                {
                    "id": c.get("criterion_id"),
                    "text": c.get("body", ""),
                    "requirement": c.get("name", ""),
                    "operation": c.get("operation", "ADDED"),
                    "capability": c.get("capability", ""),
                    "scenarios": copy.deepcopy(c.get("scenarios") or []),
                }
            )
    if tasks:
        fields["scope"]["tasks"] = tasks
    return fields


# ---------------------------------------------------------------------------
# Package fields -> document
# ---------------------------------------------------------------------------


def _insert_after(doc: Document, block: Block, predicate):
    """Insert ``block`` after the last block matching ``predicate`` (else at end of its file / doc)."""
    index = None
    for i, existing in enumerate(doc.blocks):
        if predicate(existing):
            index = i
    if index is None:
        for i, existing in enumerate(doc.blocks):
            if existing.file == block.file:
                index = i
    if index is None:
        # New file: keep global file order stable.
        rank = file_rank(block.file)
        index = -1
        for i, existing in enumerate(doc.blocks):
            if file_rank(existing.file) <= rank:
                index = i
    doc.blocks.insert(index + 1, block)


def _new_prose(block_id, path, kind, heading, text):
    return Block(
        id=block_id,
        file=path,
        kind=kind,
        content={"heading": heading, "text": text},
        original=None,
        fmt={"heading": f"## {heading}\n", "lead": "\n", "trail": "\n\n"},
    )


def _set_prose(doc: Document, kind: str, text: str, title: str):
    block = next((b for b in doc.blocks if b.kind == kind and b.file == "proposal.md"), None)
    if block is not None:
        block.content = {**block.content, "text": text}
        return
    if not text:
        return
    if not doc.blocks_of("proposal.md"):
        preamble = f"# Change: {title or 'Package'}\n\n"
        _insert_after(
            doc,
            Block(
                id="proposal.md#preamble", file="proposal.md", kind="preamble", raw=preamble, original={}, content={}
            ),
            lambda b: False,
        )
    rank = PROPOSAL_ORDER.index(kind)
    _insert_after(
        doc,
        _new_prose(f"proposal.md#{kind}", "proposal.md", kind, HEADINGS[kind], text),
        lambda b: b.file == "proposal.md" and b.kind in PROPOSAL_ORDER and PROPOSAL_ORDER.index(b.kind) < rank,
    )


def _requirement_name(criterion: dict) -> str:
    name = (criterion.get("requirement") or criterion.get("name") or "").strip()
    if name:
        return name
    text = (criterion.get("text") or "").strip().splitlines()
    first = text[0] if text else str(criterion.get("id"))
    return first[:80].rstrip(" .")


def _ensure_section(doc: Document, path: str, op: str):
    section_id = f"{path}#section:{op.lower()}"
    if doc.get(section_id) is None:
        raw = f"## {op} Requirements\n\n"
        _insert_after(
            doc,
            Block(id=section_id, file=path, kind="req_section", raw=raw, content={"op": op}, original={"op": op}),
            lambda b: b.file == path,
        )
    return section_id


def _set_criteria(doc: Document, criteria: list, default_capability: str):
    by_cid = {b.content.get("criterion_id"): b for b in doc.blocks if b.kind == "requirement"}
    existing_caps = [b.content.get("capability") for b in doc.blocks if b.kind == "requirement"]
    if existing_caps and existing_caps[0]:
        # New criteria join the change's existing capability unless they name another one.
        default_capability = existing_caps[0]
    wanted = set()
    for criterion in criteria or []:
        cid = str(criterion.get("id") or "").strip()
        if not cid:
            continue
        wanted.add(cid)
        block = by_cid.get(cid)
        if block is not None:
            content = dict(block.content)
            if criterion.get("requirement") or criterion.get("name"):
                content["name"] = _requirement_name(criterion)
            if "text" in criterion:
                content["body"] = criterion.get("text") or ""
            if "scenarios" in criterion:
                content["scenarios"] = copy.deepcopy(criterion.get("scenarios") or [])
            block.content = content
            continue
        capability = slugify(criterion.get("capability") or default_capability or "package")
        op = (criterion.get("operation") or "ADDED").upper()
        path = f"specs/{capability}/spec.md"
        section_id = _ensure_section(doc, path, op)
        new = Block(
            id=f"{path}#req:{cid}",
            file=path,
            kind="requirement",
            content={
                "name": _requirement_name(criterion),
                "criterion_id": cid,
                "has_marker": True,
                "operation": op,
                "capability": capability,
                "body": criterion.get("text") or "",
                "scenarios": copy.deepcopy(criterion.get("scenarios") or []),
            },
            original=None,
        )
        # Append at the end of the matching requirement section.
        section_seen = {"inside": False}

        def in_section(b, _path=path, _section=section_id, _state=section_seen):
            if b.id == _section:
                _state["inside"] = True
                return True
            if b.file != _path:
                return False
            if b.kind in ("req_section",) or (b.kind == "unknown" and "#section:" in b.id):
                _state["inside"] = False
            return _state["inside"]

        _insert_after(doc, new, in_section)
        by_cid[cid] = new
    for block in list(doc.blocks):
        if block.kind == "requirement" and block.content.get("criterion_id") not in wanted:
            doc.blocks.remove(block)
            doc.removed.append(block)


def _set_tasks(doc: Document, tasks: list):
    for task in tasks or []:
        block = doc.get(task.get("id") or "")
        if block is not None and block.kind == "tasks":
            text = task.get("text")
            if text is None and task.get("items") is not None:
                text = "\n".join(f"- [{'x' if i.get('done') else ' '}] {i.get('text', '')}" for i in task["items"])
            if text is not None:
                block.content = {**block.content, "text": text}
            continue
        heading = task.get("heading") or "Tasks"
        text = task.get("text") or "\n".join(
            f"- [{'x' if i.get('done') else ' '}] {i.get('text', '')}" for i in task.get("items") or []
        )
        if not text:
            continue
        _insert_after(
            doc,
            _new_prose(f"tasks.md#tasks:{slugify(heading)}", "tasks.md", "tasks", heading, text),
            lambda b: b.file == "tasks.md",
        )


def apply_fields(
    doc: Document,
    fields: dict,
    *,
    title: str = "",
    default_capability: str = "package",
    manifest: dict = None,
) -> Document:
    """Return a copy of ``doc`` with package working-draft ``fields`` applied.

    Unknown blocks are never touched. Known blocks absent from ``fields`` stay as they are.
    """
    doc = doc.copy()
    if "intent" in fields:
        _set_prose(doc, "why", fields.get("intent") or "", title)
    if "outcome" in fields:
        _set_prose(doc, "what_changes", fields.get("outcome") or "", title)
    scope = fields.get("scope") or {}
    if "impact" in scope:
        _set_prose(doc, "impact", scope.get("impact") or "", title)
    if "tasks" in scope:
        _set_tasks(doc, scope.get("tasks"))
    if "criteria" in fields:
        _set_criteria(doc, fields.get("criteria") or [], default_capability)
    if manifest is not None:
        block = doc.get(f"{MANIFEST_FILE}#manifest")
        if block is None:
            block = Block(id=f"{MANIFEST_FILE}#manifest", file=MANIFEST_FILE, kind="manifest", original=None)
            doc.blocks.append(block)
        merged = {**(block.content or {}), **manifest}
        block.content = merged
    return doc
