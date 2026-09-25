#!/usr/bin/env bash
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Project Hub browser test against the real local stack. apps/web has no Playwright setup, so the
# test is a plain script on the globally installed `playwright` library (no browser download:
# PLAYWRIGHT_BROWSERS_PATH points at the preinstalled Chromium).
#
# Prerequisites: PostgreSQL + Redis running; API env exported (DATABASE_URL, REDIS_URL, SECRET_KEY,
# AMQP_URL, ...) — e.g. `source /tmp/claude-0/testenv-pkg.sh` in the dev container, or apps/api/.env
# from ./setup.sh; node_modules installed; `playwright` available (`npm i -g playwright` or on NODE_PATH).
#
# Usage:
#   tools/project-hub/e2e/run.sh            # migrate, seed, start API :8000 + web :3000 if not up, run, stop what it started
#   E2E_SKIP_MIGRATE=1 tools/project-hub/e2e/run.sh
#   E2E_HEADED=1 tools/project-hub/e2e/run.sh
#
# Output: screenshots in docs/project-hub/screenshots/, logs in $E2E_LOG_DIR (default /tmp/project-hub-e2e).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${PYTHON:-python}"
LOG_DIR="${E2E_LOG_DIR:-/tmp/project-hub-e2e}"
API_URL="${E2E_API:-http://localhost:8000}"
WEB_URL="${E2E_WEB:-http://localhost:3000}"
export E2E_SEED_OUT="${E2E_SEED_OUT:-$LOG_DIR/seed.json}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
export NODE_PATH="${NODE_PATH:-$(npm root -g)}"
mkdir -p "$LOG_DIR"
started=()

cleanup() {
  for pid in "${started[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

wait_for() {
  local url="$1" name="$2"
  for _ in $(seq 1 120); do
    curl -s -o /dev/null "$url" && return 0
    sleep 1
  done
  echo "$name did not come up at $url (see $LOG_DIR)" >&2
  exit 1
}

cd "$ROOT/apps/api"
if [ -z "${E2E_SKIP_MIGRATE:-}" ]; then
  echo "== migrate"
  "$PY" manage.py migrate --noinput >"$LOG_DIR/migrate.log" 2>&1
fi
echo "== seed"
"$PY" manage.py shell <"$ROOT/tools/project-hub/e2e/seed.py" 2>&1 | tail -1

if ! curl -s -o /dev/null "$API_URL/api/instances/"; then
  echo "== start API ($API_URL)"
  CORS_ALLOWED_ORIGINS="$WEB_URL" "$PY" manage.py runserver 0.0.0.0:8000 --noreload >"$LOG_DIR/api.log" 2>&1 &
  started+=("$!")
  wait_for "$API_URL/api/instances/" "API"
fi

if ! curl -s -o /dev/null "$WEB_URL/"; then
  echo "== start web dev server ($WEB_URL)"
  (cd "$ROOT/apps/web" && VITE_API_BASE_URL="$API_URL" VITE_WEB_BASE_URL="$WEB_URL" \
    VITE_ADMIN_BASE_URL=http://localhost:3001 VITE_ADMIN_BASE_PATH=/god-mode \
    VITE_SPACE_BASE_URL=http://localhost:3002 VITE_SPACE_BASE_PATH=/spaces \
    VITE_LIVE_BASE_URL=http://localhost:3100 VITE_LIVE_BASE_PATH=/live \
    exec pnpm dev >"$LOG_DIR/web.log" 2>&1) &
  started+=("$!")
  wait_for "$WEB_URL/" "web"
fi

echo "== browser flow"
cd "$ROOT"
node tools/project-hub/e2e/project-hub.e2e.cjs
