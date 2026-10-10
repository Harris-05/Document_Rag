"use client";

import { ArrowRight } from "@phosphor-icons/react";
import { motion, useMotionValueEvent, useScroll } from "motion/react";
import Link from "next/link";
import { useState } from "react";

/** Scroll distance at which the navigation shrinks into a pill, and the shorter distance at which it grows back. */
const COMPACT_AFTER_PX = 64;
const EXPAND_BEFORE_PX = 24;

/*
 * Corner radius and shadow are animated through Motion, not set with CSS classes. While the nav changes
 * size it is stretched by a transform, and Motion only counter-stretches these two when it owns them;
 * otherwise the shadow smears into a grey patch and the corners wobble.
 */
const SHADOW_ON = "0px 12px 40px -12px rgba(0, 0, 0, 0.25)";
const SHADOW_OFF = "0px 12px 40px -12px rgba(0, 0, 0, 0)";
const SPRING = { type: "spring", stiffness: 220, damping: 28, mass: 0.9 } as const;

/** The contents appear in their new place a moment after the box starts to change, so nothing slides through anything else. */
const SETTLE = { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.28, delay: 0.1 } } as const;

const TEXT_LINK =
  "hidden min-h-11 items-center px-3 text-[11px] uppercase tracking-[0.22em] text-ink-muted transition-colors hover:text-ink sm:inline-flex";

/**
 * One navigation that changes shape as the page scrolls. At the top it is the open, centred bar: the
 * wordmark above a row of links. Once you scroll, the same box eases into a single-row pill that floats
 * over the page. The box resizes continuously; its contents fade in at their new positions.
 */
export function LandingNav() {
  const { scrollY } = useScroll();
  const [compact, setCompact] = useState(false);
  const shape = compact ? "pill" : "bar";

  // Two different thresholds, so hovering around one scroll position cannot make it flicker.
  useMotionValueEvent(scrollY, "change", (y) => {
    setCompact((current) => (y > COMPACT_AFTER_PX ? true : y < EXPAND_BEFORE_PX ? false : current));
  });

  return (
    <motion.div
      className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center px-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, paddingTop: compact ? 16 : 28 }}
      transition={{ opacity: { duration: 0.8, delay: 0.1 }, paddingTop: SPRING }}
    >
      <motion.nav
        layout
        aria-label="Main"
        transition={SPRING}
        initial={false}
        style={{ borderRadius: 0, boxShadow: SHADOW_OFF }}
        animate={{ borderRadius: compact ? 32 : 0, boxShadow: compact ? SHADOW_ON : SHADOW_OFF }}
        className={`pointer-events-auto flex border will-change-transform transition-[background-color,border-color] duration-500 ${
          compact
            ? "flex-row items-center gap-1 border-line bg-surface/95 py-1.5 pl-5 pr-1.5"
            : "flex-col items-center gap-1 border-line/0 bg-surface/0"
        }`}
      >
        <motion.div key={`brand-${shape}`} {...SETTLE}>
          <Link
            href="/"
            className={`inline-flex min-h-11 items-center text-[12px] font-medium uppercase tracking-[0.35em] text-ink ${
              compact ? "mr-2" : ""
            }`}
            aria-label="Marginalia home"
          >
            Marginalia
          </Link>
        </motion.div>

        <motion.div key={`links-${shape}`} {...SETTLE} className="flex items-center gap-1 sm:gap-3">
          <a href="#how-it-works" className={TEXT_LINK}>
            How it works
          </a>
          <a href="#who-its-for" className={TEXT_LINK}>
            Who it&apos;s for
          </a>
          <Link
            href="/app"
            className={`group inline-flex min-h-11 items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] active:scale-[0.97] ${
              compact
                ? "rounded-full bg-accent px-5 text-accent-ink"
                : "rounded-none border-b border-ink px-1 text-ink"
            }`}
          >
            {compact ? "Open app" : "Open the app"}
            {compact && (
              <ArrowRight
                size={14}
                weight="bold"
                className="transition-transform group-hover:translate-x-0.5"
                aria-hidden
              />
            )}
          </Link>
        </motion.div>
      </motion.nav>
    </motion.div>
  );
}
