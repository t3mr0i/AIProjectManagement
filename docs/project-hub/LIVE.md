# Live server (apps/live): access revocation and reconnect safety

PRD refs: FR-E01, FR-I07, FR-B09, NFR-04 (revoke existing streams within 60 s), NFR-05 (no confirmed change lost on reconnect), AC14, AC30.

## What is enforced

| Layer                                                                               | When                                                              | Check                                                                                                           | On failure                                                                                                                                       |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Connect (`src/lib/auth.ts`)                                                         | Every WebSocket auth                                              | `GET /api/users/me/` with the user's cookie (existing), **plus** `GET …/pages/{id}/` with the same cookie (new) | Connection rejected (`AUTH_DOCUMENT_ACCESS_DENIED`). This also covers reconnects to a document that is already loaded in memory for other users. |
| Periodic re-check (`src/extensions/access-recheck.ts`, `src/lib/access-recheck.ts`) | Every `LIVE_ACCESS_RECHECK_INTERVAL_MS` for every open connection | Same page fetch with that connection's cookie (`src/lib/document-access.ts`)                                    | See below                                                                                                                                        |
| Message gate (`beforeHandleMessage`)                                                | Every incoming message                                            | Rejects if the connection's context is flagged `accessRevoked`                                                  | Connection closed with 4403                                                                                                                      |
| Store (`src/extensions/database.ts`)                                                | Every debounced / final store                                     | If the last writer's context is revoked, store with a still-authorized context of the same document             | If none exists, the store is skipped (it would be rejected by the API anyway)                                                                    |

Re-check result handling:

- **401 / 403 / 404 → revoked.** In this order: context gets `accessRevoked = true`; the connection is set `readOnly` (Hocuspocus then answers further Yjs updates with `syncStatus=false` and does not apply them); a stateless `force_close` message is sent (`reason: "access_revoked"`, `code: 4403`); the connection is closed with close code **4403**, reason **"access revoked"**. Only that user's connection is closed; other users on the document are unaffected.
- **5xx, timeouts, network errors → transient.** The connection stays open. After `LIVE_ACCESS_RECHECK_MAX_FAILURES` consecutive failures it is marked `accessStale` and set to read-only: the user keeps reading, but the server does not accept writes. The first successful check clears the stale flag, resets the counter, and restores the original read-only state.

## Configuration

| Env var                            | Default | Notes                                                                                     |
| ---------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| `LIVE_ACCESS_RECHECK_INTERVAL_MS`  | `30000` | `0` or less turns the periodic re-check off. Values between 1 and 999 are raised to 1000. |
| `LIVE_ACCESS_RECHECK_MAX_FAILURES` | `3`     | Consecutive transient failures before the connection is marked stale. Minimum 1.          |

Worst-case revocation latency is the interval plus the API request time. The axios timeout is 20 s, so at the defaults the worst case is 30 s + 20 s = 50 s, which is under the 60 s NFR-04 limit. A request that times out counts as transient, not as revoked. One timer runs per process, and it is `unref`'d and stopped when no connections are tracked. Each process checks only its own connections, and every instance behind Redis runs its own scheduler.

## Reconnect safety (NFR-05 / AC30)

- The server applies a Yjs update to the in-memory document and then acknowledges it (`syncStatus=true`). That update is "server-confirmed". Redis fans it out to the other live instances.
- Persistence is debounced: `debounce: 10000` in `src/hocuspocus.ts`, with Hocuspocus's default `maxDebounce: 10000`. Confirmed updates are written to the API at most about 10 s after the first unsaved change.
- When the last connection of a document closes, for any reason including a 4403 revocation, Hocuspocus runs the pending store at once (`debouncer.executeNow`) and then unloads the document. Nothing that was confirmed is dropped.
- Hocuspocus stores with the context (cookie) of the connection that sent the _last_ update. If that user was just revoked, the API would reject the store. `resolveStoreContext` swaps in another context for the same document that is still authorized: an open connection first, otherwise the most recently confirmed one, which is kept until the document is unloaded. Without this swap, other users' confirmed edits could fail to save.
- A revoked connection's updates are **not accepted after detection**. They are refused by the `readOnly` flag and by `beforeHandleMessage`. The client does not get a positive ack for them, so they are never counted as confirmed.
- Unconfirmed client changes stay in the client's Y.Doc. For authorized users they are re-sent through the Yjs sync handshake on reconnect.

## Limits

- A client that already received the content keeps it locally (browser memory, IndexedDB, screen). Revocation stops further sync. It cannot erase data the client already has.
- Updates the revoked user sent between the moment access was actually removed and the moment it was detected (at most one interval) were confirmed and are persisted. They cannot be separated out of the shared CRDT state afterwards.
- The re-check calls the page detail endpoint once per connection per interval (no per-user dedupe). With N open connections that is about N / 30 API calls per second at the default interval.
- Only the `project_page` document type exists in `apps/live` today. Issue descriptions are not synced through the live server. A new document type needs a matching branch in `getPageService`, and the re-check then covers it automatically.
- Clients currently treat only close codes 4000–4003 as "forced close, do not reconnect" (`packages/editor/src/hooks/use-yjs-setup.ts`). A 4403 close therefore triggers a reconnect attempt, and the new connect-time document check rejects it. Follow-up (outside apps/live): treat 4403 as terminal in the editor and show the `force_close` message.

## Tests

`apps/live/tests/lib/access-recheck.test.ts` uses vitest with fake timers and a mocked access checker. It covers:

- a revoked connection closes with 4403 within one interval;
- transient errors do not close the connection, and it is marked stale only after N consecutive failures;
- the connection recovers after a successful check;
- on a shared document, only the revoked user's connection is closed;
- the scheduler is cleaned up on disconnect and does nothing when disabled;
- nothing is persisted after revocation: the connection is read-only before close, the store uses an authorized context, it falls back after others disconnect, and it returns null when no authorized context exists.

Run with `pnpm --filter=live test`.
