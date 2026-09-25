# syntax=docker/dockerfile:1.7
# Single-container Plane image for Fly.io, built from this repository's source.
#
# Runs web, admin, space, api, worker, beat, live, Caddy, and (unless external
# URLs are provided) Postgres and Redis. Build context is the repo root:
#   fly deploy   (uses fly.toml at the repo root)

ARG NODE_IMAGE=node:22-alpine
ARG PYTHON_IMAGE=python:3.12.12-alpine
ARG CADDY_IMAGE=caddy:2.11.4-alpine

# ---------------------------------------------------------------------------
# Frontends + live server (Node)
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS node-base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PNPM_HOME/bin:$PATH"
ENV TURBO_TELEMETRY_DISABLED=1
ENV CI=1
RUN apk add --no-cache libc6-compat && corepack enable pnpm
WORKDIR /app

FROM node-base AS pruner
ARG TURBO_VERSION=2.9.18
RUN pnpm add -g turbo@${TURBO_VERSION}
COPY . .
RUN turbo prune web admin space live --docker

FROM node-base AS node-builder
# Everything is served from one origin, so the apps use relative URLs.
ENV VITE_API_BASE_URL="" \
    VITE_API_BASE_PATH="/api" \
    VITE_WEB_BASE_URL="" \
    VITE_WEB_BASE_PATH="" \
    VITE_ADMIN_BASE_URL="" \
    VITE_ADMIN_BASE_PATH="/god-mode" \
    VITE_SPACE_BASE_URL="" \
    VITE_SPACE_BASE_PATH="/spaces" \
    VITE_LIVE_BASE_URL="" \
    VITE_LIVE_BASE_PATH="/live" \
    VITE_WEBSITE_URL="https://plane.so" \
    VITE_SUPPORT_EMAIL="support@plane.so"
COPY .gitignore .gitignore
COPY --from=pruner /app/out/json/ .
COPY --from=pruner /app/out/pnpm-lock.yaml ./pnpm-lock.yaml
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store pnpm fetch --store-dir=/pnpm/store
COPY --from=pruner /app/out/full/ .
COPY turbo.json turbo.json
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --offline --frozen-lockfile --store-dir=/pnpm/store
RUN pnpm turbo run build --filter=web --filter=admin --filter=space --filter=live

# ---------------------------------------------------------------------------
# API (Python)
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /code
RUN apk add --no-cache libpq libxslt xmlsec libffi-dev
COPY apps/api/requirements.txt ./
COPY apps/api/requirements ./requirements
RUN apk add --no-cache --virtual .build-deps bash g++ gcc cargo git make postgresql-dev libc-dev linux-headers \
    && pip install -r requirements.txt --compile --no-cache-dir \
    && apk del .build-deps
COPY apps/api/manage.py manage.py
COPY apps/api/plane plane/
COPY apps/api/templates templates/
COPY apps/api/package.json package.json
COPY apps/api/bin ./bin/
RUN mkdir -p /code/plane/logs && chmod +x ./bin/*

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM ${CADDY_IMAGE} AS caddy
FROM ${NODE_IMAGE} AS node

FROM ${PYTHON_IMAGE} AS runner
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV INSTANCE_CHANGELOG_URL=https://sites.plane.so/pages/691ef037bcfe416a902e48cb55f59891/
ARG APK_SECURITY_PATCH=2026-09-07
RUN echo "apk-security-patch ${APK_SECURITY_PATCH}" && apk update && apk upgrade --no-cache --available \
    && apk add --no-cache libpq libxslt xmlsec libffi bash curl libstdc++ libgcc \
       postgresql17 postgresql17-contrib su-exec tzdata \
    && (apk add --no-cache redis \
        || (apk add --no-cache valkey && ln -s /usr/bin/valkey-server /usr/bin/redis-server)) \
    && pip install --no-cache-dir supervisor

# Node runtime for space (SSR) and live
COPY --from=node /usr/local/bin/node /usr/local/bin/node

COPY --from=caddy /usr/bin/caddy /usr/bin/caddy

COPY --from=backend /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=backend /usr/local/bin/ /usr/local/bin/
COPY --from=backend /code /app/backend

# Static frontends
COPY --from=node-builder /app/apps/web/build/client /app/web
COPY --from=node-builder /app/apps/admin/build/client /app/admin

# Node workspace for space + live (pnpm symlinks into /app/node/node_modules/.pnpm)
COPY --from=node-builder /app/node_modules /app/node/node_modules
COPY --from=node-builder /app/packages /app/node/packages
COPY --from=node-builder /app/apps/space/build /app/node/apps/space/build
COPY --from=node-builder /app/apps/space/node_modules /app/node/apps/space/node_modules
COPY --from=node-builder /app/apps/space/package.json /app/node/apps/space/package.json
COPY --from=node-builder /app/apps/live/dist /app/node/apps/live/dist
COPY --from=node-builder /app/apps/live/node_modules /app/node/apps/live/node_modules
COPY --from=node-builder /app/apps/live/package.json /app/node/apps/live/package.json

COPY deployments/fly/Caddyfile /app/Caddyfile
COPY deployments/fly/supervisord.conf /app/supervisord.conf
COPY deployments/fly/start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /data

EXPOSE 8080
CMD ["/app/start.sh"]
