"use client";

import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { useRef, useState } from "react";
import { ProductMock, type MockStep } from "./ProductMock";
import { Reveal } from "./Reveal";

const STEPS = [
  {
    title: "Upload your contract",
    body: "Drop in a PDF or Word file. Marginalia reads it, splits it into sections and keeps it in your library. Nothing to configure.",
  },
  {
    title: "Ask in plain language",
    body: "Ask what you would ask a colleague: who can terminate, what is the liability cap, what changed. Questions can span several contracts at once.",
  },
  {
    title: "Check the evidence",
    body: "Every answer quotes the clauses it relied on, and each quote is checked against the document. Click one to see it highlighted in the original.",
  },
] as const;

function StepText({ index, active }: { index: number; active: boolean }) {
  const step = STEPS[index];
  return (
    <div className={`transition-opacity duration-300 ${active ? "opacity-100" : "opacity-35"}`}>
      <p className="mb-2 flex items-center gap-3 text-sm font-medium text-ink-subtle">
        <span
          className={`grid size-7 place-items-center rounded-full border text-xs transition-colors duration-300 ${
            active ? "border-accent bg-accent text-accent-ink" : "border-line-strong"
          }`}
        >
          {index + 1}
        </span>
        Step {index + 1}
      </p>
      <h3 className="text-2xl font-semibold tracking-tight">{step.title}</h3>
      <p className="mt-2 max-w-md leading-relaxed text-ink-muted">{step.body}</p>
    </div>
  );
}

export function HowItWorks() {
  const track = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState<MockStep>(0);
  const { scrollYProgress } = useScroll({ target: track, offset: ["start start", "end end"] });

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    setStep(progress < 0.34 ? 0 : progress < 0.67 ? 1 : 2);
  });

  return (
    <section id="how-it-works" aria-labelledby="how-title" className="border-b border-line">
      {/* Wide screens: the section stays on screen while scrolling moves through the steps. */}
      <div ref={track} className="relative hidden h-[320vh] lg:block">
        <div className="sticky top-0 flex h-svh items-center">
          <div className="mx-auto grid w-full max-w-7xl grid-cols-[1fr_1.15fr] items-center gap-16 px-10">
            <div className="space-y-10">
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-ink-subtle">How it works</p>
                <h2 id="how-title" className="mt-3 text-4xl font-light uppercase leading-tight tracking-tight">
                  From file to checked answer in three steps
                </h2>
              </div>
              {STEPS.map((_, index) => (
                <StepText key={index} index={index} active={step === index} />
              ))}
              <div className="h-1 w-40 overflow-hidden rounded-full bg-line" aria-hidden>
                <motion.div className="h-full origin-left rounded-full bg-accent" style={{ scaleX: scrollYProgress }} />
              </div>
            </div>
            <ProductMock step={step} />
          </div>
        </div>
      </div>

      {/* Narrow screens: no pinning, each step shows its own picture. */}
      <div className="mx-auto w-full max-w-7xl space-y-14 px-4 py-20 sm:px-6 lg:hidden">
        <Reveal>
          <p className="text-[11px] uppercase tracking-[0.22em] text-ink-subtle">How it works</p>
          <h2 className="mt-3 text-3xl font-light uppercase leading-tight tracking-tight">
            From file to checked answer in three steps
          </h2>
        </Reveal>
        {STEPS.map((_, index) => (
          <Reveal key={index} className="space-y-6">
            <StepText index={index} active />
            <ProductMock step={index as MockStep} />
          </Reveal>
        ))}
      </div>
    </section>
  );
}
