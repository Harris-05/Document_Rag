"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/**
 * Applies the visitor's "reduce motion" setting to every animation on the page: movement is dropped
 * and only gentle fades remain. Done here, in one place, so the server and the browser render the same HTML.
 */
export function LandingMotion({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
