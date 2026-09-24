# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""AC05 (atomic exclusive claim) and AC06 (stale fencing stops actions)."""

from __future__ import annotations

import threading
import time

import pytest

from project_hub_runner.claim import StopSignal, Supervisor, acquire_claim, heartbeat_once
from project_hub_runner.client import Client
from project_hub_runner.errors import ActionsStopped, ClaimHeld, LeaseExpired, StaleFencingToken
from project_hub_runner.manifest import fetch_manifest
from project_hub_runner.policy import PolicyGate, Rules


def _client(fake, token):
    return Client(fake.url, "ws", token, timeout=5, retries=0)


def test_concurrent_exclusive_claims_exactly_one_owner(fake):
    tokens = ["tok-A", "tok-B", "tok-C"] * 4
    results, errors = [], []
    barrier = threading.Barrier(len(tokens))

    def attempt(tok):
        barrier.wait()
        try:
            results.append(acquire_claim(_client(fake, tok), fake.project_id, fake.issue_id, "bind-1"))
        except ClaimHeld as exc:
            errors.append(exc)

    threads = [threading.Thread(target=attempt, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 1
    assert len(errors) == len(tokens) - 1
    assert all(e.code == "CLAIM_HELD" and e.holder for e in errors)


def test_shared_claims_are_explicit(fake):
    a = acquire_claim(_client(fake, "tok-A"), fake.project_id, fake.issue_id, "b", exclusive=False)
    b = acquire_claim(_client(fake, "tok-B"), fake.project_id, fake.issue_id, "b", exclusive=False)
    assert a.id != b.id
    with pytest.raises(ClaimHeld):
        acquire_claim(_client(fake, "tok-C"), fake.project_id, fake.issue_id, "b", exclusive=True)


def test_heartbeat_renews_and_expired_lease_is_reported(fake):
    c = _client(fake, "tok-A")
    claim = acquire_claim(c, fake.project_id, fake.issue_id, None, lease_seconds=30)
    assert heartbeat_once(c, claim)["lease_seconds"] == 30
    fake.expire_claim(claim.id)
    with pytest.raises(LeaseExpired):
        heartbeat_once(c, claim)


def _start_run(fake, client, claim, binding, base):
    aid = fake.add_approval(binding, base, ["src/**"])
    resp = client.start_run(fake.project_id, fake.issue_id, aid, claim.id)
    return resp["run"]["id"], resp["run_token"]


def test_stale_fencing_stops_all_further_actions(fake, git_repo):
    """AC06: A's lease expires, B claims; A's heartbeat and actions are refused and A stops locally."""
    a_client, b_client = _client(fake, "tok-A"), _client(fake, "tok-B")
    claim_a = acquire_claim(a_client, fake.project_id, fake.issue_id, "bind", lease_seconds=30)
    run_id, run_token = _start_run(fake, a_client, claim_a, "bind", git_repo.base)
    manifest = fetch_manifest(a_client, run_id, run_token)
    stop = StopSignal()
    gate = PolicyGate(Rules.from_manifest(manifest), a_client, run_token, claim_a, stop)
    gate.authorize("edit_allowed_files", paths=["src/x.py"])  # valid while we own the lease

    killed = []
    stop.on_stop(killed.append)
    sup = Supervisor(a_client, claim_a, stop, interval=0.05)
    fake.expire_claim(claim_a.id)
    claim_b = acquire_claim(b_client, fake.project_id, fake.issue_id, "bind")
    assert claim_b.fencing_token > claim_a.fencing_token
    sup.start()
    assert stop.wait(3), "supervisor must stop on LEASE_EXPIRED"
    sup.halt()
    assert stop.reason == "LEASE_EXPIRED"
    assert killed == ["LEASE_EXPIRED"], "stop callbacks (e.g. kill agent) must fire"

    n_actions = len(fake.actions)
    with pytest.raises(ActionsStopped):
        gate.authorize("push_work_branch", paths=["src/x.py"])
    assert len(fake.actions) == n_actions, "a stopped gate must not even contact the server"


def test_stale_token_action_rejected_by_server_triggers_stop(fake, git_repo):
    a_client = _client(fake, "tok-A")
    claim = acquire_claim(a_client, fake.project_id, fake.issue_id, "bind")
    run_id, run_token = _start_run(fake, a_client, claim, "bind", git_repo.base)
    manifest = fetch_manifest(a_client, run_id, run_token)
    stop = StopSignal()
    gate = PolicyGate(Rules.from_manifest(manifest), a_client, run_token, claim, stop)
    claim.fencing_token -= 1  # simulate an old token
    with pytest.raises(StaleFencingToken):
        gate.authorize("create_commit", paths=["src/a.py"])
    assert stop.is_set() and stop.reason == "STALE_FENCING_TOKEN"
    with pytest.raises(ActionsStopped):
        gate.authorize("create_commit", paths=["src/a.py"])


def test_supervisor_stops_when_server_unreachable_past_lease(fake):
    c = _client(fake, "tok-A")
    claim = acquire_claim(c, fake.project_id, fake.issue_id, None, lease_seconds=30)
    dead = Client("http://127.0.0.1:9", "ws", "tok-A", timeout=0.2, retries=0)
    claim.local_deadline = time.monotonic() - 1  # lease can no longer be confirmed
    stop = StopSignal()
    Supervisor(dead, claim, stop, interval=0.05).tick()
    assert stop.is_set() and stop.reason == "lease_unconfirmed"
