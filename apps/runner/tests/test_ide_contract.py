# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""FR-G03: both IDE workflows use the same, valid CLI contract."""

from __future__ import annotations

import json
import re
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path

from project_hub_runner.cli import build_parser

IDE = Path(__file__).resolve().parents[1] / "ide"


def _parse(argv):
    return build_parser().parse_args([re.sub(r"\$\{input:[^}]+\}|\$Prompt\$", "x", a) for a in argv])


def test_vscode_tasks_parse():


    """FR-G03: VS Code workflow uses the ph-runner CLI contract."""
    tasks = json.loads((IDE / "vscode-tasks.json").read_text())["tasks"]
    cmds = set()
    for t in tasks:
        assert t["command"] == "ph-runner"
        cmds.add(_parse(t["args"]).cmd)
    assert {"run", "heartbeat", "report", "push", "status", "release"} <= cmds


def test_jetbrains_tools_parse():


    """FR-G03: JetBrains workflow uses the same ph-runner CLI contract."""
    root = ET.parse(IDE / "jetbrains-external-tools.xml").getroot()
    cmds = set()
    for tool in root.iter("tool"):
        opts = {o.get("name"): o.get("value") for o in tool.iter("option")}
        assert opts["COMMAND"] == "ph-runner"
        cmds.add(_parse(shlex.split(opts["PARAMETERS"])).cmd)
    vscode = {_parse(t["args"]).cmd for t in json.loads((IDE / "vscode-tasks.json").read_text())["tasks"]}
    assert cmds == vscode, "both IDE workflows expose the same CLI operations"
