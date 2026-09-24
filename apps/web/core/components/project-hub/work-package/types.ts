/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Scope passed down the work package area. `issueId` is the native Plane issue id (workItemId). */
export type TWorkPackageScope = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  /** Native read-only situation (archived issue / no edit permission). */
  readOnly: boolean;
};
