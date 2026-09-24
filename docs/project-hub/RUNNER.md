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
10. Approved checks (argv from the manifest only) → evidence `runner_reported`
    (`passed` only if executed and exit 0; otherwise `failed` / `timed_out` / `not_run`).
    Developer/agent claims → evidence `local_self_report`, result `claimed`.
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

## 7. Contract assumptions for the backend (please confirm/adjust)

The HTTP client isolates all paths in `project_hub_runner/client.py` (`Paths`). The runner assumes:

- Manifest (`GET R/runs/{id}/manifest`) is either the object or `{"manifest": {...}}`, camelCase or
  snake_case, with: `runId`, `workspaceId`, `projectId`, `workItemId`, `revisionId`,
  `revisionHash` (64 hex), `policyVersion`, `approval {id, approvedBy {kind: "human"},
expiresAt, revokedAt, revisionId?, revisionHash?}`, `repositoryScope[{bindingId, baseCommit,
targetBranch, allowedPaths}]`, `allowedActions`, `limits {maxSeconds, maxSpendMinor, currency}`.
  Optional: `revisionState` (anything but `approved` is refused), `checks [{name, command: [argv],
timeoutSeconds?}]`, `task {title, intent, outcome, criteria, nonGoals}`,
  `policy.onBaseMoved` (`wait` default | `continue`), `manifestHash`.
- `manifestHash` = SHA-256 hex of `json.dumps(manifest_without_hash, sort_keys=True,
separators=(",", ":"), ensure_ascii=False)` UTF-8.
- Heartbeat response may include `lease_seconds` and `cancel_requested: true`.
- `GET P/work-items/{issue}/runs` items carry `id`, `status` and `cancel_requested_at`
  (used for cancel polling and `status`).
- Error codes mapped: `CLAIM_HELD` (`detail.holder`), `STALE_FENCING_TOKEN`, `LEASE_EXPIRED`,
  `CLAIM_INVALID`, `REVISION_NOT_APPROVED`, `APPROVAL_REVOKED`, `APPROVAL_EXPIRED`,
  `NATIVE_SOURCE_CHANGED`, `PROJECT_ARCHIVED`, `RUN_CANCELLED` / `RUN_TOKEN_EXPIRED` /
  `RUN_TOKEN_INVALID` (→ stop), `ACTION_NOT_ALLOWED` / `PATH_NOT_ALLOWED` /
  `BUDGET_EXCEEDED` (→ action rejected), `IDEMPOTENCY_MISMATCH`, `EXTENSION_DISABLED`.
- Action gate body `{action, fencing_token, detail: {paths?, spend_minor?, binding_id, branch?,
head_sha?, check?}}`; evidence body `{fencing_token, kind, name, trust, result, executed,
exit_code?, commit_sha, detail}`.
- Proposed (not in API.md yet): `GET R/runner/me` for `whoami`; `whoami` degrades gracefully on 404.
