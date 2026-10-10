"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError, getDocumentText } from "@/lib/api";
import type { DocumentDetail } from "@/lib/types";

export type DetailState = { status: "ready"; document: DocumentDetail } | { status: "error"; message: string };

/**
 * Fetches each document's text the first time it is needed, not all up front. A document that has
 * not been requested yet simply has no entry, which callers treat as "loading".
 */
export function useDocumentTexts() {
  const [details, setDetails] = useState<Record<string, DetailState>>({});
  const requested = useRef(new Set<string>());

  const ensureLoaded = useCallback((documentId: string) => {
    if (!documentId || requested.current.has(documentId)) return;
    requested.current.add(documentId);
    getDocumentText(documentId)
      .then((document) => setDetails((current) => ({ ...current, [documentId]: { status: "ready", document } })))
      .catch((error: unknown) =>
        setDetails((current) => ({
          ...current,
          [documentId]: {
            status: "error",
            message: error instanceof ApiError ? error.message : "Could not load this document.",
          },
        })),
      );
  }, []);

  const retry = useCallback(
    (documentId: string) => {
      requested.current.delete(documentId);
      setDetails((current) => {
        const next = { ...current };
        delete next[documentId];
        return next;
      });
      ensureLoaded(documentId);
    },
    [ensureLoaded],
  );

  return { details, ensureLoaded, retry };
}
