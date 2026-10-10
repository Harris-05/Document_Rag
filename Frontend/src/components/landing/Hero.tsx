"use client";

import { ArrowRight, SealCheck } from "@phosphor-icons/react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useRef } from "react";
import { ChatPane, DocumentPane, useAutoplayStep } from "./ProductMock";

const EASE = [0.22, 1, 0.36, 1] as const;
/** One floating picture. It is a drawing of the app, so it is hidden from assistive technology. */
function Tile({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      aria-hidden
      className={`overflow-hidden rounded-md border border-line bg-surface text-left text-ink shadow-[0_30px_60px_-32px_rgb(0_0_0/0.3)] ${className}`}
    >
      {children}
    </div>
  );
}

export function Hero() {
  const step = useAutoplayStep();
  const reduceMotion = useReducedMotion();
  const section = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: section, offset: ["start start", "end start"] });
  // The three pictures drift upward at different speeds as the page scrolls, which gives the row its depth.
  const depth = reduceMotion ? 0 : 1;
  const slow = useTransform(scrollYProgress, [0, 1], [0, -40 * depth]);
  const medium = useTransform(scrollYProgress, [0, 1], [0, -110 * depth]);
  const fast = useTransform(scrollYProgress, [0, 1], [0, -180 * depth]);

  const fade = (delay: number) => ({
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.8, delay, ease: EASE },
  });
  const slide = (delay: number) => ({
    initial: { y: "110%" },
    animate: { y: "0%" },
    transition: { duration: 1, delay, ease: EASE },
  });

  return (
    <section ref={section} className="hero" aria-labelledby="hero-title">
      <div className="absolute inset-0 -z-10" aria-hidden>
        <div className="mist mist-a -left-[8%] -top-[30%] h-[60vw] max-h-[760px] w-[60vw] max-w-[760px]" />
        <div className="mist mist-b -right-[10%] top-[10%] h-[55vw] max-h-[700px] w-[55vw] max-w-[700px]" />
        <div className="mist mist-c bottom-[-25%] left-[20%] h-[50vw] max-h-[640px] w-[50vw] max-w-[640px]" />
        <div className="grain" />
      </div>

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-10">
        {/* The navigation is drawn by LandingNav, fixed over the top of the page; this leaves room for it. */}
        <div aria-hidden className="h-[136px]" />

        <div className="pt-14 text-center lg:pt-20">
          <h1
            id="hero-title"
            className="mx-auto max-w-6xl text-balance text-[clamp(1.5rem,4vw,3.75rem)] font-light uppercase leading-[1.08] tracking-tight"
          >
            <span className="line-mask">
              <motion.span className="block" {...slide(0.2)}>
                Ask your contracts anything.
              </motion.span>
            </span>
            <span className="line-mask">
              <motion.span className="block" {...slide(0.35)}>
                See where the answer comes from.
              </motion.span>
            </span>
          </h1>
          <motion.p
            {...fade(0.7)}
            className="mx-auto mt-7 max-w-xl text-pretty text-[15px] leading-relaxed text-ink-muted"
          >
            Upload a PDF or Word contract, ask in plain language, and get an answer with the exact clause quoted beside
            it. Click a quote to jump to it in the original.
          </motion.p>
          <motion.div {...fade(0.85)} className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/app"
              className="group inline-flex min-h-12 items-center gap-2 rounded-full bg-accent px-7 text-[12px] font-medium uppercase tracking-[0.2em] text-accent-ink transition-transform hover:scale-[1.03] active:scale-[0.98]"
            >
              Get started
              <ArrowRight
                size={16}
                weight="bold"
                className="transition-transform group-hover:translate-x-0.5"
                aria-hidden
              />
            </Link>
          </motion.div>
        </div>

        <div className="mx-auto mt-16 grid max-w-6xl items-start gap-6 pb-24 md:grid-cols-[1fr_1.05fr_0.55fr] md:gap-8 lg:mt-24 lg:pb-32">
          <motion.div style={{ y: slow }} className="md:mt-0">
            <motion.div
              initial={{ opacity: 0, y: 60 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1.1, delay: 1, ease: EASE }}
            >
              <Tile>
                <DocumentPane step={step} />
              </Tile>
            </motion.div>
          </motion.div>

          <motion.div style={{ y: fast }} className="md:mt-24">
            <motion.div
              initial={{ opacity: 0, y: 60 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1.1, delay: 1.15, ease: EASE }}
            >
              <Tile>
                <ChatPane step={step} />
              </Tile>
            </motion.div>
          </motion.div>

          <motion.div style={{ y: medium }} className="hidden md:mt-10 md:block">
            <motion.div
              initial={{ opacity: 0, y: 60 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1.1, delay: 1.3, ease: EASE }}
            >
              <Tile>
                <div className="space-y-3 p-5">
                  <SealCheck size={26} weight="fill" />
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-subtle">Citation</p>
                  <p className="text-[13px] leading-snug">§12.2, page 7</p>
                  <p className="text-[11px] leading-snug text-ink-muted">
                    Quote found in the original and checked word for word.
                  </p>
                </div>
              </Tile>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
