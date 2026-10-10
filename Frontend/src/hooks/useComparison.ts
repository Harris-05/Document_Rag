"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getComparison } from "@/lib/api";
import type { ComparisonDetail } from "@/lib/types";

export type ComparisonState =
  | { status: "loading" }
  | { status: "ready"; comparison: ComparisonDetail }
  | { status: "missing" }
  | { status: "error"; message: string };

const POLL_INTERVAL_MS = 700;

/** Loads a comparison and keeps refreshing it while it is still being worked out. */
export function useComparison(id: string) {
  const [state, setState] = useState<ComparisonState>({ status: "loading" });

  const load = useCallback(async () => {
    try {
      setState({ status: "ready", comparison: await getComparison(id) });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) setState({ status: "missing" });
      else
        setState((current) =>
          // A failed background refresh must not throw away what is already on screen.
          current.status === "ready"
            ? current
            : { status: "error", message: error instanceof ApiError ? error.message : "Could not load this comparison." },
        );
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const processing = state.status === "ready" && state.comparison.status === "processing";
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [processing, load]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    void load();
  }, [load]);

  return { state, reload };
}
