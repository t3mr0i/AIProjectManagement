#!/usr/bin/env python3
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Administrative re-approval of product skills (PRD §14.4).

Recomputes sha256 for the named skills (or all with --all) and records who approved.
Run only after a human reviewed the skill text diff.
"""

import argparse
import hashlib
import json
import pathlib

SKILLS = pathlib.Path(__file__).resolve().parents[2] / "apps/api/plane/package_flow/skills"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args()
    manifest = json.loads((SKILLS / "manifest.json").read_text())
    for entry in manifest["skills"]:
        if args.all or entry["name"] in args.names:
            entry["sha256"] = hashlib.sha256((SKILLS / entry["name"] / "SKILL.md").read_bytes()).hexdigest()
            entry["approved"] = True
            entry["approved_by"] = args.approved_by
            print(f"approved {entry['name']} {entry['sha256'][:12]}")
    (SKILLS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
