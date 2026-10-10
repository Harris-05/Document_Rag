"use client";

import { ArrowUpRight, ShieldCheck, ShieldWarning } from "@phosphor-icons/react";
import type { Citation } from "@/lib/types";

interface CitationCardProps {
  id: string;
  citation: Citation;
  /** In a comparison, say which document the quote is from. */
  multi?: boolean;
  active: boolean;
  onOpen: (citation: Citation) => void;
}

/** One quoted passage and whether it was found word for word in the document. A row in the sources list. */
export function CitationCard({ id, citation, multi = false, active, onOpen }: CitationCardProps) {
  const { verified } = citation;
  const hasQuote = citation.quote.length > 0;

  return (
    <li
      id={id}
      className={`flex gap-3 px-4 py-3.5 transition-colors duration-200 ${
        active ? "bg-surface-2" : verified ? "bg-surface" : "bg-danger-soft/60"
      }`}
    >
      <span
        className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full font-mono text-[11px] font-medium ${
          verified ? "bg-accent text-accent-ink" : "bg-danger text-surface"
        }`}
      >
        {citation.n}
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {multi && citation.document_name && (
          <p className="flex items-center gap-2 text-[12px] text-ink-muted">
            {citation.document_label && (
              <span className="rounded-full bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                {citation.document_label}
              </span>
            )}
            <span className="min-w-0 truncate font-medium" title={citation.document_name}>
              {citation.document_name}
            </span>
          </p>
        )}
        {hasQuote ? (
          <blockquote className="text-[14px] leading-relaxed text-ink">&ldquo;{citation.quote}&rdquo;</blockquote>
        ) : (
          <p className="text-[14px] text-ink-muted">The answer cites this number, but no quote was provided for it.</p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          {verified ? (
            <p className="flex items-center gap-1.5 text-[12px] text-ink-muted">
              <ShieldCheck size={15} weight="fill" className="text-ink" aria-hidden />
              <span className="font-medium text-ink">Verified</span>
              <span>
                page {citation.page}
                {citation.occurrences > 1 ? `, ${citation.occurrences} matches` : ""}
              </span>
            </p>
          ) : (
            <p className="flex items-start gap-1.5 text-[12px] text-danger">
              <ShieldWarning size={15} weight="fill" className="mt-px shrink-0" aria-hidden />
              <span>
                <span className="font-medium">
                  {multi && citation.document_name
                    ? `Not found in ${citation.document_name}.`
                    : "Not found in the document."}
                </span>{" "}
                <span className="text-ink-muted">The wording may have been changed, so do not rely on it.</span>
              </span>
            </p>
          )}

          {verified && (
            <button
              type="button"
              onClick={() => onOpen(citation)}
              className="-mr-2 inline-flex min-h-9 cursor-pointer items-center gap-1 rounded-full px-3 text-[12px] font-medium text-ink transition-colors hover:bg-surface-2"
            >
              Open in document
              <ArrowUpRight size={13} weight="bold" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
