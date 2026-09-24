/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { setToast } from "@plane/blocks/toast";
import { getProjectHubErrorMessageKey, toProjectHubApiError } from "@plane/utils";

type TTranslate = (key: string, params?: Record<string, unknown>) => string;

/** Error toast naming the concrete contract error (never "Something went wrong" only). */
export const showHubErrorToast = (t: TTranslate, error: unknown) => {
  const err = toProjectHubApiError(error);
  setToast({
    type: "error",
    title: t(getProjectHubErrorMessageKey(err)),
    message: err.error || undefined,
  });
};

export const showHubSuccessToast = (title: string) => {
  setToast({ type: "success", title });
};
