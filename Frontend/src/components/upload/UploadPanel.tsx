"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { UploadState } from "@/hooks/useUpload";
import { Dropzone } from "./Dropzone";
import { ProgressView } from "./ProgressView";
import { ErrorView, SuccessView } from "./ResultViews";

interface UploadPanelProps {
  state: UploadState;
  onFiles: (files: File[]) => void;
  onCancel: () => void;
  onReset: () => void;
}

export function UploadPanel({ state, onFiles, onCancel, onReset }: UploadPanelProps) {
  const reduceMotion = useReducedMotion();
  // Uploading and processing share one view so the progress bar never remounts between them.
  const viewKey = state.phase === "uploading" || state.phase === "processing" ? "progress" : state.phase;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={viewKey}
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      >
        {state.phase === "idle" && <Dropzone onFiles={onFiles} />}
        {(state.phase === "uploading" || state.phase === "processing") && (
          <ProgressView state={state} onCancel={onCancel} />
        )}
        {state.phase === "done" && (
          <SuccessView file={state.file} document={state.document} onReset={onReset} />
        )}
        {state.phase === "error" && <ErrorView file={state.file} error={state.error} onRetry={onReset} />}
      </motion.div>
    </AnimatePresence>
  );
}
