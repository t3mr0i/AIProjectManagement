/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ACCESS_REVOKED_CLOSE_REASON,
  AccessRecheckScheduler,
  AccessRevokedError,
  classifyAccessError,
} from "@/lib/access-recheck";
import type { AccessCheckResult, AccessRecheckContext, RecheckConnection } from "@/lib/access-recheck";
import { CloseCode, ForceCloseReason } from "@/types/admin-commands";

type TestContext = AccessRecheckContext & { userId: string };

const INTERVAL = 30_000;

const createConnection = () => {
  const connection = {
    readOnly: false,
    close: vi.fn<RecheckConnection["close"]>(),
    sendStateless: vi.fn<RecheckConnection["sendStateless"]>(),
  };
  return connection satisfies RecheckConnection;
};

const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { statusCode: status });

describe("classifyAccessError", () => {
  it("treats 401/403/404 as revoked", () => {
    expect(classifyAccessError(httpError(401))).toBe("revoked");
    expect(classifyAccessError(httpError(403))).toBe("revoked");
    expect(classifyAccessError({ response: { status: 404 } })).toBe("revoked");
  });

  it("treats 5xx, network errors and unknown values as transient", () => {
    expect(classifyAccessError(httpError(500))).toBe("error");
    expect(classifyAccessError(httpError(503))).toBe("error");
    expect(classifyAccessError(new Error("ECONNRESET"))).toBe("error");
    expect(classifyAccessError(undefined)).toBe("error");
  });
});

describe("AccessRecheckScheduler", () => {
  let checkAccess: ReturnType<typeof vi.fn<(context: TestContext, documentName: string) => Promise<AccessCheckResult>>>;
  let scheduler: AccessRecheckScheduler<TestContext>;

  beforeEach(() => {
    vi.useFakeTimers();
    checkAccess = vi.fn<(context: TestContext, documentName: string) => Promise<AccessCheckResult>>();
    checkAccess.mockResolvedValue("granted");
    scheduler = new AccessRecheckScheduler<TestContext>({
      intervalMs: INTERVAL,
      maxConsecutiveFailures: 3,
      checkAccess,
    });
  });

  afterEach(() => {
    scheduler.reset();
    vi.useRealTimers();
  });

  it("AC14 FR-E01: closes a revoked connection within one interval with code 4403", async () => {
    const connection = createConnection();
    const context: TestContext = { userId: "u1" };
    scheduler.track(connection, context, "page-1");

    checkAccess.mockResolvedValue("revoked");
    await vi.advanceTimersByTimeAsync(INTERVAL);

    expect(checkAccess).toHaveBeenCalledWith(context, "page-1");
    expect(connection.close).toHaveBeenCalledTimes(1);
    expect(connection.close).toHaveBeenCalledWith({
      code: CloseCode.ACCESS_REVOKED,
      reason: ACCESS_REVOKED_CLOSE_REASON,
    });
    expect(CloseCode.ACCESS_REVOKED).toBe(4403);
    const notice = JSON.parse(connection.sendStateless.mock.calls[0][0]);
    expect(notice).toMatchObject({ type: "force_close", reason: ForceCloseReason.ACCESS_REVOKED, code: 4403 });
    expect(context.accessRevoked).toBe(true);
    expect(connection.readOnly).toBe(true);
    expect(scheduler.size).toBe(0);
  });

  it("does not close on transient errors and marks stale (read-only) only after N consecutive failures", async () => {
    const connection = createConnection();
    const context: TestContext = { userId: "u1" };
    scheduler.track(connection, context, "page-1");

    checkAccess.mockResolvedValue("error");
    await vi.advanceTimersByTimeAsync(INTERVAL * 2);
    expect(connection.close).not.toHaveBeenCalled();
    expect(context.accessStale).toBeFalsy();
    expect(connection.readOnly).toBe(false);

    await vi.advanceTimersByTimeAsync(INTERVAL);
    expect(connection.close).not.toHaveBeenCalled();
    expect(context.accessStale).toBe(true);
    expect(connection.readOnly).toBe(true);
    expect(scheduler.size).toBe(1);
  });

  it("treats a throwing checker as transient", async () => {
    const connection = createConnection();
    scheduler.track(connection, { userId: "u1" }, "page-1");
    checkAccess.mockRejectedValue(new Error("socket hang up"));
    await vi.advanceTimersByTimeAsync(INTERVAL);
    expect(connection.close).not.toHaveBeenCalled();
  });

  it("keeps the connection open and restores writes once access is re-confirmed", async () => {
    const connection = createConnection();
    const context: TestContext = { userId: "u1" };
    scheduler.track(connection, context, "page-1");

    checkAccess.mockResolvedValue("error");
    await vi.advanceTimersByTimeAsync(INTERVAL * 3);
    expect(connection.readOnly).toBe(true);

    checkAccess.mockResolvedValue("granted");
    await vi.advanceTimersByTimeAsync(INTERVAL);
    expect(connection.close).not.toHaveBeenCalled();
    expect(context.accessStale).toBe(false);
    expect(connection.readOnly).toBe(false);

    // failure counter was reset by the successful check
    checkAccess.mockResolvedValue("error");
    await vi.advanceTimersByTimeAsync(INTERVAL * 2);
    expect(connection.readOnly).toBe(false);
  });

  it("keeps an originally read-only connection read-only after recovery", async () => {
    const connection = createConnection();
    connection.readOnly = true;
    const context: TestContext = { userId: "u1" };
    scheduler.track(connection, context, "page-1");
    checkAccess.mockResolvedValue("error");
    await vi.advanceTimersByTimeAsync(INTERVAL * 3);
    checkAccess.mockResolvedValue("granted");
    await vi.advanceTimersByTimeAsync(INTERVAL);
    expect(connection.readOnly).toBe(true);
  });

  it("only closes the revoked user's connection on a shared document", async () => {
    const revokedConn = createConnection();
    const keptConn = createConnection();
    const revoked: TestContext = { userId: "revoked" };
    const kept: TestContext = { userId: "kept" };
    scheduler.track(revokedConn, revoked, "page-1");
    scheduler.track(keptConn, kept, "page-1");

    checkAccess.mockImplementation(async (ctx) => (ctx.userId === "revoked" ? "revoked" : "granted"));
    await vi.advanceTimersByTimeAsync(INTERVAL);

    expect(revokedConn.close).toHaveBeenCalledTimes(1);
    expect(keptConn.close).not.toHaveBeenCalled();
    expect(scheduler.size).toBe(1);
  });

  it("stops checking a connection after disconnect and stops the timer when idle", async () => {
    const connection = createConnection();
    const context: TestContext = { userId: "u1" };
    scheduler.track(connection, context, "page-1");
    scheduler.untrackContext(context, "page-1");

    checkAccess.mockResolvedValue("revoked");
    await vi.advanceTimersByTimeAsync(INTERVAL * 2);
    expect(checkAccess).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does nothing when disabled (interval <= 0)", async () => {
    const disabled = new AccessRecheckScheduler<TestContext>({
      intervalMs: 0,
      maxConsecutiveFailures: 3,
      checkAccess,
    });
    disabled.track(createConnection(), { userId: "u1" }, "page-1");
    expect(disabled.size).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  describe("no persistence after revocation", () => {
    it("marks the connection read-only before closing so later updates are rejected", async () => {
      const connection = createConnection();
      const context: TestContext = { userId: "u1" };
      const readOnlyAtClose: boolean[] = [];
      connection.close.mockImplementation(() => {
        readOnlyAtClose.push(connection.readOnly);
      });
      scheduler.track(connection, context, "page-1");

      checkAccess.mockResolvedValue("revoked");
      await scheduler.runChecks();

      expect(readOnlyAtClose).toEqual([true]);
      expect(scheduler.isRevoked(context)).toBe(true);
      // beforeHandleMessage throws this; Hocuspocus closes with its code/reason
      const error = new AccessRevokedError();
      expect(error.code).toBe(4403);
      expect(error.reason).toBe(ACCESS_REVOKED_CLOSE_REASON);
    });

    it("AC30 FR-E01: stores with a still-authorized context when the last writer was revoked", async () => {
      const revokedConn = createConnection();
      const keptConn = createConnection();
      const revoked: TestContext = { userId: "revoked" };
      const kept: TestContext = { userId: "kept" };
      scheduler.track(keptConn, kept, "page-1");
      scheduler.track(revokedConn, revoked, "page-1");

      checkAccess.mockImplementation(async (ctx) => (ctx.userId === "revoked" ? "revoked" : "granted"));
      await scheduler.runChecks();

      expect(scheduler.resolveStoreContext("page-1", revoked)).toBe(kept);
      // non-revoked context is passed through untouched
      expect(scheduler.resolveStoreContext("page-1", kept)).toBe(kept);
    });

    it("AC30 NFR-05: falls back to the last authorized context after other users disconnected (final flush)", async () => {
      const keptConn = createConnection();
      const revokedConn = createConnection();
      const kept: TestContext = { userId: "kept" };
      const revoked: TestContext = { userId: "revoked" };
      scheduler.track(keptConn, kept, "page-1");
      scheduler.untrackContext(kept, "page-1");
      scheduler.track(revokedConn, revoked, "page-1");

      checkAccess.mockResolvedValue("revoked");
      await scheduler.runChecks();

      expect(scheduler.resolveStoreContext("page-1", revoked)).toBe(kept);
      scheduler.forgetDocument("page-1");
      expect(scheduler.resolveStoreContext("page-1", revoked)).toBeNull();
    });

    it("never persists with a revoked context when no authorized context exists", async () => {
      const connection = createConnection();
      const revoked: TestContext = { userId: "revoked" };
      scheduler.track(connection, revoked, "page-1");
      checkAccess.mockResolvedValue("revoked");
      await scheduler.runChecks();
      expect(scheduler.resolveStoreContext("page-1", revoked)).toBeNull();
    });
  });
});
