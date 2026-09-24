# project-hub-runner (`ph-runner`)

External runner / CLI for the Project Hub package flow (Plane extension, I06/I07).
It connects **outbound** to Plane, claims an approved work item, prepares a
runner-owned git worktree, lets a human (IDE) or an agent implement the change
within the approved scope, reports evidence and pushes a `ph/…` work branch.
It never merges.

- Python ≥ 3.10, **standard library only** at runtime (installs anywhere).
- Full architecture, enforcement limits and IDE setup: [`docs/project-hub/RUNNER.md`](../../docs/project-hub/RUNNER.md).

## Install

```bash
pipx install ./apps/runner          # or: python -m pip install ./apps/runner
ph-runner --help                    # or without installing: python -m project_hub_runner --help
```

## Quick start

```bash
# 1. token from POST /api/workspaces/{slug}/package-flow/runners/ (shown once)
ph-runner login --server https://plane.example.com --workspace acme --token <RUNNER_TOKEN>

# 2. map repository bindings to local clones (edit ~/.config/project-hub/runner.json)
#    "bindings": {"<binding-uuid>": {"path": "/home/me/src/shop-backend", "remote": "origin"}}

# 3a. agent mode, deterministic test agent (built-in demo or --plan plan.json)
ph-runner run --project <P> --work-item <ISSUE> --approval <APPROVAL>

# 3b. external coding agent (command is operator config, never repo content)
ph-runner run --project <P> --work-item <ISSUE> --approval <APPROVAL> --adapter external --agent-command "claude -p"

# 3c. human mode: worktree + instructions, then work in your IDE
ph-runner run --mode human --project <P> --work-item <ISSUE> --approval <APPROVAL>
ph-runner heartbeat --run <RUN> --watch
ph-runner report --run <RUN> --progress implementing
ph-runner push --run <RUN> --run-checks

ph-runner status            # server-confirmed status; "unknown (stale)" when offline
```

Commands: `login`, `whoami`, `claim`, `run`, `heartbeat`, `release`,
`cancel-check`, `report`, `push`, `status`. Add `--json` for machine output.

Exit codes: `0` ok · `1` error · `2` refused/invalid (e.g. `REVISION_NOT_APPROVED`) ·
`3` waiting / claim held / base moved · `4` failed (policy, workspace) ·
`5` stopped (fencing lost, lease expired, cancelled) · `6` server unreachable (state unknown).

## IDE integration

- VS Code: copy `ide/vscode-tasks.json` to `.vscode/tasks.json` of the managed repository.
- JetBrains: copy `ide/jetbrains-external-tools.xml` to `<IDE config>/tools/ProjectHub.xml`.

Both call the same CLI contract (tested in `tests/test_ide_contract.py`).

## Development

```bash
cd apps/runner
python -m pytest tests -q          # fake in-process server + temporary git repos
ruff check . && ruff format --check .
```

Module map: `client.py` (all HTTP paths — adjust here if the server contract moves),
`manifest.py`, `claim.py`, `policy.py`, `workspace.py`, `git_ops.py`, `reporter.py`,
`checks.py`, `sandbox.py`, `runner.py` (orchestration), `cli.py`, `agents/`.
