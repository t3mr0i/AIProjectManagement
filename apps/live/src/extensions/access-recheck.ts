/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  Extension,
  connectedPayload,
  afterUnloadDocumentPayload,
  beforeHandleMessagePayload,
  onDisconnectPayload,
} from "@hocuspocus/server";
import { logger } from "@plane/logger";
import { env } from "@/env";
import { AccessRecheckScheduler, AccessRevokedError } from "@/lib/access-recheck";
import type { RecheckConnection } from "@/lib/access-recheck";
import { checkDocumentAccess } from "@/lib/document-access";
import type { HocusPocusServerContext } from "@/types";

/**
 * Shared scheduler instance; the Database extension uses it to pick a still-authorized
 * context when flushing a document whose last writer was revoked.
 */
export const accessRecheckScheduler = new AccessRecheckScheduler<HocusPocusServerContext>({
  intervalMs: env.LIVE_ACCESS_RECHECK_INTERVAL_MS > 0 ? Math.max(env.LIVE_ACCESS_RECHECK_INTERVAL_MS, 1000) : 0,
  maxConsecutiveFailures: Math.max(env.LIVE_ACCESS_RECHECK_MAX_FAILURES, 1),
  checkAccess: checkDocumentAccess,
  logger,
});

/**
 * Re-validates document access for every open connection on an interval and closes
 * connections whose access was revoked (close code 4403 "access revoked").
 */
export class AccessRecheck implements Extension {
  name = "AccessRecheck";

  async connected({ connectionInstance, context, documentName }: connectedPayload) {
    // Thin adapter: Hocuspocus types `readOnly` as the `Boolean` wrapper type.
    const connection: RecheckConnection = {
      get readOnly() {
        return Boolean(connectionInstance.readOnly);
      },
      set readOnly(value: boolean) {
        connectionInstance.readOnly = value;
      },
      close: (event) => connectionInstance.close(event),
      sendStateless: (payload) => connectionInstance.sendStateless(payload),
    };
    accessRecheckScheduler.track(connection, context as HocusPocusServerContext, documentName);
  }

  async beforeHandleMessage({ context }: beforeHandleMessagePayload) {
    // Reject anything still in flight from a revoked connection (Hocuspocus closes it with code/reason).
    if (accessRecheckScheduler.isRevoked(context as HocusPocusServerContext)) {
      throw new AccessRevokedError();
    }
  }

  async onDisconnect({ context, documentName }: onDisconnectPayload) {
    accessRecheckScheduler.untrackContext(context as HocusPocusServerContext, documentName);
  }

  async afterUnloadDocument({ documentName }: afterUnloadDocumentPayload) {
    accessRecheckScheduler.forgetDocument(documentName);
  }

  async onDestroy() {
    accessRecheckScheduler.reset();
  }
}
