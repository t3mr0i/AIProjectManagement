# Project Hub on Plane: implementation guide

Project Hub is an AI-native project management extension built **inside this Plane fork**, following PRD 0.2 (`prd/`). A work package is a native Plane `Issue` with an optional profile. There is no second ticket, project or user store.

## Start here

| Document                                     | What it covers                                                                |
| -------------------------------------------- | ----------------------------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)           | Components, data flow, invariants and where each lives in code                |
| [API.md](API.md)                             | REST contract v1.1.0 of the extension (`/package-flow/`)                      |
| [DECISIONS.md](DECISIONS.md)                 | Open PRD decisions (O01–O07, L01) and the defaults used in code               |
| [BASELINE.md](BASELINE.md)                   | I00: fork start commit, unmodified baseline test results, integration points  |
| [MUTATION_PATHS.md](MUTATION_PATHS.md)       | Every native write path and how the extension protects gates                  |
| [RUNNER.md](RUNNER.md)                       | External runner `ph-runner`: install, commands, IDE setup, enforcement limits |
| [LIVE.md](LIVE.md)                           | Realtime access re-check and revocation in `apps/live`                        |
| [AI_EVALUATION.md](AI_EVALUATION.md)         | The PRD §14.5 AI evaluation set                                               |
| [UPSTREAM_BUMP.md](UPSTREAM_BUMP.md)         | How to take a new upstream Plane commit safely                                |
| [TRACEABILITY.md](TRACEABILITY.md)           | Every FR and acceptance scenario mapped to code and tests (generated)         |
| [VERIFICATION.md](VERIFICATION.md)           | What was actually executed, the results, and what is still unverified         |
| [LICENSE_INVENTORY.md](LICENSE_INVENTORY.md) | Dependency license inventory (L01 remains open)                               |

## Enable it locally

```bash
# backend (from apps/api, with the usual Plane env)
python manage.py migrate                                  # adds pf_* tables, nothing native changes
python manage.py package_flow_backfill                    # idempotent; creates disabled activation rows
python manage.py package_flow_backfill --activate-workspace <slug>
```

Then grant capabilities in **Workspace settings → Project Hub**. Native roles never imply run, merge or approval rights. Open any work item and choose **Activate as work package**. The new navigation entries (Overview, Messages, Roadmap, Search; per project Activity, Work packages, Roadmap, Knowledge) appear only for enabled scopes.

## Code map

- `apps/api/plane/package_flow/`: Django extension app with models, services, views, adapters, AI, OpenSpec, skills, management commands and the migration.
- `apps/api/plane/tests/package_flow/`: backend tests named after PRD IDs (`test_ac05_…`, `test_pf06_…`, `test_fr_g06_…`).
- `apps/runner/`: stdlib-only external runner/CLI with its own tests and IDE task files.
- `apps/web/core/{components,services,store}/project-hub/`: web UI. Types are in `packages/types/src/project-hub`, pure helpers and tests in `packages/utils/src/project-hub`, and strings in the `project_hub` i18n namespace.
- `apps/live/src/lib/access-recheck.ts`: realtime revocation.
- `tools/project-hub/`: regression gate, upstream-lock verification, migration/restore check, traceability, license inventory, skill approval.
