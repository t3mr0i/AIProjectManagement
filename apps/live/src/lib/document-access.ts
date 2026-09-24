/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { classifyAccessError } from "@/lib/access-recheck";
import type { AccessCheckResult } from "@/lib/access-recheck";
import { getPageService } from "@/services/page/handler";
import type { HocusPocusServerContext } from "@/types";

/**
 * Check whether the user behind `context.cookie` may still access the document by fetching it
 * from the API with that cookie (the same permission path the API enforces for the page).
 * 401/403/404 → "revoked"; anything else that fails → "error" (transient).
 */
export const checkDocumentAccess = async (
  context: HocusPocusServerContext,
  documentName: string
): Promise<AccessCheckResult> => {
  try {
    const service = getPageService(context.documentType, context);
    await service.fetchDetails(documentName);
    return "granted";
  } catch (error) {
    return classifyAccessError(error);
  }
};
