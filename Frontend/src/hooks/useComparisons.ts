"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, deleteComparison, listComparisons } from "@/lib/api";
import type { ComparisonSummary } from "@/lib/types";

/** Saved comparisons of two versions, so they can be reopened. */
export function useComparisons() {
  const [comparisons, setComparisons] = useState<ComparisonSummary[]>([]);

  const refresh = useCallback(async () => {
    try {
      setComparisons(await listComparisons());
    } catch {
      // The list is a convenience. If it cannot load, the rest of the page still works.
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load on mount
    void refresh();
  }, [refresh]);

  const remove = useCallback(
    async (id: string): Promise<string | null> => {
      const previous = comparisons;
      setComparisons((current) => current.filter((comparison) => comparison.id !== id));
      try {
        await deleteComparison(id);
        return null;
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) return null;
        setComparisons(previous);
        return caught instanceof ApiError ? caught.message : "Could not delete this comparison.";
      }
    },
    [comparisons],
  );

  return { comparisons, refresh, remove };
}
