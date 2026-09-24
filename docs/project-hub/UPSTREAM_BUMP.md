# Upstream bump runbook (FR-B12, PF12, MIGRATION_AND_UPSTREAM §7)

The fork keeps `makeplane/plane` as a separate remote. A bump is a deliberate change reviewed like any other; `preview` is never pulled implicitly and never deployed directly.

## 0. Preconditions

- Current fork is green: `tools/project-hub/regression.sh` passes (or baseline failures are listed separately).
- A database + object-store backup of the target environment exists and a restore was rehearsed (see §4).
- Active package runs are drained or explicitly paused (`POST .../runs/{id}/cancel` or project deactivation).

## 1. Compare

```bash
git remote add upstream https://github.com/makeplane/plane.git   # once
git fetch upstream <tag-or-commit>
OLD=$(jq -r .implementationCommit docs/project-hub/upstream-lock.json)
NEW=<candidate commit>
git diff --stat $OLD $NEW -- apps/api/plane/db/models apps/api/plane/app/views/issue apps/api/plane/api/views/issue.py \
  apps/api/plane/db/models/issue.py apps/api/plane/db/models/state.py packages/editor apps/live apps/web/app/routes
```

Review in particular: `Issue`/`State`/`Project`/`ProjectMember` fields and managers, draft semantics, bulk/automation write paths (update `MUTATION_PATHS.md`), editor/live protocol, web route config and the navigation/detail hook points listed in `BASELINE.md §5`.

## 2. Merge

Create branch `upstream-bump/<new-short>`; `git merge $NEW` (no rebase of already shared history). Resolve conflicts in hook points only; extension code lives in `plane/package_flow`, `apps/runner`, `apps/web/core/components/project-hub`. Update `docs/project-hub/upstream-lock.json` (`implementationCommit`, versions) in the same change.

## 3. Migrate

```bash
python manage.py migrate --plan          # review native + package_flow migrations
python manage.py migrate
python manage.py package_flow_backfill   # idempotent; run twice, second run must report 0 changes
```

## 4. Restore rehearsal

1. `pg_dump` + object-store snapshot of the pre-bump state.
2. Restore into an isolated environment, run the new code + migrations.
3. Verify with `tools/project-hub/verify_restore.py` (counts and IDs of issues, package profiles, revisions, approvals, deliveries and decisions are unchanged; every approval still references the same revision hash).

Rollback is **restore**, not `migrate backwards`, whenever a migration is irreversible.

## 5. Regression (must all run; results recorded, baseline failures separated)

- `tools/project-hub/regression.sh` (native Plane test suite + package-flow suite + runner suite + upstream-lock check).
- Manual/E2E checklist: login & project switch; native issue create/edit; pages + upload; cycles/modules/views; package activation → revision → approval; native description change after approval blocks run (PF06); runner revocation; duplicate webhook delivery; DM/public-surface isolation; migration + restore scenario.

## 6. Deliverable

Old and new commit, affected contracts, migration status, the exact test commands run with pass/fail counts, remaining limitations and an explicit rollout approval by a human. L01 still governs any external distribution.
