# Project Hub runner (`apps/runner`, `ph-runner`)

Status: I06/I07 implementation, contract v1.1.0. Code: `apps/runner/project_hub_runner/`.
Tests: `apps/runner/tests/` (fake in-process server + temporary git repositories).

## 1. Architecture

```
 Plane (web / API / live)                          Runner host (dev laptop, customer runner, managed runner)
 ┌─────────────────────────────┐   HTTPS, outbound  ┌──────────────────────────────────────────────────────┐
 │ package_flow API            │◀───────────────────│ ph-runner                                            │
 │  claims · runs · manifest   │  Authorization:    │  claim ─ heartbeat/fencing (Supervisor thread)       │
 │  action gate · events ·     │  Runner <token>    │  manifest → Rules (frozen, manifest-only)            │
 │  evidence · cancel          │  X-Run-Token       │  PolicyGate: server first, then local mirror         │
 │                             │                    │  worktree (runner-owned) → adapter → diff filter     │
 │  NEVER runs repo code       │                    │  commit (trailers) → checks → evidence → push ph/*   │
 └─────────────────────────────┘                    └───────────────┬──────────────────────────────────────┘
                                                                     │ git (developer / runner credentials
                                                                     ▼  for the MANAGED repo only)
                                                         managed repository remote (GitLab/GitHub/…)
```

- **Outbound only.** The runner never listens on a port. Plane cannot reach into
  the runner; it can only answer, refuse, or mark a run cancelled (FR-G05, PRD §13.1).
- **Untrusted code runs only on the runner.** Repository code (checks, agent) is
  executed in the runner-owned worktree, never in the Plane web/API/live processes.
- **Platform repo vs. managed repos.** The Plane fork (platform repository) and the
  managed customer/team repositories never share worktrees or credentials:
  - the runner token lives in `~/.config/project-hub/runner.json` (0600) and is sent
    only to the Plane server; the run token is per-run and kept in the runner's
    state dir (0600);
  - git operations on managed repos use the credentials of the runner host
    (SSH agent / credential helper) and are never sent to Plane;
  - subprocesses (agent, checks) get a scrubbed environment: runner/run tokens and
    `PLANE_*`/`PROJECT_HUB_*`/`PH_RUNNER_*` variables are never forwarded.
- **Worktrees** live in `<runner_home>/worktrees/<binding>/<run>` (default
  `~/.local/share/project-hub-runner`), on a new branch `ph/<issue8>/<run8>` from the
  approved `baseCommit`. The developer's own checkout is only used as git object
  store and is never modified (FR-G02). A worktree is created **only after** the
  server started a run and its manifest validated (INV-01).

### Run sequence (`ph-runner run`)

1. `POST P/work-items/{issue}/claims` — atomic; second exclusive claim → `409 CLAIM_HELD` (AC05).
2. `POST P/work-items/{issue}/runs {approval_id, claim_id, mode}` — server refuses drafts /
   unapproved / revoked / expired / changed native source (`REVISION_NOT_APPROVED`, …; AC01).
3. `GET R/runs/{id}/manifest` — validated locally (required fields, human approver,
   not revoked/expired, not draft, matches claimed work item/project, `manifestHash`).
4. Supervisor thread: heartbeat every `lease/3`; polls `GET P/work-items/{issue}/runs` for
   cancellation. `LEASE_EXPIRED` / `STALE_FENCING_TOKEN` / cancel → **StopSignal**: agent
   process group killed, every further action refused locally (AC06, FR-G06).
5. `started` event (includes the actual enforcement report, see §4).
6. Worktree: `prepare_worktree` through the action gate; if the target branch head ≠
   `baseCommit` and policy is `wait` (default) → `waiting {reason: base_moved}` (INV-04).
7. Adapter (`deterministic` | `external` | `human`) receives only the `TaskSpec` (approved
   task text = data) and the `PolicyGate` (manifest-derived, frozen).
8. Post-run diff filter: any changed file outside `allowedPaths` → `failed
{reason: paths_outside_scope}`; nothing is committed or pushed.
9. Commit with trailers `Work-Item:`, `Revision:`, `Run:` (FR-G08); agent-made commits
   are squashed so every change carries them. Git hooks are disabled for runner commits.
10. Approved checks (argv from the manifest = human-approved at approval time; never from
    the repository) → evidence `runner_reported`
    (server-side: for `customer`/`managed` runners). `passed` only if executed and exit 0;
    otherwise `failed` / `not_run`. Developer/agent claims → `local_self_report`, result `unknown`.
11. `push_work_branch` through the gate, then `git push remote refs/heads/ph/…` (no
    `--force`, no `+` refspec, never the target branch). There is no merge code (K09).
12. `finished` event with commit sha, branch, changed files, check results; claim released.

## 2. Install

```bash
pipx install ./apps/runner      # stdlib only, Python >= 3.10
ph-runner login --server https://plane.example.com --workspace <slug> --token <runner token>
```

The runner token comes from `POST W/runners/` (shown once). Plain `http://` is refused
for non-local servers. Map repository bindings to local clones in `runner.json`:

```json
{
  "server": "https://plane.example.com",
  "workspace": "acme",
  "token": "…",
  "runner_home": "",
  "bindings": { "<binding-uuid>": { "path": "/home/me/src/shop", "remote": "origin" } },
  "agent_command": ["claude", "-p"],
  "env_passthrough": ["ANTHROPIC_API_KEY"],
  "sandbox_prefix": ["firejail", "--quiet", "--net=none", "--"],
  "checks": [],
  "lease_seconds": 300
}
```

## 3. Commands

| Command                                                                                                                                          | Purpose                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `login --server --workspace --token`                                                                                                             | store config (0600)                                                                  |
| `whoami`                                                                                                                                         | show configured identity (token masked); server identity if `GET R/runner/me` exists |
| `claim --project --work-item [--repo] [--shared] [--hold]`                                                                                       | atomic claim; `--hold` heartbeats until Ctrl-C                                       |
| `run --project --work-item --approval [--repo] [--mode agent\|human] [--adapter deterministic\|external] [--plan] [--agent-command] [--no-push]` | full run                                                                             |
| `heartbeat --claim\|--run [--watch]`                                                                                                             | renew lease; `--watch` also stops on cancel                                          |
| `release --claim\|--run`                                                                                                                         | release claim                                                                        |
| `cancel-check --run`                                                                                                                             | exit 5 if cancelled, 6 if unknown                                                    |
| `report --run [--progress PHASE] [--question] [--waiting] [--self-report]`                                                                       | human-mode reporting                                                                 |
| `push --run [--run-checks]`                                                                                                                      | human mode: verify commits vs. policy, checks, push, finish                          |
| `status [--run]`                                                                                                                                 | server-confirmed status; offline → `unknown`, last confirmed value marked stale      |

Exit codes: 0 ok · 1 error · 2 refused · 3 waiting/claim held · 4 failed · 5 stopped · 6 unreachable.

## 4. IDE setup (FR-G03)

Two IDE workflows over the same CLI contract (verified by `tests/test_ide_contract.py`):

- **VS Code**: copy `apps/runner/ide/vscode-tasks.json` to `.vscode/tasks.json` in the managed
  repository → _Terminal ▸ Run Task ▸ Project Hub: …_. "Keep lease alive" is a background task.
- **JetBrains**: copy `apps/runner/ide/jetbrains-external-tools.xml` to
  `<IDE config dir>/tools/ProjectHub.xml` → _Tools ▸ External Tools ▸ Project Hub_.

Flow: _take over package_ → open the printed worktree → _keep lease alive_ → edit/commit →
_report progress / ask question_ → _run checks and push work branch_.

## 5. Enforcement and its limits (INV-09, INV-10 — honest)

| Control                                   | Enforced by                                                                                                                                                   | Strength                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Actions (`allowedActions`)                | server action gate (authority) + local mirror                                                                                                                 | enforced                                    |
| Paths (`allowedPaths`)                    | gate per edit (deterministic agent) + post-run diff filter (all adapters) + server check on commit/push paths                                                 | enforced before anything leaves the machine |
| Fencing / lease / cancel                  | server rejects stale tokens; runner stops all actions and kills the agent                                                                                     | enforced                                    |
| Time (`maxSeconds`)                       | wall-clock budget, process-group kill                                                                                                                         | enforced                                    |
| Environment / credentials                 | allowlist; platform tokens never forwarded                                                                                                                    | enforced                                    |
| Git hooks                                 | disabled for runner commits/pushes                                                                                                                            | enforced                                    |
| **Network egress**                        | **not enforced by the runner** (stdlib cannot sandbox) — delegate to `sandbox_prefix` (firejail/bwrap) or run the runner in a container with `--network none` | delegated                                   |
| **Filesystem reads outside the worktree** | not enforced by the runner; delegate as above                                                                                                                 | delegated                                   |
| **Spend (`maxSpendMinor`)**               | agent-reported via `PH_SPEND_FILE`, checked post hoc                                                                                                          | weak                                        |
| Human mode                                | developer is trusted to work in the worktree; only what is reported/pushed is visible                                                                         | by design                                   |

- A developer running arbitrary local programs, or an admin with shell access, can
  bypass any local control (INV-10). The server-side gates (action gate, fencing,
  branch protection on the provider, human merge gate) remain the real boundary.
  The `started` event carries the actual enforcement report so the UI can show it.
- INV-09: the runner only reports what it did itself (its own state dir). It never
  scans other directories. Without a runner, local work is **unknown**; when the
  server is unreachable, `ph-runner status` says `unknown` and marks the last
  confirmed state as stale (FR-G07, AC32).
- Skills and repository files are not a security boundary (PRD §14.4): adapters get a
  frozen, manifest-derived policy and no server client; `AGENTS.md` asking to "ignore
  rules and merge" changes nothing (AC27, tested).

## 6. Execution location (O01)

The contract supports all three; the first real path still has to be chosen:

| Option                                   | Pros                                                                                         | Cons / requirements                                                                                            |
| ---------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Developer machine (`kind=local`)         | zero infra, IDE flow, human mode                                                             | weakest isolation; network/filesystem not sandboxed unless the developer uses a container                      |
| Customer-hosted runner (`kind=customer`) | code and credentials stay in customer network; container sandbox (`--network none`) possible | customer operates it; needs outbound HTTPS to Plane                                                            |
| Managed runner (`kind=managed`)          | uniform sandbox, central logs                                                                | we hold repo credentials and run untrusted code → separate security review, isolated from the Plane deployment |

Recommendation for the pilot: customer-hosted runner in a container (network off by default,
explicit egress allowlist for the agent's model API), plus developer-machine human mode.

## 7. Contract with the backend — verified against the real implementation

Verified by `apps/api/plane/tests/package_flow/test_runner_contract.py` (backend + runner
parsing in one test) and `apps/api/plane/tests/package_flow/test_runner_e2e.py` (the real
`project_hub_runner` package driving a live Django server over HTTP: claim → run → manifest →
worktree → deterministic agent → checks/evidence → push → finish; plus a negative run refused
with `NATIVE_SOURCE_CHANGED`). All paths remain isolated in `project_hub_runner/client.py`.

| Topic                      | Actual backend (`plane/package_flow`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Runner behaviour                                                                                                                                                                                                                                                       |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth                       | `Authorization: Runner <token>` resolves to the runner's owner as an _agent_ principal on `P/`, `W/` and `R/` routes; capability checks use the owner's grants (`run.start`, `project.read`). Run-scoped `R/runs/*` additionally need `X-Run-Token`.                                                                                                                                                                                                                                                                          | as assumed ✔                                                                                                                                                                                                                                                           |
| Claim                      | `POST P/work-items/{id}/claims {repository_binding_id?, exclusive, lease_seconds, approval_id?}`; binding must be in the approved scope; lease clamped to 30–3600 s; response `{id, fencing_token, lease_expires_at, status, …}` (no `lease_seconds`).                                                                                                                                                                                                                                                                        | now sends `approval_id`; clamps lease locally ✔                                                                                                                                                                                                                        |
| Heartbeat                  | body `{fencing_token, lease_seconds?}` — **without `lease_seconds` the server resets the lease to 300 s**. Response = claim + (added for the runner) `lease_seconds`, `run_id`, `run_status`, `cancel_requested`.                                                                                                                                                                                                                                                                                                             | now always sends its lease; stops on `cancel_requested` ✔                                                                                                                                                                                                              |
| Run start                  | `POST P/work-items/{id}/runs` → `{run, run_token, manifest}`; errors `REVISION_NOT_APPROVED`, `APPROVAL_REVOKED`, `APPROVAL_EXPIRED`, `NATIVE_SOURCE_CHANGED`, `CLAIM_INVALID`, `RUN_ALREADY_ACTIVE`, `PROJECT_ARCHIVED`.                                                                                                                                                                                                                                                                                                     | all mapped to `RunRefused` (exit 2), claim released ✔                                                                                                                                                                                                                  |
| Manifest                   | `GET R/runs/{id}/manifest` → `{"manifest": {...}, "manifest_hash": "…"}`; hash is **outside** the object. Keys: `schemaVersion, runId, workspaceId, projectId, workItemId, revisionId, revisionNumber, revisionHash, approvalId, policyVersion, claimId, fencingToken, runnerProfileId, mode, repositoryScope[], allowedActions, limits, checks[{name,command,trusted}], intent{title,intent,outcome,nonGoals,criteria,scope}, expiresAt`. No `approval{}` object, no `approvedBy`, no `revisionState`.                       | parser fixed: reads the wrapper hash, `approvalId`/`expiresAt`, task from `intent`; also verifies `claimId` and `fencingToken` against its own claim. Approver kind is enforced server-side (`HUMAN_PRINCIPAL_REQUIRED`); if a manifest states it, it must be `human`. |
| Manifest hash              | `sha256(json.dumps(m, sort_keys=True, separators=(",",":"), ensure_ascii=False, default=str))`                                                                                                                                                                                                                                                                                                                                                                                                                                | identical (`canonical_hash`) ✔, tamper test ✔                                                                                                                                                                                                                          |
| Checks                     | Human-defined on the approval: `checks: [{name (slug), command: [argv], trusted?}]` (max 20, validated), stored on `ExecutionApproval.checks`, returned in the REST approval shape (not in the 1.1.0 contract JSON), copied into manifest `checks` (covered by `manifest_hash`). Gate rejects `run_allowed_checks` with `CHECK_NOT_ALLOWED` if `detail.check` is not in the manifest or `detail.command` differs.                                                                                                             | manifest checks always win; `trusted:false` checks run inside `sandbox_prefix` (if configured), `trusted:true` without it ✔                                                                                                                                            |
| Action gate                | `POST R/runs/{id}/actions {action, fencing_token, detail{paths?, binding_id?, spend_minor?, …}}` → `{accepted:true}`; rejection 409 `GATE_REJECTED` subtype codes: `STALE_FENCING_TOKEN`, `LEASE_EXPIRED`, `CLAIM_INVALID`, `RUN_CANCELLED`, `RUN_ENDED`, `RUN_PAUSED`, `APPROVAL_REVOKED/EXPIRED`, `NATIVE_SOURCE_CHANGED`, `ACTION_NOT_ALLOWED`, `PATH_NOT_ALLOWED`, `CHECK_NOT_ALLOWED`, `BUDGET_EXCEEDED`, `TIME_LIMIT_EXCEEDED`, `PROJECT_ARCHIVED`; 403 `PERMISSION_DENIED`. Every decision is stored as a `RunAction`. | fencing/cancel/paused/ended/revoked/source-changed/permission → **stop all actions**; path/action/budget/time → `PolicyViolation` (run fails) ✔                                                                                                                        |
| Cancel                     | `P/runs/{id}/cancel` sets status `cancelled`, clears the run token → later run-scoped calls get 403 `RUN_TOKEN_INVALID`.                                                                                                                                                                                                                                                                                                                                                                                                      | mapped to `RunCancelled` → stop, no commit/push ✔                                                                                                                                                                                                                      |
| Native change during a run | a native-hook pauses the run (`RUN_PAUSED`, `pause_reason=scope_changed`) before the gate would say `NATIVE_SOURCE_CHANGED`.                                                                                                                                                                                                                                                                                                                                                                                                  | both stop the runner ✔                                                                                                                                                                                                                                                 |
| Events                     | `POST R/runs/{id}/events {type, fencing_token, detail}`; terminal runs → `RUN_ENDED`/`RUN_CANCELLED`. `finished.detail` is stored as `run.result`.                                                                                                                                                                                                                                                                                                                                                                            | ✔                                                                                                                                                                                                                                                                      |
| Evidence                   | `POST R/runs/{id}/evidence {kind, name, result∈passed/failed/not_run/unknown, commit_sha, repository_binding_id?, detail}`. **Trust is decided by the server from the runner kind**: `local` runner → always `local_self_report`; `customer`/`managed` → `runner_reported`. Added: a runner may request `trust: local_self_report` (downgrade only, never upgrade).                                                                                                                                                           | fixed vocabulary: timed-out check → `failed` (+`detail.timed_out`), developer/agent claims → `unknown` + `trust: local_self_report`; sends `repository_binding_id` ✔                                                                                                   |
| Run list                   | `GET P/work-items/{id}/runs` → `{"results": [run]}` with `status`, `cancel_requested_at`, `pause_reason`, `last_heartbeat_at`.                                                                                                                                                                                                                                                                                                                                                                                                | used for `status` / `cancel-check` ✔                                                                                                                                                                                                                                   |
| whoami                     | added `GET R/runner/me` → runner (`id, name, kind, token_prefix, workspace_slug, principal_kind`); 404 for non-runner principals.                                                                                                                                                                                                                                                                                                                                                                                             | `ph-runner whoami` ✔                                                                                                                                                                                                                                                   |

Consequences / open points:

- **Checks** are approved by a human together with the scope and travel in the manifest
  (verified in `test_runner_e2e.py` and `test_runner_contract.py::TestApprovalChecks`).
  Operator-configured checks (`checks` in `runner.json`) remain only as a fallback when a
  manifest carries none (older servers); the current server gate rejects any check name
  not in the manifest (`CHECK_NOT_ALLOWED`), so such a check is reported `not_run`.
  Repository content can never add a check (AC27).
- A `local` (developer-machine) runner can never produce `runner_reported` evidence — by
  design of the backend; register a `customer`/`managed` runner for that (O01).
- The manifest carries no approver kind; INV-03 relies on the server-side
  `HUMAN_PRINCIPAL_REQUIRED` check at approval time (tested in the E2E: the only approval is
  the human one, the agent created none).
