"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * Reveals streamed text at a steady pace. Providers often deliver text in uneven bursts, which makes
 * an answer appear to jump in all at once. This drains whatever has arrived a few characters per
 * frame, speeding up as the backlog grows so the display never falls noticeably behind the stream.
 *
 * Finished messages and people who ask for reduced motion see the full text immediately.
 */
export function useSmoothedText(target: string, live: boolean): string {
  const reduceMotion = useReducedMotion();
  const [count, setCount] = useState(0);
  const targetLength = useRef(target.length);

  useEffect(() => {
    targetLength.current = target.length;
  }, [target.length]);

  useEffect(() => {
    if (!live || reduceMotion) return;
    let frame = 0;
    const tick = () => {
      setCount((current) => {
        const backlog = targetLength.current - current;
        // Bails out of re-rendering when there is nothing new to show.
        return backlog <= 0 ? current : current + Math.max(2, Math.ceil(backlog / 10));
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [live, reduceMotion]);

  return live && !reduceMotion ? target.slice(0, count) : target;
}
