/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
// types
import type { IProjectHubStore } from "@/store/project-hub";

export const useProjectHub = (): IProjectHubStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useProjectHub must be used within StoreProvider");
  return context.projectHub;
};
