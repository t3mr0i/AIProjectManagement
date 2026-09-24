# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""HTTP client behaviour, offline status (FR-G07/AC32), config and CLI basics."""

from __future__ import annotations

import os
import stat
import time

import pytest

from project_hub_runner.cli import main
from project_hub_runner.client import Client
from project_hub_runner.config import load_config, login, save_config
from project_hub_runner.errors import (
    ClaimHeld,
    ConfigError,
    RevisionNotApproved,
    ServerError,
    ServerUnreachable,
    StaleFencingToken,
    error_for,
)
from project_hub_runner.runner import server_run_status
from project_hub_runner.state import StateStore


def test_error_mapping():
    assert isinstance(error_for(409, {"code": "STALE_FENCING_TOKEN", "error": "x"}), StaleFencingToken)
    held = error_for(409, {"code": "CLAIM_HELD", "detail": {"holder": "u1"}})
    assert isinstance(held, ClaimHeld) and held.holder == "u1"
    assert isinstance(error_for(422, {"code": "REVISION_NOT_APPROVED"}), RevisionNotApproved)
    assert isinstance(error_for(502, None), ServerError)


def test_retries_5xx_but_not_4xx(fake):
    c = Client(fake.url, "ws", "tok-A", retries=2, backoff=0.001)
    fake.fail_next = [503, 502]
    claim = c.create_claim(fake.project_id, fake.issue_id)
    assert claim["fencing_token"] == 1
    posts = [r for r in fake.requests if r[0] == "POST"]
    assert len(posts) == 3, "two 5xx retried with the same idempotency key"

    n = len(fake.requests)
    with pytest.raises(StaleFencingToken):
        c.heartbeat(claim["id"], 999)
    assert len(fake.requests) == n + 1, "409 must not be retried"


def test_idempotent_retry_does_not_duplicate_claim(fake):
    c = Client(fake.url, "ws", "tok-A", retries=0)
    first = c.create_claim(fake.project_id, fake.issue_id, idempotency_key="k1")
    again = c.create_claim(fake.project_id, fake.issue_id, idempotency_key="k1")
    assert first == again and len(fake.claims) == 1


def test_unreachable_server_raises_typed_error():
    c = Client("http://127.0.0.1:9", "ws", "t", timeout=0.2, retries=1, backoff=0.001)
    with pytest.raises(ServerUnreachable):
        c.list_runs("p", "i")


def test_offline_status_is_unknown_not_running(tmp_path, capsys):
    """AC32/FR-G07: without the server, local state is reported as unknown/stale, never as live."""
    home = tmp_path / "home"
    store = StateStore(home)
    saved = {
        "run_id": "run-1",
        "project_id": "p",
        "work_item_id": "i",
        "last_server_status": "running",
        "last_server_contact_at": time.time() - 3600,
        "local_status": "working",
        "claim": {"id": "c", "fencing_token": 1, "project_id": "p", "work_item_id": "i"},
        "run_token": "rt",
    }
    store.save_run("run-1", saved)
    dead = Client("http://127.0.0.1:9", "ws", "t", timeout=0.2, retries=0)
    s = server_run_status(dead, saved)
    assert s["status"] == "unknown" and s["stale"] is True
    assert s["last_confirmed_status"] == "running"

    cfg_path = tmp_path / "runner.json"
    login("http://127.0.0.1:9", "ws", "tok", path=cfg_path, runner_home=str(home))
    rc = main(["--config", str(cfg_path), "status"])
    out = capsys.readouterr().out
    assert rc == 6
    assert "server=unknown" in out and "UNKNOWN" in out and "stale" in out
    assert "server=running" not in out


def test_login_writes_private_config(tmp_path):
    path = tmp_path / "cfg" / "runner.json"
    login("https://plane.example.com/", "acme", "secret-token", path=path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    cfg = load_config(path)
    assert cfg.server == "https://plane.example.com" and cfg.token == "secret-token"
    with pytest.raises(ConfigError):
        login("http://plane.example.com", "acme", "t", path=path)
    login("http://localhost:8000", "acme", "t2", path=path)  # local http is fine for dev
    os.chmod(path, 0o644)
    load_config(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_cli_claim_and_release(fake, tmp_path, capsys):
    path = tmp_path / "runner.json"
    login(fake.url, "ws", "tok-A", path=path, runner_home=str(tmp_path / "h"))
    assert (
        main(["--config", str(path), "--json", "claim", "--project", fake.project_id, "--work-item", fake.issue_id])
        == 0
    )
    claim_id = next(iter(fake.claims))
    # second exclusive claim by another runner → CLAIM_HELD, exit 3
    path_b = tmp_path / "runner-b.json"
    login(fake.url, "ws", "tok-B", path=path_b, runner_home=str(tmp_path / "hb"))
    assert main(["--config", str(path_b), "claim", "--project", fake.project_id, "--work-item", fake.issue_id]) == 3
    assert main(["--config", str(path), "heartbeat", "--claim", claim_id]) == 0
    assert main(["--config", str(path), "release", "--claim", claim_id]) == 0
    assert fake.claims[claim_id]["status"] == "released"


def test_cli_whoami(fake, tmp_path, capsys):
    path = tmp_path / "runner.json"
    login(fake.url, "ws", "tok-A-long-token", path=path)
    save_config(load_config(path), path)
    fake.runner_tokens["tok-A-long-token"] = "runner-A"
    assert main(["--config", str(path), "whoami"]) == 0
    out = capsys.readouterr().out
    assert "tok-A-long-token" not in out and "runner-A" in out
