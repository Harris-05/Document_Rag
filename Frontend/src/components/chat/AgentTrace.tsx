"use client";

import {
  ArrowsClockwise,
  CaretDown,
  CheckCircle,
  CircleNotch,
  Database,
  Lightbulb,
  MagnifyingGlass,
  PencilLine,
  Quotes,
  Scales,
  ShieldCheck,
  Wrench,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";
import { useState } from "react";
import type { TraceStep } from "@/lib/types";

const STEP_ICONS: Record<string, Icon> = {
  index: Database,
  understand: Lightbulb,
  search: MagnifyingGlass,
  grade: Scales,
  refine: ArrowsClockwise,
  answer: PencilLine,
  quotes: Quotes,
  verify: ShieldCheck,
  tool: Wrench,
  limit: WarningCircle,
};

function StepIcon({ step, active }: { step: TraceStep; active: boolean }) {
  if (active) {
    return (
      <CircleNotch
        size={16}
        weight="bold"
        className="animate-spin text-accent motion-reduce:animate-none"
        aria-hidden
      />
    );
  }
  if (step.kind === "tool_result") {
    return step.detail?.ok === false ? (
      <WarningCircle size={16} weight="fill" className="text-warn" aria-hidden />
    ) : (
      <CheckCircle size={16} weight="fill" className="text-success" aria-hidden />
    );
  }
  if (step.kind === "limit") {
    return <WarningCircle size={16} weight="fill" className="text-warn" aria-hidden />;
  }
  if (step.kind === "quality") {
    const sufficient = step.detail?.sufficient === true;
    return sufficient ? (
      <CheckCircle size={16} weight="fill" className="text-success" aria-hidden />
    ) : (
      <WarningCircle size={16} weight="fill" className="text-warn" aria-hidden />
    );
  }
  const Glyph = STEP_ICONS[step.kind] ?? Lightbulb;
  return <Glyph size={16} className="text-ink-subtle" aria-hidden />;
}

interface AgentTraceProps {
  steps: TraceStep[];
  /** True while the agent is still working and no answer text has arrived yet. */
  working: boolean;
}

export function AgentTrace({ steps, working }: AgentTraceProps) {
  const [expanded, setExpanded] = useState(false);
  if (steps.length === 0) return null;

  const open = working || expanded;
  const rounds = Math.max(0, ...steps.map((step) => step.round ?? 0));
  const toolCalls = steps.filter((step) => step.kind === "tool").length;
  const last = steps[steps.length - 1];
  // Between a result coming back and the next call, the model is deciding what to do next.
  const decidingNext = working && last.kind === "tool_result";

  return (
    <div className="flex flex-col gap-2">
      {!working && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="flex min-h-9 w-fit cursor-pointer items-center gap-1.5 rounded-ctl text-[13px] text-ink-subtle transition-colors hover:text-ink"
        >
          <CaretDown
            size={14}
            className={`transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            aria-hidden
          />
          How this was answered
          <span className="font-mono tabular-nums">
            {toolCalls > 0
              ? `${toolCalls} lookup${toolCalls === 1 ? "" : "s"}, ${rounds} round${rounds === 1 ? "" : "s"}`
              : `${steps.length} steps${rounds > 1 ? `, ${rounds} search rounds` : ""}`}
          </span>
        </button>
      )}

      {open && (
        <ol className="flex flex-col gap-2 border-l border-line pl-4" aria-label="Steps taken to answer">
          {steps.map((step, index) => {
            const active = working && index === steps.length - 1 && step.kind !== "tool_result";
            const isResult = step.kind === "tool_result";
            return (
              <li
                key={index}
                className={`flex items-start gap-2.5 text-[13px] leading-snug ${isResult ? "ml-6" : ""}`}
              >
                <span className="mt-px shrink-0">
                  <StepIcon step={step} active={active} />
                </span>
                <span className={active ? "text-ink" : "text-ink-muted"}>
                  {step.text}
                  {step.round && step.round > 1 && step.kind !== "tool_result" && (
                    <span className="ml-2 font-mono text-xs text-ink-subtle">round {step.round}</span>
                  )}
                </span>
              </li>
            );
          })}
          {decidingNext && (
            <li className="flex items-start gap-2.5 text-[13px] leading-snug">
              <span className="mt-px shrink-0">
                <StepIcon step={{ kind: "understand", round: null, text: "", detail: null }} active />
              </span>
              <span className="text-ink">Deciding what to look up next</span>
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
