"use client";

import { GitDiff, Trash } from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { SIGNIFICANCE_LABEL } from "@/lib/changes";
import { formatRelativeTime } from "@/lib/format";
import type { ComparisonSummary } from "@/lib/types";

interface ComparisonListProps {
  comparisons: ComparisonSummary[];
  onDelete: (id: string) => Promise<string | null>;
}

function describe(comparison: ComparisonSummary): string {
  if (comparison.status === "processing") return "Comparing now";
  const stats = comparison.stats;
  if (!stats) return "";
  const changed = stats.modified + stats.added + stats.removed + stats.moved;
  if (changed === 0) return "No differences";
  const critical = stats.by_significance.critical ?? 0;
  const major = stats.by_significance.major ?? 0;
  const parts = [`${changed} ${changed === 1 ? "change" : "changes"}`];
  if (critical > 0) parts.push(`${critical} ${SIGNIFICANCE_LABEL.critical.toLowerCase()}`);
  if (major > 0) parts.push(`${major} ${SIGNIFICANCE_LABEL.major.toLowerCase()}`);
  return parts.join(", ");
}

function Row({ comparison, onDelete }: { comparison: ComparisonSummary; onDelete: ComparisonListProps["onDelete"] }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const title = `${comparison.old_document.filename} and ${comparison.new_document.filename}`;

  const confirmDelete = async () => {
    setBusy(true);
    const failure = await onDelete(comparison.id);
    if (failure) {
      setError(failure);
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:px-5">
      <div className="flex items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-ctl bg-accent-soft text-accent">
          <GitDiff size={18} weight="duotone" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <Link
            href={`/comparisons/${comparison.id}`}
            className="block truncate rounded-ctl text-[14px] font-medium text-ink hover:text-accent"
            title={title}
          >
            {title}
          </Link>
          <p className="flex flex-wrap gap-x-3 text-[12px] text-ink-subtle">
            <span>{describe(comparison)}</span>
            <span>{formatRelativeTime(comparison.created_at)}</span>
          </p>
        </div>
        {!confirming && (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setConfirming(true);
            }}
            aria-label={`Delete the comparison of ${title}`}
            className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-ctl text-ink-subtle transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <Trash size={18} aria-hidden />
          </button>
        )}
      </div>

      {confirming && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-ctl bg-danger-soft px-3 py-2">
          <p className="text-sm text-ink">Delete this comparison? The documents stay.</p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
              Keep
            </Button>
            <Button variant="danger" onClick={confirmDelete} disabled={busy}>
              {busy ? "Deleting" : "Delete"}
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function ComparisonList({ comparisons, onDelete }: ComparisonListProps) {
  if (comparisons.length === 0) return null;
  return (
    <section aria-labelledby="version-comparisons-heading" className="flex flex-col gap-3">
      <h2 id="version-comparisons-heading" className="text-lg font-semibold tracking-tight text-ink">
        Version comparisons
      </h2>
      <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {comparisons.map((comparison) => (
          <Row key={comparison.id} comparison={comparison} onDelete={onDelete} />
        ))}
      </ul>
    </section>
  );
}
