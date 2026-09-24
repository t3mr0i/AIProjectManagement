/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { getAgeParts, getAgeSeconds } from "@plane/utils";

/** Formatting helpers bound to the current locale. */
export const useHubFormatters = () => {
  const { t, currentLocale } = useTranslation();

  const formatAge = useCallback(
    (value: string | number | Date | null | undefined): string => {
      if (value === null || value === undefined || value === 0) return t("project_hub.time.never");
      const seconds = getAgeSeconds(typeof value === "number" ? new Date(value) : value);
      if (seconds === null) return t("project_hub.time.never");
      const { value: amount, unit } = getAgeParts(seconds);
      return t(`project_hub.time.${unit}_ago`, { value: amount });
    },
    [t]
  );

  const formatDateTime = useCallback(
    (value: string | number | Date | null | undefined): string => {
      if (!value) return "—";
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) return "—";
      return new Intl.DateTimeFormat(currentLocale, { dateStyle: "medium", timeStyle: "short" }).format(date);
    },
    [currentLocale]
  );

  const formatDate = useCallback(
    (value: string | number | Date | null | undefined): string => {
      if (!value) return "—";
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) return "—";
      return new Intl.DateTimeFormat(currentLocale, { dateStyle: "medium" }).format(date);
    },
    [currentLocale]
  );

  return { formatAge, formatDateTime, formatDate };
};
