"use client";

import { FilePdf, Quotes, SealCheck } from "@phosphor-icons/react";
import { useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/** 0 = a contract is uploaded, 1 = a question is asked, 2 = the cited answer is shown. */
export type MockStep = 0 | 1 | 2;

const QUESTION = "Can either party terminate for convenience?";
const CLAUSE = "Either party may terminate this Agreement for convenience on ninety (90) days' written notice.";

function Typed({ text }: { text: string }) {
  const reduceMotion = useReducedMotion();
  const [count, setCount] = useState(0);

  // The first render is the same for everyone (so it matches the server's); reduced motion jumps to the full text after.
  useEffect(() => {
    if (reduceMotion) {
      const timer = setTimeout(() => setCount(text.length), 0);
      return () => clearTimeout(timer);
    }
    const timer = setInterval(() => setCount((value) => Math.min(value + 1, text.length)), 38);
    return () => clearInterval(timer);
  }, [reduceMotion, text]);

  return (
    <>
      {text.slice(0, count)}
      {count < text.length && <span className="caret ml-px inline-block h-4 w-px translate-y-0.5 bg-accent-ink" />}
    </>
  );
}

function Lines({ widths }: { widths: string[] }) {
  return (
    <div className="space-y-2">
      {widths.map((width, index) => (
        <div key={index} className="h-2 rounded-full bg-line" style={{ width }} />
      ))}
    </div>
  );
}

/** The contract side of the picture: a page of text with the cited sentence highlighted once it is found. */
export function DocumentPane({ step }: { step: MockStep }) {
  return (
    <div className="space-y-4 bg-surface p-5">
      <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
        <FilePdf size={14} /> Master Services Agreement.pdf
      </p>
      <Lines widths={["92%", "100%", "78%"]} />
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">12. Term and termination</p>
      <p className="text-[13px] leading-relaxed text-ink-muted">
        12.1 This Agreement begins on the Effective Date and continues for an initial term of two years.
      </p>
      <p className="text-[13px] leading-relaxed text-ink-muted">
        12.2 <span className={step === 2 ? "mock-mark text-ink" : ""}>{CLAUSE}</span>
      </p>
      <Lines widths={["100%", "86%", "94%", "60%"]} />
    </div>
  );
}

/** The conversation side of the picture: the question typing in, then the answer with its quoted evidence. */
export function ChatPane({ step }: { step: MockStep }) {
  return (
    <div className="flex min-h-[270px] flex-col gap-3 bg-surface p-5">
      {step === 0 && (
        <div className="my-auto space-y-2 text-center">
          <SealCheck size={28} className="mx-auto" weight="fill" />
          <p className="text-sm font-medium">Contract ready</p>
          <p className="text-xs text-ink-subtle">Ask a question in plain language.</p>
        </div>
      )}
      {step >= 1 && (
        <>
          <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-[13px] text-accent-ink">
            {step === 1 ? <Typed text={QUESTION} /> : QUESTION}
          </div>
          {step === 2 && (
            <div className="space-y-3 rounded-2xl rounded-bl-md border border-line bg-surface px-3.5 py-3">
              <p className="text-[13px] leading-relaxed">
                Yes. Either party may end the agreement without cause by giving{" "}
                <strong>90 days&apos; written notice</strong>.
              </p>
              <div className="flex items-start gap-2 rounded-ctl border border-line bg-surface-2 p-2.5">
                <Quotes size={14} weight="fill" className="mt-0.5 shrink-0" />
                <div className="text-[11px] leading-snug text-ink-muted">
                  <span className="font-semibold text-ink">§12.2, page 7.</span> &ldquo;{CLAUSE}&rdquo;
                </div>
              </div>
              <p className="flex items-center gap-1.5 text-[11px] font-medium text-ink-muted">
                <SealCheck size={13} weight="fill" /> Every quote checked against the document
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * A drawn imitation of the app: a contract on the left, a conversation on the right. It is a picture,
 * not a working screen, so it is hidden from assistive technology.
 */
export function ProductMock({ step }: { step: MockStep }) {
  return (
    <div
      aria-hidden
      className="overflow-hidden rounded-card border border-line bg-surface text-left text-ink shadow-[0_30px_60px_-30px_rgb(0_0_0/0.25)]"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="size-2.5 rounded-full bg-line-strong" />
        <span className="ml-3 flex items-center gap-1.5 text-xs text-ink-subtle">
          <FilePdf size={14} /> Master Services Agreement.pdf
        </span>
      </div>
      <div className="grid min-h-[340px] sm:grid-cols-[1.1fr_1fr]">
        <div className="border-b border-line bg-surface-2/60 sm:border-b-0 sm:border-r">
          <DocumentPane step={step} />
        </div>
        <ChatPane step={step} />
      </div>
    </div>
  );
}

/**
 * Plays the three steps in a loop. People who prefer less motion get the finished answer instead; that is
 * set after the page loads, so the first render matches the server's.
 */
export function useAutoplayStep(): MockStep {
  const reduceMotion = useReducedMotion();
  const [step, setStep] = useState<MockStep>(0);

  useEffect(() => {
    const hold: Record<MockStep, number> = { 0: 1400, 1: 2800, 2: 5000 };
    const timer = reduceMotion
      ? setTimeout(() => setStep(2), 0)
      : setTimeout(() => setStep((current) => ((current + 1) % 3) as MockStep), hold[step]);
    return () => clearTimeout(timer);
  }, [step, reduceMotion]);

  return step;
}
