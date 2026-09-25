# I00 — Plane source baseline and unmodified-baseline report

Status date: 2026-09-24. Requirement refs: FR-B01, FR-B03, FR-B12, FR-B13, PF01.

## 1. Source state

| Item                                | Value                                                                                                                                           |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Upstream repository                 | `makeplane/plane` (public Community source, AGPL-3.0-only)                                                                                      |
| Analysis commit (PRD 0.2)           | `d616636119d20a531a815c78d364bdb47d552a2d` (`preview`, 2026-09-24T09:45:14Z)                                                                    |
| Fork start commit (this repository) | `d616636119d20a531a815c78d364bdb47d552a2d` — **identical** to the analysis commit, so no baseline deviation had to be evaluated (PF01).         |
| Root `package.json` version         | `1.4.2` (not treated as a release tag)                                                                                                          |
| Toolchain from manifest             | Node `>=22.22.0` (observed `v22.22.2`), `pnpm@11.10.0` (lockfile install `--frozen-lockfile` succeeded), Python 3.11, Django 5.2.15, DRF 3.17.2 |
| Edition                             | Community source only. No Commercial/Cloud/Airgapped code is present or assumed (O07, FR-B13).                                                  |

`docs/project-hub/prd/foundation/upstream-lock.json` records the analysis state; `docs/project-hub/upstream-lock.json` records the fork start commit used for implementation. Any later upstream bump must follow `UPSTREAM_BUMP.md`; `preview` is never fetched silently.

## 2. Baseline run (unmodified Plane, before extension code)

Environment: cloud dev container, no Docker daemon. Services started locally instead of `docker-compose-test.yml`: PostgreSQL 16, Redis 7 (Valkey-compatible), Celery broker `memory://` (instead of RabbitMQ), no MinIO. Env: `DATABASE_URL`, `REDIS_URL`, `AMQP_URL=memory://`, `WEB_URL`/`APP_BASE_URL=http://localhost:3000`, `SECRET_KEY`.

Command: `pytest plane/tests -o addopts="--nomigrations --reuse-db"` (from `apps/api`).

Result on the unmodified fork start commit: **571 passed, 15 failed**.

The 15 failures are **baseline failures of this environment**, not caused by the extension (the extension did not exist yet when they were recorded) and are therefore not counted as our own successful or failed tests:

- `plane/tests/contract/app/test_authentication.py` — 12 magic-link sign-in/sign-up tests (`TestMagicLinkGenerate`, `TestMagicSignIn`, `TestMagicSignUp`, `TestMagicSign*VerifyAttempts`, `TestBotUserLoginBlocked::test_bot_magic_sign_in_blocked`): magic-code generation returns HTTP 400 in this environment (instance/SMTP configuration of the local, non-Docker setup).
- `plane/tests/contract/api/test_projects_lite.py` — 3 tests fail **only in the full-suite run** (test-order dependent: which 3 of its 5 tests fail varies between runs); all 5 pass when the module runs alone (verified 3× before and after the extension). All 5 are listed in `baseline-failures.txt` as order-dependent baseline tests.

They must be re-checked inside the official `docker-compose-test.yml` stack before a pilot (see `RUNNING_TESTS.md`).

Web: `pnpm install --frozen-lockfile` succeeded. Type checks and builds of the web app are recorded in `VERIFICATION.md` together with the extension results.

## 3. Native flows — static and test evidence

| Native flow                                      | Evidence at baseline                                                                                | Extension impact                                               |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Login / session                                  | Plane auth tests (except the magic-link env failures above)                                         | Reused; no second auth (FR-B03)                                |
| Workspaces / projects / members                  | Contract tests `test_workspace_app`, `test_project_app`, `test_project_member_is_active_authz` pass | Reused as the only identity/membership source                  |
| Issues incl. drafts, sub-issues, archive         | Contract tests pass; `IssueManager` excludes drafts, triage, archived                               | Packages are `Issue` + 0..1 `PackageProfile`                   |
| Cycles / modules                                 | `test_cycles`, `test_cycle_issue_app`, `test_workspace_cycles_modules_project_scope_app` pass       | Reused for Scrum/planning context (FR-M05)                     |
| Pages / versions / assets                        | `test_page_version_project_scope_app`, `test_workspace_file_asset_project_scope_app` pass           | Reused; uploads get an additional `UploadRecord` (scan/format) |
| Live collaboration (`apps/live`, Hocuspocus/Yjs) | Not executed in this container (needs Node service + Redis; see `VERIFICATION.md`)                  | Not modified                                                   |

## 4. Suitability gaps discovered (input for later increments)

1. `Issue` has a single `external_id`/`external_source` — insufficient for multiple integrations → `ExternalLink` (PRD §7.1).
2. Native bulk paths (`BulkIssueOperationsEndpoint` date updates, bulk archive, automation task auto-archive/auto-close, bulk delete via soft-delete queryset) use `bulk_update`/queryset updates and therefore **bypass Django signals**. The extension therefore never relies on signals for safety: every run/merge gate re-reads native state synchronously (see `MUTATION_PATHS.md`).
3. No native chat/DM, runner, approval, evidence or portfolio dependency semantics in the Community source (as expected by PLANE_FOUNDATION §2).
4. Native `Team` exists without project/member assignment → thin `TeamScope` extension.

## 5. Minimal integration points chosen

- New Django app `plane.package_flow` (models in `pf_*` tables, one additive migration), registered in `INSTALLED_APPS` and mounted at `api/` next to `plane.app.urls`.
- Django signal receivers on native `Issue`, `Project`, `ProjectMember` saves (best-effort projection only).
- Web: new routes/components under `apps/web/core/components/project-hub` plus small hook points in native navigation and work-item detail.
- External runner as a separate package `apps/runner` (never executed inside web/API/live).

No new project scaffold, auth system, ORM or design system was introduced.
