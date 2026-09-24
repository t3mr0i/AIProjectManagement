#!/usr/bin/env python3
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Compare two integrity snapshots (FR-B04, FR-B12, PF04, PF12).

Create snapshots with `python manage.py package_flow_integrity_snapshot --out before.json`
before backup/migration and `--out after.json` after restore/bump, then:

    verify_restore.py before.json after.json

Fails when native IDs, package profiles, revision hashes, approval bindings,
deliveries or decisions were lost or changed. New rows in `after` are allowed.
"""

import json
import sys


def main(before_path, after_path):
    before = json.load(open(before_path))
    after = json.load(open(after_path))
    problems = []
    for table, rows in before["tables"].items():
        after_rows = after["tables"].get(table, {})
        for row_id, digest in rows.items():
            if row_id not in after_rows:
                problems.append(f"{table}: row {row_id} missing after restore")
            elif after_rows[row_id] != digest:
                problems.append(f"{table}: row {row_id} changed ({digest} -> {after_rows[row_id]})")
    for p in problems[:200]:
        print(p)
    if problems:
        print(f"FAILED: {len(problems)} integrity problem(s)")
        return 1
    total = sum(len(r) for r in before["tables"].values())
    print(f"OK: {total} rows across {len(before['tables'])} tables preserved")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
