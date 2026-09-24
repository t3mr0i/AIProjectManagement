# Project Hub package-flow API (contract v1.1.0)

Additive REST API of the `plane.package_flow` Django app. These are **new
extension endpoints**, not upstream Plane endpoints. Native Plane
project/issue/page APIs stay unchanged (PRD §13.4).

Conventions

- Auth: Plane session cookie (human) or `Authorization: Runner <token>` (agent).
  API keys and bot users are always _agent_ principals. Principal kind is
  derived from authentication, never from payload fields (INV-03).
- IDs are native Plane UUIDs: `workItemId == issue_id`, `projectId`, `workspaceId`.
- Writes accept `Idempotency-Key`. Replays return the stored response with header
  `Idempotent-Replay: true`; same key + different payload → `409 IDEMPOTENCY_MISMATCH`.
- Optimistic concurrency: body field `expected_version` (profile) / `expected_revision_id` → `409 VERSION_CONFLICT`.
- Errors: `{"error": str, "code": str, "detail"?: {}}` with 401/403/404/409/422/429.
  `202` means accepted, not finished.
- Disabled extension → `403 EXTENSION_DISABLED` for writes; reads of history stay available.
- JSON keys are snake_case in the REST API; the JSON-schema transport contracts
  (camelCase, `schemaVersion: "1.1.0"`) are available at the `.../contract` endpoints.

Prefixes

- `P = /api/workspaces/{slug}/projects/{project_id}/package-flow`
- `W = /api/workspaces/{slug}/package-flow`
- `R = /api/package-flow` (runner + webhook ingress)

## 1. Activation, capabilities, audit (I01)

| Method   | Path                             | Notes                                                                   |
| -------- | -------------------------------- | ----------------------------------------------------------------------- |
| GET      | `W/activation/`                  | `{workspace_enabled, projects: [{project_id, is_enabled}]}`             |
| PUT      | `W/activation/`                  | body `{is_enabled, reason}`; requires `workspace.admin`; audited        |
| PUT      | `P/activation/`                  | body `{is_enabled, reason}`; requires `workspace.admin`                 |
| GET      | `W/capabilities/me/?project_id=` | `{capabilities: [str], principal_kind, extension_enabled}`              |
| GET/POST | `W/capability-grants/`           | list / create `{member_id, capability, project_id?}`; `workspace.admin` |
| DELETE   | `W/capability-grants/{id}/`      | revoke                                                                  |
| GET      | `W/audit/?project_id=&action=`   | `workspace.admin` only                                                  |

## 2. Packages, revisions, approvals (I02)

| Method   | Path                                                      | Notes                                                                                                                                                                                                                                                                                                                                     |
| -------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | ------ | ---- | ---- | ---- | -------------------------------------------------------------------------------------- |
| GET      | `P/packages/?view=drafts                                  | ready                                                                                                                                                                                                                                                                                                                                     | build | review | ship | done | all` | package rows for issues with a profile, incl. authorized drafts. Row: see _PackageRow_ |
| POST     | `P/work-items/{issue_id}/profile`                         | activate profile (idempotent: second call returns existing, 200). body `{profile_kind?, package_type?}` → 201 _Profile_                                                                                                                                                                                                                   |
| GET      | `P/work-items/{issue_id}/profile`                         | _Profile_ or 404 `NO_PROFILE`                                                                                                                                                                                                                                                                                                             |
| PATCH    | `P/work-items/{issue_id}/profile`                         | edit working draft `{intent, outcome, non_goals, scope, criteria, risk, profile_kind, package_type, completion_criterion, expected_version}`                                                                                                                                                                                              |
| GET      | `P/work-items/{issue_id}/readiness`                       | `{ready: bool, missing: [{field, message}], policies: [{id, message}], profile_kind}`                                                                                                                                                                                                                                                     |
| GET/POST | `P/work-items/{issue_id}/revisions`                       | create immutable snapshot from current working draft + native title/description → 201 _Revision_                                                                                                                                                                                                                                          |
| GET      | `P/work-items/{issue_id}/revisions/{revision_id}`         | _Revision_ (+ `contract` = package-revision 1.1.0 JSON)                                                                                                                                                                                                                                                                                   |
| GET      | `P/work-items/{issue_id}/revisions/compare?from=&to=`     | field-level diff                                                                                                                                                                                                                                                                                                                          |
| GET/POST | `P/work-items/{issue_id}/execution-approvals`             | human + `package.approve_execution`; body `{revision_id, repository_scope:[{binding_id, base_commit, target_branch, allowed_paths}], allowed_actions, runner_profile_id?, limits:{max_seconds,max_spend_minor,currency}, expires_in_hours?}` → 201 _Approval_. Errors: `HUMAN_PRINCIPAL_REQUIRED`, `REVISION_NOT_READY`, `REVISION_STALE` |
| POST     | `P/work-items/{issue_id}/execution-approvals/{id}/revoke` | body `{reason}`                                                                                                                                                                                                                                                                                                                           |
| GET/POST | `P/work-items/{issue_id}/change-records`                  | `{kind, title, description}`                                                                                                                                                                                                                                                                                                              |
| PATCH    | `P/work-items/{issue_id}/change-records/{id}`             | `{status}`                                                                                                                                                                                                                                                                                                                                |
| GET      | `P/work-items/{issue_id}/status`                          | _PackageStatus_ projection (phase, lifecycle, delivery, flags, native state group)                                                                                                                                                                                                                                                        |

_Profile_: `{id, work_item_id, project_id, workspace_id, profile_kind, package_type, completion_criterion, intent, outcome, non_goals, scope, criteria:[{id, text}], risk, working_revision_id, approved_revision_id, version, flags, native:{name, priority, state_group, state_name, is_draft, sequence_id, project_identifier}}`

_Revision_: `{id, work_item_id, number, title, intent, outcome, non_goals, scope, criteria, decisions, artifacts, source_versions, content_hash, created_by, created_at, is_approved, is_stale}`

_PackageStatus_: `{work_item_id, lifecycle: draft|ready|active|review|completed|cancelled|archived, phase: drafts|ready|build|review|ship|done, delivery: not_integrated|partially_integrated|integrated|deployed|released|rolled_back|unknown, flags:[blocked|scope_changed|sync_conflict|stale_evidence|integration_offline|native_done_without_delivery], native_state_group, repositories:[{binding_id, name, delivery, merge_request_state}], explanations:[str]}`

_PackageRow_: _PackageStatus_ + `{name, sequence_id, project_identifier, priority, assignee_ids, updated_at, open_questions}`

## 3. Runner, claims, runs (I06/I07)

| Method   | Path                             | Notes                                                                                                                                              |
| -------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------- | -------- | ------ | --------------------------------- |
| GET/POST | `W/runners/`                     | register runner `{name, kind}` → 201 `{id, token}` (token shown once)                                                                              |
| DELETE   | `W/runners/{id}/`                | deactivate (revokes further actions)                                                                                                               |
| POST     | `P/work-items/{issue_id}/claims` | `{repository_binding_id?, exclusive=true, lease_seconds=300}` → 201 `{id, fencing_token, lease_expires_at}`; 409 `CLAIM_HELD` with `detail.holder` |
| POST     | `R/claims/{claim_id}/heartbeat`  | `{fencing_token}` → extends lease; 409 `STALE_FENCING_TOKEN` / `LEASE_EXPIRED`                                                                     |
| POST     | `R/claims/{claim_id}/release`    | `{fencing_token}`                                                                                                                                  |
| POST     | `P/work-items/{issue_id}/runs`   | `{approval_id, claim_id, mode: human                                                                                                               | agent, agent_adapter?}`→ 201`{run, run_token}`; errors `REVISION_NOT_APPROVED`, `APPROVAL_REVOKED`, `APPROVAL_EXPIRED`, `NATIVE_SOURCE_CHANGED`, `CLAIM_INVALID`, `PROJECT_ARCHIVED` |
| GET      | `P/work-items/{issue_id}/runs`   | list                                                                                                                                               |
| GET      | `R/runs/{run_id}/manifest`       | immutable manifest (run token auth header `X-Run-Token`)                                                                                           |
| POST     | `R/runs/{run_id}/events`         | `{type: started                                                                                                                                    | progress                                                                                                                                                                             | waiting | finished | failed | question, fencing_token, detail}` |
| POST     | `R/runs/{run_id}/actions`        | controlled action gate `{action, fencing_token, detail:{paths?, spend_minor?}}` → 200 `{accepted:true}` / 409                                      |
| POST     | `R/runs/{run_id}/evidence`       | runner evidence (trust = runner_reported / local_self_report)                                                                                      |
| POST     | `P/runs/{run_id}/cancel`         | `run.cancel`; blocks further actions; 202                                                                                                          |

## 4. Integrations, delivery, review (I04/I10/I12)

| Method           | Path                                                               | Notes                                                                                                                            |
| ---------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| GET              | `W/providers/`                                                     | adapter capability declarations for gitlab/jira/linear/azure_devops/generic_git/github                                           |
| GET/POST         | `W/connections/`                                                   | `{provider, instance_url, instance_type, edition, display_name, webhook_secret?}` (`integration.manage`)                         |
| GET/PATCH/DELETE | `W/connections/{id}/`                                              | DELETE = disconnect (keeps links as `disconnected`)                                                                              |
| GET              | `W/connections/{id}/health`                                        | `{status, last_successful_sync_at, backlog_count, affected_capabilities, last_error}`                                            |
| POST             | `W/connections/{id}/reconcile`                                     | 202; replays unprocessed inbox, marks gaps                                                                                       |
| POST             | `R/webhooks/{connection_id}/`                                      | authenticated ingress; 202 after durable store; duplicates 200 `{duplicate:true}`                                                |
| GET/POST         | `P/repositories/`                                                  | bind repo `{connection_id, external_id, path_with_namespace, default_branch, role, branch_rules}`                                |
| POST             | `P/repositories/import-preview`                                    | J01 preview `{connection_id, external_id, commit}` → observed items flagged `observed`/`proposed`; no writes                     |
| GET/POST         | `P/work-items/{issue_id}/external-links`                           | `{connection_id, object_type, external_id, external_key, url, represents_package, field_ownership}`                              |
| GET              | `P/work-items/{issue_id}/merge-requests`                           |                                                                                                                                  |
| GET              | `P/work-items/{issue_id}/evidence`                                 |                                                                                                                                  |
| GET              | `P/work-items/{issue_id}/review`                                   | review view: intent (approved revision), change summary, criteria ↔ evidence mapping, open points, approvals (valid/invalidated) |
| POST             | `P/reviews/{issue_id}/approvals`                                   | `{kind: code                                                                                                                     | outcome, merge_request_id?, head_sha?, decision, comment}` human only |
| POST             | `P/merge-requests/{link_id}/merge`                                 | `{expected_head_sha}` → gate + provider merge; 409 `HEAD_MISMATCH`, `REVIEW_REQUIRED`, `CAPABILITY_MISSING`                      |
| GET              | `P/work-items/{issue_id}/delivery`                                 | per repo/environment chain + history (incl. rollbacks)                                                                           |
| GET              | `P/work-items/{issue_id}/sync-conflicts` / POST `.../{id}/resolve` |                                                                                                                                  |

## 5. Collaboration, AI, knowledge (I08/I09/I13)

| Method   | Path                                      | Notes                                                                                                      |
| -------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| GET/POST | `W/conversations/`                        | list mine / create `{kind: project                                                                         | package                                                                                     | direct, project_id?, issue_id?, participant_ids?, title?}` (package thread is get-or-create per issue) |
| GET      | `W/conversations/{id}/`                   | 404 for non-participants of DMs (also admins)                                                              |
| GET/POST | `W/conversations/{id}/messages/`          | `{body, parent_id?}`; `@AI` in body triggers AI answer proposal                                            |
| PATCH    | `W/conversations/{id}/messages/{mid}/`    | edit → new version kept                                                                                    |
| POST     | `W/conversations/{id}/read`               | explicit read marker                                                                                       |
| POST     | `W/ai/context-preview`                    | `{conversation_id?, selection:[{type, id, version?}], project_ids}` → sources allowed/blocked for audience |
| POST     | `P/decisions/preview`                     | `{conversation_id, message_ids, issue_id?, instruction}` → preview or clarification question               |
| POST     | `P/decisions`                             | confirm `{preview_id?                                                                                      | title,text,rationale, issue_id?, source_message_ids, idempotency_key}` (`decision.publish`) |
| GET      | `P/decisions/?issue_id=`                  | incl. `source_changed_since_decision`                                                                      |
| POST     | `P/work-items/{issue_id}/clarify`         | start/continue `{answer?}` → next question w/ recommendation or checkpoint                                 |
| GET/POST | `P/proposals/` / `P/proposals/{id}/accept | reject`                                                                                                    | AI proposals, never applied without human accept                                            |
| GET/POST | `P/diagrams/` · PUT `P/diagrams/{id}/`    | `{semantic, layout, expected_version}` → `{layout_only, semantic_diff, proposal_id?}`                      |
| POST     | `P/uploads/{asset_id}/register`           | scan + format support record                                                                               |
| GET      | `W/search/?q=&types=`                     | ACL-filtered results `{type, id, title, snippet, project_id, source, updated_at}`; no hidden counts        |
| GET      | `P/activity/?since=last_visit             | ISO&until=&group=package`                                                                                  | grouped by package & day; `P/activity/visit` POST sets marker                               |
| GET      | `P/overview`                              | active/ready/review/shipped packages, open decisions, next work (with reasons)                             |
| GET      | `W/notifications/`                        | targeted vs bundled                                                                                        |
| GET/PUT  | `W/retention/`                            | per-category retention; `POST W/retention/apply`                                                           |

## 6. Planning, specs (I05/I11)

| Method   | Path                                                              | Notes                                                                                       |
| -------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| GET/POST | `P/milestones/` · PATCH/DELETE `P/milestones/{id}/`               | `{name, target_at, timezone, owner_id, issues, date_confidence}`                            |
| GET/POST | `W/dependencies/` · POST `W/dependencies/{id}/confirm`            | cycle → 422 `DEPENDENCY_CYCLE` with path                                                    |
| GET      | `W/roadmap/?project_ids=&team_id=&from=&to=`                      | projects, milestones, packages (native dates), dependencies with redaction                  |
| POST     | `W/scenarios/` · GET `W/scenarios/{id}/impact` · POST `.../apply` | variants                                                                                    |
| GET/POST | `P/risks/`                                                        | automatic risks carry `cause` link                                                          |
| GET/POST | `P/events/` · GET `P/events.ics`                                  | calendar                                                                                    |
| GET/POST | `W/teams/`                                                        | native Team + scope                                                                         |
| POST     | `P/work-items/{issue_id}/spec/export`                             | `{repository_binding_id, expected_base_commit}` → rendered OpenSpec; conflict on moved head |
| POST     | `P/work-items/{issue_id}/spec/import`                             | `{content, commit}` → new revision or 3-way conflict                                        |
| GET      | `P/work-items/{issue_id}/spec`                                    | sync state                                                                                  |
