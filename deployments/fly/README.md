# Deploying to Fly.io

The whole app runs as **one Fly app with one machine**, built from this
repository's source (so fork-specific features are included):

| Inside the container  | Port | Notes                                                                    |
| --------------------- | ---- | ------------------------------------------------------------------------ |
| Caddy (public)        | 8080 | Routes `/api`, `/auth`, `/live`, `/spaces`, `/god-mode`, `/`             |
| API (Django/gunicorn) | 8000 | Migrations run on start                                                  |
| Celery worker + beat  | –    | Uses Redis as broker (no RabbitMQ needed)                                |
| Live server           | 3100 | Realtime collaboration (WebSockets)                                      |
| Space (SSR)           | 3002 | Public project pages                                                     |
| Postgres + Redis      | –    | Local on the `/data` volume, unless `DATABASE_URL` / `REDIS_URL` are set |

Files: `fly.toml` (repo root), `deployments/fly/{Dockerfile,start.sh,supervisord.conf,Caddyfile}`.

## First deploy

```bash
fly apps create ai-project-management            # name must match fly.toml
fly volumes create plane_data --region fra --size 10 -a ai-project-management
fly storage create -a ai-project-management      # Tigris bucket; sets AWS_* + BUCKET_NAME secrets
fly deploy
```

The app is then available at `https://ai-project-management.fly.dev`.
Open `/god-mode/` first to create the instance admin.

## Configuration

| Variable / secret                      | Default                                       | Notes                                                                                     |
| -------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `PUBLIC_URL`                           | `https://$FLY_APP_NAME.fly.dev`               | Set when using a custom domain                                                            |
| `DATABASE_URL`                         | local Postgres on `/data`                     | e.g. a Fly Managed Postgres URL                                                           |
| `REDIS_URL`                            | local Redis                                   |                                                                                           |
| `AWS_*`, `BUCKET_NAME`                 | –                                             | Set by `fly storage create`; any S3 works via `AWS_S3_ENDPOINT_URL`, `AWS_S3_BUCKET_NAME` |
| `SECRET_KEY`, `LIVE_SERVER_SECRET_KEY` | generated once, stored in `/data/secrets.env` |                                                                                           |
| `GUNICORN_WORKERS`                     | `2`                                           |                                                                                           |

Set secrets with `fly secrets set KEY=value`.

## Backups

With the local Postgres, data lives on the `plane_data` volume. Fly takes daily
volume snapshots (`fly volumes snapshots list`). For stronger guarantees, point
`DATABASE_URL` at Fly Managed Postgres.

## Local test

```bash
docker build -f deployments/fly/Dockerfile -t plane-fly .
docker run --rm -p 8080:8080 -v plane-data:/data plane-fly
```
