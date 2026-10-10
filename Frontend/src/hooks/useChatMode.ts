"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { ChatMode } from "@/lib/types";

const STORAGE_KEY = "marginalia:chat-mode";
const listeners = new Set<() => void>();
// Used when the browser blocks storage, so the choice still holds until the page is closed.
let memoryMode: ChatMode = "standard";

function read(): ChatMode {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "standard" || value === "research") return value;
  } catch {
    // Storage blocked: fall back to the in-memory choice.
  }
  return memoryMode;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/**
 * The answering mode the reader last chose, remembered per browser. Rendered as "standard" on the
 * server and in the first client render, then switches to the remembered value without a mismatch.
 */
export function useChatMode(): [ChatMode, (mode: ChatMode) => void] {
  const mode = useSyncExternalStore(subscribe, read, () => "standard" as ChatMode);
  const setMode = useCallback((next: ChatMode) => {
    memoryMode = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not remembered across visits, which only means the next visit starts in Standard.
    }
    listeners.forEach((listener) => listener());
  }, []);
  return [mode, setMode];
}
