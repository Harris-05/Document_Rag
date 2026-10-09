"use client";

import { CloudSlash, FolderOpen } from "@phosphor-icons/react";
import { AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/Button";
import { MAX_COMPARE, MIN_COMPARE } from "@/lib/selection";
import type { DocumentSummary } from "@/lib/types";
import { DocumentRow } from "./DocumentRow";

interface LibraryPanelProps {
  documents: DocumentSummary[];
  status: "loading" | "ready" | "error";
  error: string | null;
  onRetry: () => void;
  onDelete: (id: string) => Promise<string | null>;
  /** Ids chosen for a comparison, in the order they were chosen. */
  selected: string[];
  onToggleSelected: (id: string) => void;
  onClearSelection: () => void;
  onCompare: () => void;
  comparing: boolean;
  compareError: string | null;
}

function LibrarySkeleton() {
  return (
    <ul aria-hidden className="divide-y divide-line">
      {[0, 1, 2].map((row) => (
        <li key={row} className="flex items-center gap-3 px-5 py-4">
          <span className="skeleton size-10 rounded-ctl" />
          <span className="flex flex-1 flex-col gap-2">
            <span className="skeleton h-3.5 w-2/3 rounded-full" />
            <span className="skeleton h-3 w-1/2 rounded-full" />
          </span>
        </li>
      ))}
    </ul>
  );
}

function EmptyLibrary() {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span className="grid size-12 place-items-center rounded-card bg-surface-2 text-ink-subtle">
        <FolderOpen size={24} weight="duotone" aria-hidden />
      </span>
      <h3 className="text-[15px] font-medium text-ink">Your library is empty</h3>
      <p className="max-w-[32ch] text-sm leading-relaxed text-ink-muted">
        Documents you upload are saved here, so you can open them again later.
      </p>
    </div>
  );
}

function LibraryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-card bg-danger-soft text-danger">
        <CloudSlash size={24} weight="duotone" aria-hidden />
      </span>
      <h3 className="text-[15px] font-medium text-ink">Couldn&apos;t load your library</h3>
      <p className="max-w-[36ch] text-sm leading-relaxed text-ink-muted">{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

export function LibraryPanel({
  documents,
  status,
  error,
  onRetry,
  onDelete,
  selected,
  onToggleSelected,
  onClearSelection,
  onCompare,
  comparing,
  compareError,
}: LibraryPanelProps) {
  return (
    <section aria-labelledby="library-heading" className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 id="library-heading" className="text-lg font-semibold tracking-tight text-ink">
          Library
        </h2>
        {status === "ready" && documents.length > 0 && (
          <p className="font-mono text-sm tabular-nums text-ink-subtle">
            {documents.length} {documents.length === 1 ? "document" : "documents"}
          </p>
        )}
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {status === "loading" && <LibrarySkeleton />}
        {status === "error" && (
          <LibraryError message={error ?? "Something went wrong."} onRetry={onRetry} />
        )}
        {status === "ready" && documents.length === 0 && <EmptyLibrary />}
        {status === "ready" && documents.length > 0 && (
          <ul className="max-h-[34rem] divide-y divide-line overflow-y-auto">
            <AnimatePresence initial={false}>
              {documents.map((document) => (
                <DocumentRow
                  key={document.id}
                  document={document}
                  onDelete={onDelete}
                  selectedAs={selected.includes(document.id) ? selected.indexOf(document.id) + 1 : null}
                  selectionFull={selected.length >= MAX_COMPARE}
                  onToggleSelected={onToggleSelected}
                />
              ))}
            </AnimatePresence>
          </ul>
        )}
        {selected.length > 0 && (
          <div className="flex flex-col gap-2 border-t border-line bg-surface-2 px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-[13px] text-ink-muted" aria-live="polite">
                <span className="font-mono tabular-nums text-ink">{selected.length}</span> of {MAX_COMPARE} selected
                {selected.length < MIN_COMPARE && ", choose at least 2 to compare"}
              </p>
              <div className="flex items-center gap-2">
                <Button variant="ghost" onClick={onClearSelection} disabled={comparing} className="min-h-10 px-3 text-[13px]">
                  Clear
                </Button>
                <Button onClick={onCompare} disabled={selected.length < MIN_COMPARE || comparing} className="min-h-10 px-4 text-[13px]">
                  {comparing ? "Opening" : selected.length >= MIN_COMPARE ? `Compare ${selected.length} documents` : "Compare"}
                </Button>
              </div>
            </div>
            {compareError && (
              <p role="alert" className="text-[13px] text-danger">
                {compareError}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
