#!/usr/bin/env bash
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Project Hub regression gate (FR-B12): native Plane suite + extension suite +
# runner suite + upstream-lock check. Expects the API test environment
# (DATABASE_URL, REDIS_URL, AMQP_URL, SECRET_KEY, WEB_URL) to be exported, or
# run inside `docker compose -f docker-compose-test.yml run --rm api-tests`.
# Baseline failures listed in docs/project-hub/BASELINE.md are reported
# separately and never counted as extension results.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-python}"
status=0

echo "== upstream lock =="
"$PY" "$ROOT/tools/project-hub/verify_upstream_lock.py" || status=1

echo "== Project Hub extension suite =="
(cd "$ROOT/apps/api" && "$PY" -m pytest plane/tests/package_flow -q -p no:cacheprovider -o addopts="--nomigrations") || status=1

echo "== runner suite =="
(cd "$ROOT/apps/runner" && "$PY" -m pytest tests -q -p no:cacheprovider) || status=1

echo "== native Plane suite (baseline failures reported separately) =="
BASELINE="$ROOT/docs/project-hub/baseline-failures.txt"
OUT="$(mktemp)"
(cd "$ROOT/apps/api" && "$PY" -m pytest plane/tests --ignore=plane/tests/package_flow -q -p no:cacheprovider \
  -o addopts="--nomigrations" -rf 2>&1 | tee "$OUT" | tail -3)
NEW_FAIL=$(grep '^FAILED' "$OUT" | sed 's/ - .*//;s/^FAILED //' | sort | comm -23 - <(sort "$BASELINE"))
if [ -n "$NEW_FAIL" ]; then
  echo "New native failures (not in baseline):"; echo "$NEW_FAIL"; status=1
else
  echo "No native failures beyond the documented baseline."
fi
exit $status
