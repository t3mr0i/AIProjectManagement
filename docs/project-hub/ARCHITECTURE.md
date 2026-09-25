# Architecture: Project Hub as a Plane extension

## Principles (PRD §13, PLANE_DELTA)

1. **One identity.** A work package is `db.Issue` plus a 0..1 `PackageProfile` (`workItemId == issue.id`). Workspaces, projects, users and memberships stay native. Title, priority, assignees and state are never copied into a second live store.
2. **Additive.** New tables are `pf_*` in the Django app `plane.package_flow`, created by one migration. Native tables, state groups, URLs and APIs are unchanged. Activation is per workspace and project, and ordinary issues stay ordinary.
3. **Gates, not signals.** Every critical action re-reads native state synchronously: approval, claim, run start, runner action and merge. Signals only project changes into flags and activity (`MUTATION_PATHS.md`).
4. **Humans approve, agents propose.** The principal kind comes from how the request authenticated, never from the payload (`principal.py`). Only a human with the matching capability can approve execution, code or outcome, publish decisions, or merge.
5. **Customer code never runs in Plane.** `apps/runner` connects outbound, works in its own worktrees and asks the server before every controlled action.

## Components

```text
apps/web (React Router, MobX)                  apps/live (Hocuspocus/Yjs)
  core/components/project-hub/*                  + periodic access re-check → close 4403
  core/services/project-hub/*  ──REST──┐
                                       ▼
apps/api  plane.package_flow (Django, DRF)
  principal.py / capabilities.py   who is acting, what they may do (on native memberships)
  models/        core · execution · integration · collaboration · planning (pf_* tables)
  services/      packages · execution · integrations · delivery · review · specs · diagrams
                 planning · conversations · decisions · knowledge · search · activity
                 notifications · retention · exports · events (transactional outbox)
  adapters/      gitlab · github · jira · linear · azure_devops · generic_git (capability-declared)
  ai/            provider (LLM or offline rules) · context (audience ACL) · clarify
  openspec/      lossless parse/render · three-way merge · manifest
  tasks.py       celery: inbound events, reconcile, lease expiry, outbound field push
        ▲                         ▲
        │ webhooks (signed)       │ Runner token + X-Run-Token
   providers                  apps/runner (ph-runner, stdlib) ── git worktree ── agent adapter
```

## Key flows

- **Package lifecycle.** Activate profile → edit working draft (`expected_version`) → readiness → immutable `PackageRevision` (canonical sha256 over content plus native title/description hash) → human `ExecutionApproval` bound to revision hash, policy, repository scope, allowed actions, checks and limits.
- **Execution.** Claim (a DB unique constraint and fencing counter ensure one exclusive owner) → run start gate. The gate checks approval validity, revocation, expiry and the native source hash (PF06), the claim and the project state. It then issues a hashed run token and an immutable manifest (`manifest_hash`). Each runner action passes the gate: fencing token, lease, allowed action/path/check, time and spend. Cancel invalidates the token.
- **Delivery.** Signed webhook → durable `InboundEvent` (deduplicated by connection and external id; rate-limited; replay window) → normalized events → `MergeRequestLink`, `Evidence` (trust classes), `Delivery` (integrated → deployed → released, rollback appended) → `delivery_summary` per repository. A new head invalidates code reviews. The merge gate re-fetches the provider head.
- **Status projection.** `compute_package_status` derives phase (Drafts/Ready/Build/Review/Ship/Done), lifecycle, delivery and flags from evidence. Native "Done" without delivery shows a flag and is never shown as shipped (FR-B11). List views batch the inputs (`batch_status_facts`).
- **Collaboration.** Conversations (project, package thread, DM) with explicit participants. @AI context includes a source only if every audience member may read it. Decisions snapshot exact message versions and are idempotent. All AI output is an `AIProposal` until a human accepts it.
- **Planning.** Milestones in UTC with a timezone name. Dependencies are typed and confirmed, with cycle detection over confirmed hard edges. The roadmap removes unreadable nodes (or shows an anonymous blocker). Scenarios only preview until applied. Risks carry their cause.
- **Specs and diagrams.** OpenSpec export requires the expected base (no force push) and never approves. Import merges three-way into a new working revision; the approved revision is untouched. Diagram layout changes never create proposals; semantic changes do.

## Security boundaries

- **Read boundary.** Native project membership is checked on every request (`accessible_project_ids`), so revocation needs no re-login. Guests never get execution rights.
- **Private data.** DMs are participant-only (admins included). Exports never give admins someone else's DMs. Deleted sources are tombstoned in decisions.
- **Uploads.** Uploads are MIME-sniffed and scanned before any extraction, and quarantined files never reach AI or search.
- **Webhooks.** The workspace is taken from the connection row, never from the payload. Secrets are encrypted and never returned.
- **Skills.** Product skills are hash-pinned (`skills/manifest.json`). A changed skill is withheld until re-approved.
