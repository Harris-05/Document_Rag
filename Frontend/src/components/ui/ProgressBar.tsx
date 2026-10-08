"use client";

import { motion, useReducedMotion } from "motion/react";

interface ProgressBarProps {
  /** Completion from 0 to 1. */
  value: number;
  label: string;
  tone?: "accent" | "success";
}

/** Animates transform only (scaleX), never width, so progress updates stay on the compositor. */
export function ProgressBar({ value, label, tone = "accent" }: ProgressBarProps) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.min(1, Math.max(0, value));

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped * 100)}
      className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
    >
      <motion.div
        className={`h-full origin-left rounded-full ${tone === "success" ? "bg-success" : "bg-accent"}`}
        initial={false}
        animate={{ scaleX: clamped }}
        transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 140, damping: 24 }}
      />
    </div>
  );
}
