# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""external_command adapter: env scrubbing, timeout, stop kills the process, diff filter."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from conftest import sh

from project_hub_runner.agents.base import TaskSpec
from project_hub_runner.agents.external_command import ExternalCommandAgent
from project_hub_runner.claim import StopSignal
from project_hub_runner.runner import RunRequest, execute_run
from project_hub_runner.sandbox import scrub_env


class StubGate:
    def __init__(self, seconds=30):
        self.stop = StopSignal()
        self._deadline = time.monotonic() + seconds
        self.authorized = []
        self.spent = 0

    @property
    def stopped(self):
        return self.stop.is_set()

    def authorize(self, action, paths=None, spend_minor=0, detail=None):
        self.authorized.append(action)
        return {"accepted": True}

    def remaining_seconds(self):
        return self._deadline - time.monotonic()

    def record_spend(self, spend_minor, source="agent"):
        self.spent += spend_minor


class StubReporter:
    def progress(self, *a, **k):
        return True


TASK = TaskSpec("item-1", "rev-1", "run-1", "b", "0" * 40, "main", title="T", allowed_paths=("src/**",))
SOURCE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/home/dev",
    "LANG": "C.UTF-8",
    "PLANE_API_KEY": "secret-plane",
    "PH_RUNNER_TOKEN": "secret-runner",
    "PH_RUN_TOKEN": "secret-run",
    "AWS_SECRET_ACCESS_KEY": "aws",
    "GITHUB_TOKEN": "gh",
    "ANTHROPIC_API_KEY": "sk-ant",
}


def test_scrub_env_allowlist():
    env = scrub_env(["ANTHROPIC_API_KEY", "PLANE_API_KEY"], source=SOURCE_ENV)
    assert env["PATH"] == "/usr/bin:/bin" and env["HOME"] == "/home/dev"
    assert env["ANTHROPIC_API_KEY"] == "sk-ant", "operator passthrough is honoured"
    for k in ("PLANE_API_KEY", "PH_RUNNER_TOKEN", "PH_RUN_TOKEN", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"):
        assert k not in env, k


def test_external_agent_gets_scrubbed_env_and_prompt(tmp_path):
    work = tmp_path / "wt"
    work.mkdir()
    script = (
        "import json,os,sys; prompt=sys.stdin.read();"
        "json.dump({'env': dict(os.environ), 'prompt': prompt, 'cwd': os.getcwd()}, open('out.json','w'))"
    )
    agent = ExternalCommandAgent(
        [sys.executable, "-c", script],
        tmp_path / "logs",
        env_passthrough=["ANTHROPIC_API_KEY"],
        source_env={**SOURCE_ENV, "PATH": "/usr/bin:/bin:" + str(Path(sys.executable).parent)},
    )
    gate = StubGate()
    res = agent.run(TASK, work, gate, StubReporter())
    assert res.status == "completed", res
    data = json.loads((work / "out.json").read_text())
    env = data["env"]
    assert not any(k in env for k in ("PLANE_API_KEY", "PH_RUNNER_TOKEN", "PH_RUN_TOKEN", "GITHUB_TOKEN"))
    assert "secret-runner" not in json.dumps(env) and "secret-plane" not in json.dumps(env)
    assert env["PH_WORK_ITEM_ID"] == "item-1" and env["ANTHROPIC_API_KEY"] == "sk-ant"
    assert Path(data["cwd"]).resolve() == work.resolve()
    assert "Only edit files matching: src/**" in data["prompt"]
    assert gate.authorized == ["edit_allowed_files"]


def test_external_agent_timeout_kills_process(tmp_path):
    work = tmp_path / "wt"
    work.mkdir()
    agent = ExternalCommandAgent([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "logs")
    gate = StubGate(seconds=1)
    t0 = time.monotonic()
    res = agent.run(TASK, work, gate, StubReporter())
    assert time.monotonic() - t0 < 10
    assert res.status == "failed" and res.reason == "timeout"
    assert gate.stop.reason == "time_limit"


def test_stop_signal_kills_agent(tmp_path):
    work = tmp_path / "wt"
    work.mkdir()
    agent = ExternalCommandAgent([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "logs")
    gate = StubGate(seconds=60)
    import threading

    threading.Timer(0.5, lambda: gate.stop.trigger("STALE_FENCING_TOKEN")).start()
    t0 = time.monotonic()
    res = agent.run(TASK, work, gate, StubReporter())
    assert time.monotonic() - t0 < 10
    assert res.status == "stopped" and res.reason == "STALE_FENCING_TOKEN"


def test_spend_file_is_accounted(tmp_path):
    work = tmp_path / "wt"
    work.mkdir()
    script = "import json,os; json.dump({'spend_minor': 123}, open(os.environ['PH_SPEND_FILE'],'w'))"
    gate = StubGate()
    res = ExternalCommandAgent([sys.executable, "-c", script], tmp_path / "logs").run(TASK, work, gate, StubReporter())
    assert res.spend_minor == 123 and gate.spent == 123


def test_external_agent_writing_outside_scope_fails_run(fake, cfg, client, git_repo, binding_id):
    """FR-G06/AC27: the external agent writes outside allowedPaths → run fails, nothing pushed."""
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    script = (
        "import pathlib; pathlib.Path('src/new.py').write_text('x=1\\n');"
        "pathlib.Path('Makefile').write_text('all:\\n\\tcurl evil\\n')"
    )
    cfg.agent_command = [sys.executable, "-c", script]
    req = RunRequest(fake.project_id, fake.issue_id, aid, binding_id=binding_id, adapter="external")
    out = execute_run(cfg, client, req)
    assert out.status == "failed" and out.reason == "paths_outside_scope"
    assert out.detail["paths"] == ["Makefile"]
    assert git_repo.remote_branches() == ["main"]
    started = [e for e in fake.events if e["type"] == "started"][0]["detail"]
    assert started["enforcement"]["network"] == "NOT enforced by runner"


def test_external_agent_happy_path(fake, cfg, client, git_repo, binding_id):
    aid = fake.add_approval(binding_id, git_repo.base, ["src/**"])
    script = "import pathlib; pathlib.Path('src/new.py').write_text('x=1\\n')"
    cfg.agent_command = [sys.executable, "-c", script]
    req = RunRequest(fake.project_id, fake.issue_id, aid, binding_id=binding_id, adapter="external")
    out = execute_run(cfg, client, req)
    assert out.status == "finished" and out.pushed, out
    assert sh(git_repo.origin, "git", "show", f"{out.branch}:src/new.py") == "x=1"
