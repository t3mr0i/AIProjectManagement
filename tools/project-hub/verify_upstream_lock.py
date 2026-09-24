#!/usr/bin/env python3
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""FR-B01 / PF01: verify that the build commit is based on the locked upstream commit.

Checks:
1. docs/project-hub/upstream-lock.json exists and names implementationCommit.
2. implementationCommit is an ancestor of HEAD (the fork was not rebased onto another upstream state).
3. Optional (--upstream-remote NAME): every commit reachable from the remote-tracking upstream branch
   that is also contained in HEAD is contained in implementationCommit, i.e. no newer upstream commit
   was merged without updating the lock.
Exit code 0 = consistent, 1 = mismatch.
"""

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-remote", help="remote-tracking branch of upstream, e.g. upstream/preview")
    args = parser.parse_args()

    lock = json.loads((ROOT / "docs/project-hub/upstream-lock.json").read_text())
    commit = lock.get("implementationCommit")
    if not commit:
        print("upstream-lock.json has no implementationCommit")
        return 1
    if git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        print(f"locked commit {commit} is not present in this clone (fetch more history)")
        return 1
    if git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        print(f"locked commit {commit} is not an ancestor of HEAD")
        return 1
    if args.upstream_remote:
        extra = git("rev-list", "HEAD", f"^{commit}", args.upstream_remote).stdout.split()
        upstream_in_head = [c for c in extra if git("merge-base", "--is-ancestor", c, "HEAD").returncode == 0]
        if upstream_in_head:
            print(f"{len(upstream_in_head)} upstream commit(s) newer than the lock are merged into HEAD")
            return 1
    head = git("rev-parse", "HEAD").stdout.strip()
    print(f"OK: HEAD {head} is based on locked upstream commit {commit}; licensePathApproved={lock.get('licensePathApproved')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
