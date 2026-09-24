# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""OpenSpec adapter: block parser, lossless renderer, 3-way merge, manifest (FR-W08, FR-G02, PRD §12.4).

Format basis: OpenSpec change folders (SOURCES S01). A change folder
``openspec/changes/<change-id>/`` is handled as a mapping ``{relative_path: text}``.
"""

from .document import Block, Document  # noqa: F401
from .merge import MergeResult, merge_documents  # noqa: F401
from .parser import parse_files  # noqa: F401
from .renderer import LossyExportError, apply_fields, extract_fields, render_files  # noqa: F401
