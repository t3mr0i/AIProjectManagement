# Verification report

Status: 2026-09-25 · commit after `0713eba` · environment: cloud dev container. The container had PostgreSQL 16, Redis and Chromium, and no Docker daemon. It used the Celery broker `memory://` (see `BASELINE.md §2`). Every result below was **actually executed**. Anything not executed is listed under "Not verified" and is not claimed.

## Executed checks

| Area | Command | Result |
|---|---|---|
| Native Plane + extension backend | `pytest plane/tests -o addopts="--nomigrations --create-db"` (apps/api) | **882 passed, 15 failed**. All 15 failures are baseline tests (`baseline-failures.txt`). **0 new native failures**. |
| Extension backend only | `pytest plane/tests/package_flow` | **311 passed** (32 test files) |
| Runner (external CLI) | `python -m pytest tests` (apps/runner) | **80 passed** |
| Runner ↔ real backend E2E | `test_runner_e2e.py` (Django `live_server`, real git repo) | passed: happy path and `NATIVE_SOURCE_CHANGED` refusal |
| Live collaboration revocation | `pnpm --filter=live test` | **46 passed** |
| Web helpers | `pnpm test` (packages/utils) | **24 passed** |
| Browser E2E (real API + web dev server, Chromium) | `tools/project-hub/e2e/run.sh` | passed. The flow activates a package, fills the brief, creates a revision, checks readiness, then opens project Activity and Work packages, workspace Roadmap and Settings, and the diagram editor (semantic change, then a layout-only change). It also registers an upload next to a quarantined one. 13 screenshots are in `screenshots/`. |
| Type checks | `pnpm turbo run check:types --filter=web --filter=live --filter=@plane/types --filter=@plane/utils --filter=@plane/editor` | 16/16 tasks successful |
| Web build | `pnpm turbo run build --filter=web` | successful (web agent run) |
| Lint / format | `ruff check plane/package_flow plane/tests/package_flow`; `oxlint` / `oxfmt --check` on all changed TS/JSON/MD | clean |
| i18n | `pnpm --filter @plane/i18n check:sync` | all 21 locales in sync (4,632 keys) |
| Migration drift | `manage.py makemigrations --check package_flow` | no changes |
| Additive migration + restore (PF04, FR-B04, FR-B12) | `tools/project-hub/migration_check.sh` on a scratch Postgres DB | passed. It seeded a legacy native dataset, then ran the extension migration and backfill twice (the second run changed nothing; no issue was auto-converted; the extension stayed disabled). Native IDs were preserved and native issue create still worked. A `pg_dump` restore preserved all 83 rows. Reversing the migration kept native data. |
| Upstream lock (FR-B01) | `tools/project-hub/verify_upstream_lock.py` | OK: HEAD is based on `d616636…`; `licensePathApproved=false` |
| Traceability | `tools/project-hub/traceability.py` | every one of the 73 FRs and 46 acceptance scenarios has ≥1 automated test |
| NFR-01 latency probe (10 % of Testprofil A: 5 projects, 1,000 packages, 10k messages, 100k events) | `manage.py package_flow_latency_probe` (in-process, no network) | p95 server-side: package list 163 ms, package status 34 ms, project overview 477 ms, activity 265 ms, roadmap 291 ms, search 74 ms |

## Not verified (open, not claimed)

- **Full Testprofil A** (50 projects, 10,000 packages, 1M events, 100 concurrent users): only 10 % was measured, single user, in-process. NFR-01 to NFR-03 are not proven at full scale.
- **Live providers.** No real GitLab, GitHub, Jira, Linear or Azure DevOps instance was contacted. The adapters are tested with recorded fixture payloads through a fake transport. These still need confirmation against real instances: Jira webhook signing, Azure release deployments, squash-merge payloads, and edition detection.
- **Real coding agent.** The runner was exercised with the deterministic test agent and the external-command adapter (shell stub). No LLM coding agent was run on a customer repository.
- **Sandboxing.** Network and filesystem isolation of the runner depend on the OS or container (INV-10). They are not enforced by `ph-runner` itself.
- **Human checks.** No usability tests with people (PRD §17/§18). There was no manual WCAG 2.2 AA keyboard or screen-reader audit; the UI was built to the rules, but NFR-06 is not audited.
- **Docker test stack.** The official `docker-compose-test.yml` stack was not run (no Docker daemon). The 15 baseline failures should be re-checked there.
- **Operations.** No HA, backup schedule or RPO/RTO drills (NFR-07). No provider rate-limit or outage drill beyond automated tests.
- **Enterprise identity.** SAML, OIDC and SCIM are not part of the Community source and remain `needs_verification` (O03/O07).
- **Security review and license.** No independent security review has been done. L01 (distribution path) is open: no external distribution or public hosting is authorized.

## How to reproduce

```bash
# backend (apps/api) with DATABASE_URL, REDIS_URL, AMQP_URL=memory://, SECRET_KEY, WEB_URL set
tools/project-hub/regression.sh            # lock + extension + runner + native suite vs baseline
DATABASE_URL=.../scratch tools/project-hub/migration_check.sh
python manage.py package_flow_seed_load_profile --scale 0.1
python manage.py package_flow_latency_probe --slug <seeded slug>
tools/project-hub/e2e/run.sh               # browser flow, needs Chromium
```
