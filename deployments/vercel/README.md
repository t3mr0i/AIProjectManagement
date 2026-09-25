# Deploying the frontend to Vercel

One Vercel project serves both static frontends from the same domain:

| Path            | App                    | Source          |
| --------------- | ---------------------- | --------------- |
| `/`             | Web app (SPA)          | `apps/web`      |
| `/god-mode/`    | Instance admin (SPA)   | `apps/admin`    |
| `/api`, `/auth` | Proxied to the backend | `middleware.ts` |

The Plane backend (Django API, Celery workers, Postgres, Redis, RabbitMQ,
object storage, and the `live` realtime server) cannot run on Vercel and must
be hosted elsewhere (e.g. with `docker-compose.yml` on any Docker host).

## Files

- `vercel.json` (repo root): install/build commands, output directory, SPA
  fallbacks and cache headers.
- `middleware.ts` (repo root): proxies `/api/*` and `/auth/*` to
  `PLANE_API_URL`. Keeping the API same-origin means the backend's session
  and CSRF cookies work without cross-site cookie settings.
- `deployments/vercel/build.sh`: builds `web` and `admin` with Turbo and merges
  both bundles into `.vercel-dist/`.

## Vercel project settings

- Root directory: repository root
- Node.js version: 22.x
- Environment variables:

| Variable                       | Required    | Notes                                                                                                          |
| ------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------- |
| `ENABLE_EXPERIMENTAL_COREPACK` | recommended | `1`, so Vercel uses the pnpm version pinned in `package.json`                                                  |
| `PLANE_API_URL`                | yes         | Public URL of the Plane API, e.g. `https://api.example.com`. Until it is set, `/api` and `/auth` answer `503`. |
| `VITE_LIVE_BASE_URL`           | no          | Public URL of the `live` server. Vercel cannot proxy WebSockets, so it must be reachable directly.             |
| `VITE_SPACE_BASE_URL`          | no          | URL of a separately hosted `space` app (public pages).                                                         |

`VITE_*` variables are baked in at build time — redeploy after changing them.
`PLANE_API_URL` is read at request time; redeploy once after changing it so the
middleware picks up the new value.

## Backend configuration

On the backend (`apps/api/.env`), allow the Vercel domain:

```env
WEB_URL=https://<your-app>.vercel.app
ADMIN_BASE_URL=https://<your-app>.vercel.app
APP_BASE_URL=https://<your-app>.vercel.app
CORS_ALLOWED_ORIGINS=https://<your-app>.vercel.app
```

## Local check

```bash
pnpm install
bash deployments/vercel/build.sh
npx serve .vercel-dist   # static preview, without the /api proxy
```
