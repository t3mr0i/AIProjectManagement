/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useRef, useState } from "react";
// plane imports
import type { TProjectHubApiError } from "@plane/types";
import { toProjectHubApiError } from "@plane/utils";
// hooks
import { useProjectHub } from "@/hooks/store/use-project-hub";

export type THubResource<T> = {
  /** Last successfully loaded value (kept when a refresh fails → stale state). */
  data: T | undefined;
  error: TProjectHubApiError | null;
  /** First load without any data yet. */
  isLoading: boolean;
  /** Any request in flight (incl. background refresh). */
  isRefreshing: boolean;
  fetchedAt: number | undefined;
  refresh: () => Promise<void>;
};

/**
 * Loads a Project Hub resource into the MobX store and exposes loading/error/stale state.
 * Must be used inside an `observer` component (reads observable store maps).
 * Invalidating the key in the store (`invalidate(prefix)`) triggers a refetch.
 */
export const useHubResource = <T>(key: string | null, fetcher: () => Promise<T>): THubResource<T> => {
  const store = useProjectHub();
  const [error, setError] = useState<TProjectHubApiError | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const fetchedAt = key ? store.fetchedAt.get(key) : undefined;
  const data = key ? store.getResource<T>(key) : undefined;

  const refresh = useCallback(async () => {
    if (!key) return;
    setIsRefreshing(true);
    try {
      await store.load(key, () => fetcherRef.current());
      setError(null);
    } catch (err) {
      setError(toProjectHubApiError(err));
    } finally {
      setIsRefreshing(false);
    }
  }, [key, store]);

  useEffect(() => {
    if (!key) return;
    setError(null);
  }, [key]);

  useEffect(() => {
    if (!key) return;
    if (fetchedAt === undefined || fetchedAt === 0) void refresh();
  }, [key, fetchedAt, refresh]);

  return {
    data,
    error,
    isLoading: !!key && data === undefined && !error,
    isRefreshing,
    fetchedAt,
    refresh,
  };
};
