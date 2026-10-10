import { Info, Sparkle } from "@phosphor-icons/react/dist/ssr";
import { formatCount } from "@/lib/format";
import { SIGNIFICANCE_LABEL, SIGNIFICANCE_ORDER } from "@/lib/changes";
import type { ComparisonDetail } from "@/lib/types";

function plural(count: number, word: string): string {
  return `${formatCount(count)} ${word}${count === 1 ? "" : "s"}`;
}

/** What a reader needs first: how much changed, and in plain language what mattered. */
export function SummaryCard({ comparison }: { comparison: ComparisonDetail }) {
  const stats = comparison.stats;
  if (!stats) return null;
  const total = comparison.changes.length;
  const substantive = SIGNIFICANCE_ORDER.filter((level) => level !== "cosmetic" && level !== "minor")
    .map((level) => [level, stats.by_significance[level] ?? 0] as const)
    .filter(([, count]) => count > 0);

  const headline =
    comparison.summary?.headline ||
    (total === 0
      ? "The two versions have identical wording."
      : `${plural(total, "clause")} changed. ` +
        (substantive.length > 0
          ? substantive.map(([level, count]) => `${count} ${SIGNIFICANCE_LABEL[level].toLowerCase()}`).join(", ") + "."
          : "None of them is rated major or critical."));

  return (
    <section aria-label="Overview" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold leading-snug tracking-tight text-ink">{headline}</h2>
        {comparison.summary && comparison.summary.key_points.length > 0 && (
          <ul className="flex flex-col gap-2">
            {comparison.summary.key_points.map((point, index) => (
              <li key={index} className="flex gap-2.5 text-[14px] leading-relaxed text-ink-muted">
                <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        )}
        {comparison.summary && (
          <p className="flex items-center gap-1.5 text-[12px] text-ink-subtle">
            <Sparkle size={13} weight="fill" aria-hidden />
            Written by AI from the changes below. Check it against the clauses.
          </p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
        {[
          ["Unchanged", stats.unchanged],
          ["Modified", stats.modified],
          ["Added", stats.added],
          ["Removed", stats.removed],
          ["Moved", stats.moved],
        ].map(([label, value]) => (
          <div key={label} className="flex flex-col gap-0.5">
            <dt className="text-xs text-ink-subtle">{label}</dt>
            <dd className="font-mono text-xl tabular-nums text-ink">{formatCount(Number(value))}</dd>
          </div>
        ))}
      </dl>

      {comparison.ai_notice && (
        <p role="note" className="flex items-start gap-2 rounded-ctl bg-warn-soft px-3 py-2.5 text-[13px] leading-relaxed text-warn">
          <Info size={16} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          {comparison.ai_notice}
        </p>
      )}
    </section>
  );
}
