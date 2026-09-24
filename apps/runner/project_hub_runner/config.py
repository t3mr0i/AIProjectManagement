# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local runner configuration (``~/.config/project-hub/runner.json``, mode 0600).

Holds the server URL, workspace slug and the runner token issued once by
``POST W/runners/``. This file is operator-controlled local configuration;
repository content can never change it (AC27).

Everything the runner stores on disk that is a secret (runner token, run
tokens in run state files) is written with mode 0600 in 0700 directories.
The platform repository and managed repositories never share this file or
any credential in it (PRD §13.1).
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import ConfigError

ENV_CONFIG_PATH = "PH_RUNNER_CONFIG"


def default_config_path() -> Path:
    env = os.environ.get(ENV_CONFIG_PATH)
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "project-hub" / "runner.json"


def default_runner_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "project-hub-runner"


@dataclass
class BindingConfig:
    """Where the runner finds a local clone for a repository binding.

    The clone is only used as a git object store: all work happens in a
    separate runner-owned worktree (FR-G02).
    """

    path: str
    remote: str = "origin"


@dataclass
class RunnerConfig:
    server: str
    workspace: str
    token: str
    runner_home: str = ""
    bindings: dict[str, BindingConfig] = field(default_factory=dict)
    # External coding-agent command, e.g. ["claude", "-p"]. Operator-controlled.
    agent_command: list[str] = field(default_factory=list)
    # Extra env vars the operator allows through to the agent subprocess.
    env_passthrough: list[str] = field(default_factory=list)
    # Optional OS/container sandbox prefix, e.g. ["firejail", "--net=none", "--"] (INV-10).
    sandbox_prefix: list[str] = field(default_factory=list)
    # Seconds between heartbeats; 0 = lease_seconds / 3.
    heartbeat_interval: float = 0.0
    lease_seconds: int = 300
    request_timeout: float = 15.0

    @property
    def home(self) -> Path:
        return Path(self.runner_home).expanduser() if self.runner_home else default_runner_home()

    def binding(self, binding_id: str) -> BindingConfig | None:
        return self.bindings.get(binding_id)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["bindings"] = {k: asdict(v) for k, v in self.bindings.items()}
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunnerConfig:
        try:
            bindings = {
                str(k): BindingConfig(**v) if isinstance(v, dict) else BindingConfig(path=str(v))
                for k, v in (data.get("bindings") or {}).items()
            }
            return cls(
                server=str(data["server"]).rstrip("/"),
                workspace=str(data["workspace"]),
                token=str(data["token"]),
                runner_home=str(data.get("runner_home") or ""),
                bindings=bindings,
                agent_command=[str(x) for x in data.get("agent_command") or []],
                env_passthrough=[str(x) for x in data.get("env_passthrough") or []],
                sandbox_prefix=[str(x) for x in data.get("sandbox_prefix") or []],
                heartbeat_interval=float(data.get("heartbeat_interval") or 0.0),
                lease_seconds=int(data.get("lease_seconds") or 300),
                request_timeout=float(data.get("request_timeout") or 15.0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid runner config: {exc}") from exc


def validate_server_url(url: str, allow_insecure_http: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ConfigError(f"server URL must be http(s)://host[:port], got {url!r}")
    if parsed.scheme == "http" and not allow_insecure_http:
        host = (parsed.hostname or "").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise ConfigError("refusing plain http for a non-local server (token would be sent in clear); use https")
    return url.rstrip("/")


def _write_private(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save_config(cfg: RunnerConfig, path: Path | None = None) -> Path:
    path = path or default_config_path()
    _write_private(path, cfg.to_json())
    return path


def load_config(path: Path | None = None) -> RunnerConfig:
    path = path or default_config_path()
    if not path.exists():
        raise ConfigError(f"no runner config at {path}; run `ph-runner login` first")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        print(
            f"warning: {path} is readable by group/others (mode {oct(mode)}); fixing to 0600",
            file=sys.stderr,
        )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read runner config {path}: {exc}") from exc
    return RunnerConfig.from_json(data)


def login(
    server: str,
    workspace: str,
    token: str,
    path: Path | None = None,
    allow_insecure_http: bool = False,
    runner_home: str = "",
) -> Path:
    """Store credentials locally. Existing bindings/agent settings are preserved."""
    server = validate_server_url(server, allow_insecure_http)
    if not workspace or not token:
        raise ConfigError("workspace and token are required")
    path = path or default_config_path()
    existing: RunnerConfig | None = None
    if path.exists():
        try:
            existing = load_config(path)
        except ConfigError:
            existing = None
    cfg = existing or RunnerConfig(server=server, workspace=workspace, token=token)
    cfg.server, cfg.workspace, cfg.token = server, workspace, token
    if runner_home:
        cfg.runner_home = runner_home
    return save_config(cfg, path)


def mask_token(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return token[:4] + "…" + token[-2:]


write_private_json = _write_private
