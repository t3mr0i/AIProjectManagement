#!/usr/bin/env bash
# Builds the web app and the admin (god-mode) app and merges both static
# client bundles into a single output directory served by one Vercel project:
#
#   /            -> apps/web/build/client
#   /god-mode/   -> apps/admin/build/client
#
# API (/api, /auth) requests are proxied to the backend by middleware.ts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/.vercel-dist"

# Same-origin defaults: everything lives on the Vercel domain, so the apps use
# relative URLs. Any of these can be overridden in the Vercel project settings.
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-}"
export VITE_WEB_BASE_URL="${VITE_WEB_BASE_URL:-}"
export VITE_ADMIN_BASE_URL="${VITE_ADMIN_BASE_URL:-}"
export VITE_ADMIN_BASE_PATH="${VITE_ADMIN_BASE_PATH:-/god-mode}"
export VITE_SPACE_BASE_URL="${VITE_SPACE_BASE_URL:-}"
export VITE_SPACE_BASE_PATH="${VITE_SPACE_BASE_PATH:-/spaces}"
export VITE_LIVE_BASE_URL="${VITE_LIVE_BASE_URL:-}"
export VITE_LIVE_BASE_PATH="${VITE_LIVE_BASE_PATH:-/live}"
export TURBO_TELEMETRY_DISABLED=1

cd "$ROOT"
pnpm turbo run build --filter=web --filter=admin

rm -rf "$OUT"
mkdir -p "$OUT"
cp -R apps/web/build/client/. "$OUT/"
mkdir -p "$OUT${VITE_ADMIN_BASE_PATH}"
cp -R apps/admin/build/client/. "$OUT${VITE_ADMIN_BASE_PATH}/"

echo "Vercel output assembled in $OUT"
