"use client";

import { CheckCircle, Circle, CircleNotch } from "@phosphor-icons/react";
import { ProgressBar } from "@/components/ui/ProgressBar";
import type { ComparisonSummary } from "@/lib/types";

const STAGES = [
  { key: "reading", label: "Read both versions" },
  { key: "aligning", label: "Match clauses between them" },
  { key: "rating", label: "Rate how significant each change is" },
  { key: "summarising", label: "Write the overview" },
] as const;

function stageIndex(stage: string): number {
  const index = STAGES.findIndex((entry) => entry.key === stage);
  return index === -1 ? 0 : index;
}

function fraction(comparison: ComparisonSummary): number {
  const { stage, progress_done: done, progress_total: total } = comparison;
  if (stage === "aligning") return 0.2;
  if (stage === "rating") return total ? 0.25 + 0.6 * (done / total) : 0.3;
  if (stage === "summarising") return 0.92;
  return 0.06;
}

function detail(comparison: ComparisonSummary): string {
  const { stage, progress_done: done, progress_total: total } = comparison;
  if (stage === "rating" && total) return `Rating the changes, batch ${Math.min(done + 1, total)} of ${total}`;
  return STAGES[stageIndex(stage)].label;
}

export function ComparisonProgress({ comparison }: { comparison: ComparisonSummary }) {
  const current = stageIndex(comparison.stage);
  const progress = fraction(comparison);

  return (
    <div className="mx-auto mt-10 flex w-full max-w-xl flex-col gap-8 rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight text-ink">Comparing the two versions</h1>
        <p className="truncate text-sm text-ink-muted">
          {comparison.old_document.filename} and {comparison.new_document.filename}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-end justify-between">
          <p className="text-sm text-ink-muted" role="status" aria-live="polite">
            {detail(comparison)}
          </p>
          <p className="font-mono text-2xl tabular-nums text-ink">
            {Math.round(progress * 100)}
            <span className="text-base text-ink-subtle">%</span>
          </p>
        </div>
        <ProgressBar value={progress} label="Comparison progress" />
      </div>

      <ol className="flex flex-col gap-2.5">
        {STAGES.map((stage, index) => {
          const status = index < current ? "done" : index === current ? "active" : "pending";
          return (
            <li
              key={stage.key}
              aria-current={status === "active" ? "step" : undefined}
              className={`flex items-center gap-2.5 text-sm ${status === "pending" ? "text-ink-subtle" : "text-ink"}`}
            >
              {status === "done" && <CheckCircle size={18} weight="fill" className="text-success" aria-hidden />}
              {status === "active" && (
                <CircleNotch size={18} weight="bold" className="animate-spin text-accent motion-reduce:animate-none" aria-hidden />
              )}
              {status === "pending" && <Circle size={18} className="text-line-strong" aria-hidden />}
              {stage.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
