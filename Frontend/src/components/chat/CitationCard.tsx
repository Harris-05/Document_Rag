"use client";

import { ShieldCheck, ShieldWarning } from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import type { Citation } from "@/lib/types";

interface CitationCardProps {
  id: string;
  citation: Citation;
  /** In a comparison, say which document the quote is from. */
  multi?: boolean;
  active: boolean;
  onOpen: (citation: Citation) => void;
}

export function CitationCard({ id, citation, multi = false, active, onOpen }: CitationCardProps) {
  const { verified } = citation;
  const hasQuote = citation.quote.length > 0;

  return (
    <li
      id={id}
      className={`flex gap-3 rounded-card border p-4 transition-colors duration-200 ${
        active ? "border-accent bg-accent-soft" : verified ? "border-line bg-surface" : "border-warn/40 bg-warn-soft"
      }`}
    >
      <span
        className={`grid size-6 shrink-0 place-items-center rounded-full font-mono text-xs font-medium ${
          verified ? "bg-accent-soft text-accent" : "bg-surface text-warn"
        }`}
      >
        {citation.n}
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-3">
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
          <blockquote className="border-l-2 border-line-strong pl-3 text-[14px] leading-relaxed text-ink">
            &ldquo;{citation.quote}&rdquo;
          </blockquote>
        ) : (
          <p className="text-[14px] text-ink-muted">The answer cites this number, but no quote was provided for it.</p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {verified ? (
            <p className="flex items-center gap-1.5 text-[13px] text-success">
              <ShieldCheck size={16} weight="fill" aria-hidden />
              <span className="font-medium">Verified</span>
              <span className="text-ink-subtle">
                page {citation.page}
                {citation.occurrences > 1 ? `, ${citation.occurrences} matches` : ""}
              </span>
            </p>
          ) : (
            <p className="flex items-start gap-1.5 text-[13px] text-warn">
              <ShieldWarning size={16} weight="fill" className="mt-px shrink-0" aria-hidden />
              <span>
                <span className="font-medium">
                  {multi && citation.document_name ? `Not found in ${citation.document_name}.` : "Not found in the document."}
                </span>{" "}
                <span className="text-ink-muted">The wording may have been changed, so do not rely on it.</span>
              </span>
            </p>
          )}

          {verified && (
            <Button variant="secondary" onClick={() => onOpen(citation)} className="min-h-10 px-3 text-[13px]">
              Open in document
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}
