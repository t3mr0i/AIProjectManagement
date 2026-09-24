/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Periodic document access re-check for open realtime connections
 * (Project Hub PRD: FR-I07, FR-B09, NFR-04 — "existing streams revoked within 60 s").
 *
 * This module is intentionally free of env/service imports so it can be unit-tested
 * with fake timers and an injected access checker. See docs/project-hub/LIVE.md.
 */

import { CloseCode, ForceCloseReason, getForceCloseMessage } from "@/types/admin-commands";
import type { ClientForceCloseMessage } from "@/types/admin-commands";

export type AccessCheckResult = "granted" | "revoked" | "error";

export const ACCESS_REVOKED_CLOSE_REASON = "access revoked";

/** Minimal surface of a Hocuspocus `Connection` that the scheduler needs. */
export interface RecheckConnection {
  readOnly: boolean;
  close(event?: { code: number; reason: string }): void;
  sendStateless(payload: string): void;
}

/** Flags written onto the per-connection Hocuspocus context. */
export interface AccessRecheckContext {
  /** Set once the API denied access (401/403/404). Never reset for this connection. */
  accessRevoked?: boolean;
  /** Set after N consecutive transient check failures; cleared on the next successful check. */
  accessStale?: boolean;
}

export interface AccessRecheckLogger {
  info(message: string, meta?: unknown): void;
  warn(message: string, meta?: unknown): void;
  error(message: string, meta?: unknown): void;
}

export interface AccessRecheckOptions<C extends AccessRecheckContext> {
  /** Interval between checks for every tracked connection. <= 0 disables the timer. */
  intervalMs: number;
  /** Consecutive transient failures before a connection is marked stale (writes paused). */
  maxConsecutiveFailures: number;
  checkAccess: (context: C, documentName: string) => Promise<AccessCheckResult>;
  logger?: AccessRecheckLogger;
}

interface Entry<C extends AccessRecheckContext> {
  connection: RecheckConnection;
  context: C;
  documentName: string;
  initialReadOnly: boolean;
  consecutiveFailures: number;
  inFlight: boolean;
}

const REVOKED_STATUS_CODES = new Set([401, 403, 404]);

/**
 * Classify an error thrown by an API call: 401/403/404 mean the user lost access,
 * everything else (5xx, timeouts, network errors) is transient.
 */
export const classifyAccessError = (error: unknown): AccessCheckResult => {
  if (error && typeof error === "object") {
    const err = error as { statusCode?: unknown; response?: { status?: unknown } };
    const status = typeof err.statusCode === "number" ? err.statusCode : err.response?.status;
    if (typeof status === "number" && REVOKED_STATUS_CODES.has(status)) return "revoked";
  }
  return "error";
};

/** Error thrown from `beforeHandleMessage`; Hocuspocus closes the connection with `code`/`reason`. */
export class AccessRevokedError extends Error {
  code = CloseCode.ACCESS_REVOKED;
  reason = ACCESS_REVOKED_CLOSE_REASON;
  constructor() {
    super(ACCESS_REVOKED_CLOSE_REASON);
    this.name = "AccessRevokedError";
  }
}

export class AccessRecheckScheduler<C extends AccessRecheckContext> {
  private readonly entries = new Map<RecheckConnection, Entry<C>>();
  /**
   * Contexts per document that passed an access check (most recent last), kept until the document
   * is unloaded; used to flush the store after the last writer was revoked.
   */
  private readonly authorizedContexts = new Map<string, Set<C>>();
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly options: AccessRecheckOptions<C>) {}

  get enabled(): boolean {
    return this.options.intervalMs > 0;
  }

  get size(): number {
    return this.entries.size;
  }

  /** Start tracking a connection that just passed authentication. */
  track(connection: RecheckConnection, context: C, documentName: string): void {
    if (!this.enabled) return;
    this.entries.set(connection, {
      connection,
      context,
      documentName,
      initialReadOnly: connection.readOnly,
      consecutiveFailures: 0,
      inFlight: false,
    });
    this.rememberAuthorized(documentName, context);
    this.ensureTimer();
  }

  /** Stop tracking all connections that belong to the given context/document (called from onDisconnect). */
  untrackContext(context: C, documentName: string): void {
    for (const [connection, entry] of this.entries) {
      if (entry.context === context && entry.documentName === documentName) this.entries.delete(connection);
    }
    this.stopTimerIfIdle();
  }

  /** Drop per-document state once the document is unloaded from memory (after its final store). */
  forgetDocument(documentName: string): void {
    this.authorizedContexts.delete(documentName);
  }

  isRevoked(context: C | undefined | null): boolean {
    return !!context?.accessRevoked;
  }

  /**
   * Hocuspocus stores with the context of the connection that produced the LAST update.
   * If that connection has since been revoked its cookie would be rejected by the API and
   * the other users' confirmed edits would not be saved. Swap in a still-authorized context
   * for the same document; return null if none exists (nothing can be persisted safely).
   */
  resolveStoreContext(documentName: string, context: C): C | null {
    if (!context?.accessRevoked) return context;
    for (const entry of this.entries.values()) {
      if (entry.documentName === documentName && !entry.context.accessRevoked && !entry.context.accessStale) {
        return entry.context;
      }
    }
    const known = [...(this.authorizedContexts.get(documentName) ?? [])];
    return known.findLast((candidate) => !candidate.accessRevoked) ?? null;
  }

  /** Run one check round for every tracked connection. Exposed for tests. */
  async runChecks(): Promise<void> {
    const pending: Promise<void>[] = [];
    for (const entry of this.entries.values()) {
      if (entry.inFlight) continue;
      pending.push(this.checkEntry(entry));
    }
    await Promise.all(pending);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  /** Stop the timer and forget all state (server shutdown / tests). */
  reset(): void {
    this.stop();
    this.entries.clear();
    this.authorizedContexts.clear();
  }

  private async checkEntry(entry: Entry<C>): Promise<void> {
    entry.inFlight = true;
    let result: AccessCheckResult;
    try {
      result = await this.options.checkAccess(entry.context, entry.documentName);
    } catch (error) {
      result = classifyAccessError(error);
    } finally {
      entry.inFlight = false;
    }

    // Connection may have disconnected while the check was running.
    if (this.entries.get(entry.connection) !== entry) return;

    if (result === "granted") {
      entry.consecutiveFailures = 0;
      if (entry.context.accessStale) {
        entry.context.accessStale = false;
        entry.connection.readOnly = entry.initialReadOnly;
        this.options.logger?.info(`[ACCESS_RECHECK] Access re-confirmed, resuming writes for ${entry.documentName}`);
      }
      this.rememberAuthorized(entry.documentName, entry.context);
      return;
    }

    if (result === "revoked") {
      this.revoke(entry);
      return;
    }

    entry.consecutiveFailures += 1;
    if (entry.consecutiveFailures >= this.options.maxConsecutiveFailures && !entry.context.accessStale) {
      // Keep the connection open (read state stays), but stop accepting writes until access is confirmed.
      entry.context.accessStale = true;
      entry.connection.readOnly = true;
      this.options.logger?.warn(
        `[ACCESS_RECHECK] ${entry.consecutiveFailures} consecutive check failures for ${entry.documentName}; marked stale (read-only)`
      );
    }
  }

  private revoke(entry: Entry<C>): void {
    // Order matters: flag + read-only first so no further update from this connection is applied.
    entry.context.accessRevoked = true;
    entry.connection.readOnly = true;
    this.entries.delete(entry.connection);
    this.authorizedContexts.get(entry.documentName)?.delete(entry.context);

    this.options.logger?.info(`[ACCESS_RECHECK] Access revoked, closing connection for ${entry.documentName}`);

    const message: ClientForceCloseMessage = {
      type: "force_close",
      reason: ForceCloseReason.ACCESS_REVOKED,
      code: CloseCode.ACCESS_REVOKED,
      message: getForceCloseMessage(ForceCloseReason.ACCESS_REVOKED),
      timestamp: new Date().toISOString(),
    };
    try {
      entry.connection.sendStateless(JSON.stringify(message));
    } catch (error) {
      this.options.logger?.error("[ACCESS_RECHECK] Failed to notify client about revocation", error);
    }
    try {
      entry.connection.close({ code: CloseCode.ACCESS_REVOKED, reason: ACCESS_REVOKED_CLOSE_REASON });
    } catch (error) {
      this.options.logger?.error("[ACCESS_RECHECK] Failed to close revoked connection", error);
    }
    this.stopTimerIfIdle();
  }

  private rememberAuthorized(documentName: string, context: C): void {
    if (context.accessRevoked) return;
    let known = this.authorizedContexts.get(documentName);
    if (!known) {
      known = new Set<C>();
      this.authorizedContexts.set(documentName, known);
    }
    // re-insert so the most recently confirmed context is last
    known.delete(context);
    known.add(context);
  }

  private ensureTimer(): void {
    if (this.timer || !this.enabled) return;
    this.timer = setInterval(() => {
      this.runChecks().catch((error: unknown) => {
        this.options.logger?.error("[ACCESS_RECHECK] Check round failed", error);
      });
    }, this.options.intervalMs);
    // Never keep the process alive just for re-checks.
    this.timer.unref?.();
  }

  private stopTimerIfIdle(): void {
    if (this.entries.size === 0) this.stop();
  }
}
