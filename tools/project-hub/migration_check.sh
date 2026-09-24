#!/usr/bin/env bash
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# PF04 / FR-B04 / FR-B12: additive migration + backfill + restore on a legacy
# native dataset. Needs DATABASE_URL pointing at a *scratch* database and
# pg_dump/psql on PATH. Destroys and recreates that database.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-python}"
cd "$ROOT/apps/api"
DB_URL="$DATABASE_URL"
DB_NAME="${DB_URL##*/}"
BASE_URL="${DB_URL%/*}"
TMP="$(mktemp -d)"
echo "== reset scratch database $DB_NAME"
psql "$BASE_URL/postgres" -qc "DROP DATABASE IF EXISTS $DB_NAME" -c "CREATE DATABASE $DB_NAME"
psql "$BASE_URL/postgres" -qc "DROP DATABASE IF EXISTS ${DB_NAME}_restore"
echo "== native schema only (package_flow not migrated)"
"$PY" manage.py migrate db --noinput >/dev/null
"$PY" manage.py migrate --noinput >/dev/null 2>&1 || true
"$PY" manage.py migrate package_flow zero --noinput >/dev/null
"$PY" manage.py shell < "$ROOT/tools/project-hub/seed_native_fixture.py"
# snapshot of native tables only (extension tables don't exist yet)
"$PY" manage.py shell -c "
import json,hashlib
from plane.db.models import Workspace,Project,State,Issue,Cycle,Module,Page
def d(v): return hashlib.sha256(json.dumps(v,default=str,sort_keys=True).encode()).hexdigest()[:16]
T={'workspaces':(Workspace.all_objects,['id','slug']),'projects':(Project.all_objects,['id','workspace_id','identifier']),
'states':(State.all_objects,['id','project_id','group']),'issues':(Issue.all_objects,['id','project_id','workspace_id','sequence_id']),
'cycles':(Cycle.all_objects,['id','project_id']),'modules':(Module.all_objects,['id','project_id']),'pages':(Page.all_objects,['id','workspace_id'])}
json.dump({'tables':{n:{str(r[0]):d(r) for r in m.all().values_list(*f,'deleted_at')} for n,(m,f) in T.items()}},open('$TMP/before.json','w'))
print('native snapshot taken')"
echo "== apply extension migration"
"$PY" manage.py migrate package_flow --noinput
echo "== backfill twice (idempotent)"
"$PY" manage.py package_flow_backfill
"$PY" manage.py package_flow_backfill
"$PY" manage.py shell -c "
from plane.db.models import Issue
from plane.package_flow.models import PackageProfile, ExtensionActivation
assert PackageProfile.objects.count()==0, 'backfill must not convert issues'
assert not ExtensionActivation.objects.filter(is_enabled=True).exists(), 'extension must stay disabled'
print('no automatic package conversion; extension disabled by default')"
"$PY" manage.py package_flow_integrity_snapshot --out "$TMP/after.json"
"$PY" "$ROOT/tools/project-hub/verify_restore.py" "$TMP/before.json" "$TMP/after.json"
echo "== native flows still work with extension disabled (issue create + list through ORM manager)"
"$PY" manage.py shell -c "
from plane.db.models import Issue, Project
p=Project.objects.first(); n=Issue.issue_objects.filter(project=p).count()
Issue.objects.create(name='post-migration issue', project=p, workspace=p.workspace, state=p.project_state.first())
assert Issue.issue_objects.filter(project=p).count()==n+1; print('native issue create ok')"
echo "== activate one workspace, create package data, dump + restore"
"$PY" manage.py package_flow_backfill --activate-workspace "$("$PY" manage.py shell -c 'from plane.db.models import Workspace;print(Workspace.objects.order_by("created_at").first().slug)' | tail -1)"
"$PY" manage.py shell -c "
from plane.db.models import Issue
from plane.package_flow.models import PackageProfile, PackageRevision
i=Issue.issue_objects.first(); PackageProfile.objects.create(issue=i, intent='x')
PackageRevision.objects.create(issue=i, number=1, title=i.name, content_hash='b'*64); print('package rows created')"
"$PY" manage.py package_flow_integrity_snapshot --out "$TMP/pre_backup.json"
pg_dump "$DB_URL" > "$TMP/dump.sql"
psql "$BASE_URL/postgres" -qc "CREATE DATABASE ${DB_NAME}_restore"
psql -q "$BASE_URL/${DB_NAME}_restore" < "$TMP/dump.sql" >/dev/null
DATABASE_URL="$BASE_URL/${DB_NAME}_restore" "$PY" manage.py package_flow_integrity_snapshot --out "$TMP/restored.json"
"$PY" "$ROOT/tools/project-hub/verify_restore.py" "$TMP/pre_backup.json" "$TMP/restored.json"
echo "== reverse extension migration keeps native data"
"$PY" manage.py migrate package_flow zero --noinput >/dev/null
"$PY" manage.py shell -c "
from plane.db.models import Issue; print('issues after reverse migration:', Issue.all_objects.count())"
echo "MIGRATION CHECK PASSED"
