"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, deleteDocument, listDocuments } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";

type LoadStatus = "loading" | "ready" | "error";

const POLL_INTERVAL_MS = 800;

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
      setStatus("ready");
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load your library.");
      // Keep showing the last good list if a background refresh fails.
      setStatus((current) => (current === "ready" ? "ready" : "error"));
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load on mount
    void refresh();
  }, [refresh]);

  const hasProcessing = documents.some((document) => document.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, refresh]);

  const remove = useCallback(
    async (id: string): Promise<string | null> => {
      const previous = documents;
      setDocuments((current) => current.filter((document) => document.id !== id));
      try {
        await deleteDocument(id);
        return null;
      } catch (caught) {
        // 404 means it is already gone, which is the outcome the user asked for.
        if (caught instanceof ApiError && caught.status === 404) return null;
        setDocuments(previous);
        return caught instanceof ApiError ? caught.message : "Could not delete this document.";
      }
    },
    [documents],
  );

  return { documents, status, error, refresh, remove };
}
