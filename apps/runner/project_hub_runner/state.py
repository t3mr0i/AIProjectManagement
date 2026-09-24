# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local state of claims and runs this runner started (0600 files in a 0700 dir).

Only what *this runner* did is recorded — no scanning of other directories
(INV-09). ``last_server_status`` is what the server confirmed at
``last_server_contact_at``; when the server is unreachable the status is shown
as unknown/stale, never as "still running" (FR-G07, AC32).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .config import write_private_json


class StateStore:
    def __init__(self, runner_home: str | Path):
        self.root = Path(runner_home).expanduser() / "state"

    def _dir(self, kind: str) -> Path:
        d = self.root / kind
        d.mkdir(parents=True, exist_ok=True)
        for p in (self.root, d):
            try:
                os.chmod(p, 0o700)
            except OSError:
                pass
        return d

    def _path(self, kind: str, ident: str) -> Path:
        safe = "".join(ch for ch in ident if ch.isalnum() or ch in "-_")
        if not safe:
            raise ValueError("empty id")
        return self._dir(kind) / f"{safe}.json"

    def save(self, kind: str, ident: str, data: dict[str, Any]) -> None:
        data = dict(data)
        data["updated_at"] = time.time()
        write_private_json(self._path(kind, ident), data)

    def load(self, kind: str, ident: str) -> dict[str, Any] | None:
        p = self._path(kind, ident)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def update(self, kind: str, ident: str, **changes: Any) -> dict[str, Any]:
        data = self.load(kind, ident) or {}
        data.update(changes)
        self.save(kind, ident, data)
        return data

    def delete(self, kind: str, ident: str) -> None:
        p = self._path(kind, ident)
        if p.exists():
            p.unlink()

    def list(self, kind: str) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self._dir(kind).glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return out

    # convenience
    def save_run(self, run_id: str, data: dict[str, Any]) -> None:
        self.save("runs", run_id, data)

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        return self.load("runs", run_id)

    def save_claim(self, claim_id: str, data: dict[str, Any]) -> None:
        self.save("claims", claim_id, data)

    def load_claim(self, claim_id: str) -> dict[str, Any] | None:
        return self.load("claims", claim_id)
