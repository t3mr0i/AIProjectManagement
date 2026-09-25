#!/bin/bash
# Entrypoint for the single-container Fly.io image.
#
# - Derives Plane's URLs from PUBLIC_URL (default: https://$FLY_APP_NAME.fly.dev)
# - Generates SECRET_KEY / LIVE_SERVER_SECRET_KEY once and keeps them on /data
# - Runs Postgres and Redis locally on /data unless DATABASE_URL / REDIS_URL are set
# - Maps Tigris storage secrets (fly storage create) to Plane's AWS_* variables
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [ -z "${PUBLIC_URL:-}" ]; then
  if [ -n "${FLY_APP_NAME:-}" ]; then
    PUBLIC_URL="https://${FLY_APP_NAME}.fly.dev"
  else
    PUBLIC_URL="http://localhost:8080"
  fi
fi
PUBLIC_URL="${PUBLIC_URL%/}"
export PUBLIC_URL

# --- Persistent secrets -----------------------------------------------------
SECRETS_FILE="$DATA_DIR/secrets.env"
touch "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"
ensure_secret() {
  local key="$1"
  if [ -n "${!key:-}" ]; then
    export "$key"
    return
  fi
  local stored
  stored=$(grep "^${key}=" "$SECRETS_FILE" | cut -d= -f2- || true)
  if [ -z "$stored" ]; then
    stored=$(tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 50 || true)
    echo "${key}=${stored}" >>"$SECRETS_FILE"
  fi
  export "$key=$stored"
}
ensure_secret SECRET_KEY
ensure_secret LIVE_SERVER_SECRET_KEY

# --- Postgres -----------------------------------------------------------------
export RUN_LOCAL_POSTGRES=false
if [ -z "${DATABASE_URL:-}" ]; then
  RUN_LOCAL_POSTGRES=true
  PGDATA="$DATA_DIR/postgres"
  export PGDATA
  mkdir -p "$PGDATA" /run/postgresql
  chown -R postgres:postgres "$PGDATA" /run/postgresql
  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Initializing local Postgres in $PGDATA"
    su-exec postgres initdb -D "$PGDATA" -U plane --auth-local=trust --auth-host=trust --encoding=UTF8 >/dev/null
    su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses=127.0.0.1" -w start >/dev/null
    su-exec postgres createdb -h 127.0.0.1 -U plane plane
    su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null
  fi
  export DATABASE_URL="postgresql://plane@127.0.0.1:5432/plane"
fi

# --- Redis (cache, live server, and Celery broker) ------------------------------
export RUN_LOCAL_REDIS=false
if [ -z "${REDIS_URL:-}" ]; then
  RUN_LOCAL_REDIS=true
  mkdir -p "$DATA_DIR/redis"
  export REDIS_URL="redis://127.0.0.1:6379/0"
fi
# Celery accepts a redis:// broker URL, so RabbitMQ is not needed.
export AMQP_URL="${AMQP_URL:-${REDIS_URL%/*}/1}"

# --- Object storage (Tigris via `fly storage create`, or any S3) -----------------
export AWS_S3_ENDPOINT_URL="${AWS_S3_ENDPOINT_URL:-${AWS_ENDPOINT_URL_S3:-}}"
export AWS_S3_BUCKET_NAME="${AWS_S3_BUCKET_NAME:-${BUCKET_NAME:-uploads}}"
export AWS_REGION="${AWS_REGION:-auto}"
export USE_MINIO=0
if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
  echo "WARNING: no object storage configured (AWS_ACCESS_KEY_ID unset); file uploads will fail." >&2
fi

# --- Plane URLs -----------------------------------------------------------------
export WEB_URL="$PUBLIC_URL"
export APP_BASE_URL="$PUBLIC_URL" APP_BASE_PATH=""
export ADMIN_BASE_URL="$PUBLIC_URL" ADMIN_BASE_PATH="/god-mode"
export SPACE_BASE_URL="$PUBLIC_URL" SPACE_BASE_PATH="/spaces"
export LIVE_BASE_URL="$PUBLIC_URL" LIVE_BASE_PATH="/live"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-$PUBLIC_URL}"
export API_BASE_URL="http://127.0.0.1:8000"
export DEBUG="${DEBUG:-0}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
export FILE_SIZE_LIMIT="${FILE_SIZE_LIMIT:-5242880}"
export MINIO_ENDPOINT_SSL=1

exec supervisord -c /app/supervisord.conf
