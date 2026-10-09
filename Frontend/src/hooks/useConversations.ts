"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, deleteConversation, listConversations } from "@/lib/api";
import type { Conversation } from "@/lib/types";

/** Saved comparisons across several documents, so they can be reopened. */
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch {
      // The list is a convenience. If it cannot load, the rest of the page still works.
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load on mount
    void refresh();
  }, [refresh]);

  const remove = useCallback(
    async (id: string): Promise<string | null> => {
      const previous = conversations;
      setConversations((current) => current.filter((conversation) => conversation.id !== id));
      try {
        await deleteConversation(id);
        return null;
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) return null;
        setConversations(previous);
        return caught instanceof ApiError ? caught.message : "Could not delete this comparison.";
      }
    },
    [conversations],
  );

  return { conversations, loaded, refresh, remove };
}
