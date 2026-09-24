# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Three-way merge of OpenSpec block documents by block id (AC07, FR-G02, PRD §12.4).

Inputs: ``base`` (last common synced git snapshot), ``platform`` (working draft
rendered onto base) and ``git`` (incoming IDE/Git version).

Per block id, comparing the rendered block text:
* platform == git            -> take it
* platform unchanged vs base -> take git (incl. deletion)
* git unchanged vs base      -> take platform (incl. deletion)
* otherwise                  -> conflict listing base, platform and git versions.

There is no last-write-wins: a conflict yields no merged document unless the
caller supplies an explicit ``resolutions`` choice per conflicting block.
The manifest is identity metadata, never merged; the git manifest is kept.
"""

from dataclasses import dataclass, field
from typing import Optional

from .document import Block, Document


@dataclass
class MergeResult:
    document: Optional[Document]
    conflicts: list = field(default_factory=list)
    taken_from_platform: list = field(default_factory=list)
    taken_from_git: list = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.conflicts


def _text(block: Optional[Block]):
    return None if block is None else block.text()


def merge_documents(base: Document, platform: Document, git: Document, resolutions: dict = None) -> MergeResult:
    resolutions = resolutions or {}
    base_map = {b.id: b for b in base.blocks}
    plat_map = {b.id: b for b in platform.blocks}
    git_map = {b.id: b for b in git.blocks}

    chosen = {}
    result = MergeResult(document=None)
    all_ids = (
        list(git_map)
        + [i for i in plat_map if i not in git_map]
        + [i for i in base_map if i not in git_map and i not in plat_map]
    )
    for block_id in all_ids:
        b, p, g = base_map.get(block_id), plat_map.get(block_id), git_map.get(block_id)
        if (p or g or b).kind == "manifest":
            chosen[block_id] = g
            continue
        bt, pt, gt = _text(b), _text(p), _text(g)
        if pt == gt:
            chosen[block_id] = g
        elif pt == bt:
            chosen[block_id] = g
            result.taken_from_git.append(block_id)
        elif gt == bt:
            chosen[block_id] = p
            result.taken_from_platform.append(block_id)
        else:
            choice = resolutions.get(block_id)
            if choice == "platform":
                chosen[block_id] = p
                result.taken_from_platform.append(block_id)
            elif choice == "git":
                chosen[block_id] = g
                result.taken_from_git.append(block_id)
            else:
                ref = p or g or b
                result.conflicts.append(
                    {
                        "block_id": block_id,
                        "file": ref.file,
                        "kind": ref.kind,
                        "base": bt,
                        "platform": pt,
                        "git": gt,
                    }
                )
    if result.conflicts:
        return result

    # Order: git order first, platform-only blocks inserted after their platform predecessor.
    ordered = [chosen[i] for i in git_map if chosen.get(i) is not None]
    placed = {b.id for b in ordered}
    previous_in_file = {}
    for block in platform.blocks:
        if block.id not in placed and chosen.get(block.id) is not None:
            previous = previous_in_file.get(block.file)
            if previous is not None:
                index = next((n for n, o in enumerate(ordered) if o.id == previous), len(ordered) - 1)
            else:
                # First block of its file: insert before the first block of that file, if any.
                first = next((n for n, o in enumerate(ordered) if o.file == block.file), None)
                index = (first - 1) if first is not None else len(ordered) - 1
            ordered.insert(index + 1, chosen[block.id])
            placed.add(block.id)
        if block.id in placed:
            previous_in_file[block.file] = block.id
    result.document = Document(blocks=ordered)
    return result
