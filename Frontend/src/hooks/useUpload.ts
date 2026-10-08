"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, getDocument, uploadDocument } from "@/lib/api";
import type { DocumentSummary, ErrorCode, UserFacingError } from "@/lib/types";
import { validateFile } from "@/lib/validation";

export interface FileInfo {
  name: string;
  size: number;
}

export type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; file: FileInfo; fraction: number }
  | { phase: "processing"; file: FileInfo; document: DocumentSummary }
  | { phase: "done"; file: FileInfo; document: DocumentSummary }
  | { phase: "error"; file: FileInfo | null; error: UserFacingError };

type Action =
  | { type: "start"; file: FileInfo }
  | { type: "uploadProgress"; fraction: number }
  | { type: "processing"; document: DocumentSummary }
  | { type: "done"; document: DocumentSummary }
  | { type: "fail"; file: FileInfo | null; error: UserFacingError }
  | { type: "reset" };

function reducer(state: UploadState, action: Action): UploadState {
  switch (action.type) {
    case "start":
      return { phase: "uploading", file: action.file, fraction: 0 };
    case "uploadProgress":
      return state.phase === "uploading" ? { ...state, fraction: action.fraction } : state;
    case "processing":
      if (state.phase === "idle" || state.phase === "error") return state;
      return { phase: "processing", file: state.file, document: action.document };
    case "done":
      if (state.phase === "idle" || state.phase === "error") return state;
      return { phase: "done", file: state.file, document: action.document };
    case "fail":
      return { phase: "error", file: action.file, error: action.error };
    case "reset":
      return { phase: "idle" };
  }
}

const POLL_INTERVAL_MS = 350;
const MAX_CONSECUTIVE_POLL_FAILURES = 5;

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}

export function useUpload(onSettled: () => void) {
  const [state, dispatch] = useReducer(reducer, { phase: "idle" } as UploadState);
  const controller = useRef<AbortController | null>(null);
  const onSettledRef = useRef(onSettled);

  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    const file = files[0];
    const info: FileInfo = { name: file.name, size: file.size };

    if (files.length > 1) {
      dispatch({
        type: "fail",
        file: null,
        error: { code: "UNKNOWN", message: "Upload one file at a time." },
      });
      return;
    }
    const invalid = validateFile(file);
    if (invalid) {
      dispatch({ type: "fail", file: info, error: invalid });
      return;
    }

    controller.current?.abort();
    const run = new AbortController();
    controller.current = run;
    dispatch({ type: "start", file: info });

    try {
      let document = await uploadDocument(
        file,
        (fraction) => dispatch({ type: "uploadProgress", fraction }),
        run.signal,
      );
      dispatch({ type: "processing", document });

      let failures = 0;
      while (!run.signal.aborted && document.status === "processing") {
        await wait(POLL_INTERVAL_MS, run.signal);
        if (run.signal.aborted) return;
        try {
          document = await getDocument(document.id);
          failures = 0;
          dispatch({ type: "processing", document });
        } catch (error) {
          failures += 1;
          if (failures >= MAX_CONSECUTIVE_POLL_FAILURES) throw error;
        }
      }
      if (run.signal.aborted) return;

      if (document.status === "failed") {
        dispatch({
          type: "fail",
          file: info,
          error: {
            code: (document.error_code as ErrorCode | null) ?? "UNKNOWN",
            message: document.error_message ?? "This document could not be processed.",
          },
        });
      } else {
        dispatch({ type: "done", document });
      }
      onSettledRef.current();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      dispatch({
        type: "fail",
        file: info,
        error:
          error instanceof ApiError
            ? error.toUserFacing()
            : { code: "UNKNOWN", message: "Something went wrong during the upload." },
      });
      onSettledRef.current();
    }
  }, []);

  const cancel = useCallback(() => {
    controller.current?.abort();
    dispatch({ type: "reset" });
  }, []);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  return { state, start, cancel, reset };
}

/** Overall completion from 0 to 1, weighted across the three stages the user sees. */
export function overallProgress(state: UploadState): number {
  switch (state.phase) {
    case "uploading":
      return state.fraction * 0.2;
    case "processing": {
      const { stage, progress_done, progress_total } = state.document;
      if (stage === "saving") return 0.97;
      if (progress_total && progress_total > 0) return 0.2 + 0.75 * (progress_done / progress_total);
      return 0.55;
    }
    case "done":
      return 1;
    default:
      return 0;
  }
}
