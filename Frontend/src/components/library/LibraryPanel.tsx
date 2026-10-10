"use client";

import { CloudSlash, FolderOpen, MagnifyingGlass } from "@phosphor-icons/react";
import { useState } from "react";
import { AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/Button";
import { MAX_COMPARE, MIN_COMPARE } from "@/lib/selection";
import type { DocumentSummary } from "@/lib/types";
import { DocumentRow } from "./DocumentRow";
import { EmptyState } from "./EmptyState";

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
  /** Start a question across the selected documents. */
  onCompare: () => void;
  comparing: boolean;
  /** Show what changed between two versions (exactly two selected). */
  onShowChanges: () => void;
  showingChanges: boolean;
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
  onShowChanges,
  showingChanges,
  compareError,
}: LibraryPanelProps) {
  const busy = comparing || showingChanges;
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = needle ? documents.filter((document) => document.filename.toLowerCase().includes(needle)) : documents;

  return (
    <section aria-label="Documents">
      {status === "ready" && documents.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
          <label className="relative block w-full sm:w-72">
            <span className="sr-only">Search your documents</span>
            <MagnifyingGlass
              size={16}
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by file name"
              className="min-h-10 w-full rounded-full border border-line-strong bg-surface pl-9 pr-4 text-sm text-ink placeholder:text-ink-subtle"
            />
          </label>
          <p className="text-xs text-ink-subtle" aria-live="polite">
            {needle
              ? `${shown.length} of ${documents.length} documents`
              : `${documents.length} ${documents.length === 1 ? "document" : "documents"}. Tick two or more to compare.`}
          </p>
        </div>
      )}

      {status === "loading" && <LibrarySkeleton />}
      {status === "error" && <LibraryError message={error ?? "Something went wrong."} onRetry={onRetry} />}
      {status === "ready" && documents.length === 0 && (
        <EmptyState
          icon={FolderOpen}
          title="Your library is empty"
          body="Documents you upload are saved here, so you can open them again later."
        />
      )}
      {status === "ready" && documents.length > 0 && shown.length === 0 && (
        <EmptyState
          icon={MagnifyingGlass}
          title="No matching documents"
          body={`Nothing in your library matches “${query.trim()}”.`}
        />
      )}
      {status === "ready" && shown.length > 0 && (
        <ul className="max-h-[36rem] divide-y divide-line overflow-y-auto">
          <AnimatePresence initial={false}>
            {shown.map((document) => (
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
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="ghost" onClick={onClearSelection} disabled={busy} className="min-h-10 px-3 text-[13px]">
                Clear
              </Button>
              {selected.length === MIN_COMPARE && (
                <Button
                  variant="secondary"
                  onClick={onShowChanges}
                  disabled={busy}
                  className="min-h-10 px-3 text-[13px]"
                >
                  {showingChanges ? "Comparing" : "See what changed"}
                </Button>
              )}
              <Button
                onClick={onCompare}
                disabled={selected.length < MIN_COMPARE || busy}
                className="min-h-10 px-4 text-[13px]"
              >
                {comparing
                  ? "Opening"
                  : selected.length >= MIN_COMPARE
                    ? `Ask across ${selected.length} documents`
                    : "Ask across documents"}
              </Button>
            </div>
          </div>
          {selected.length === MIN_COMPARE && (
            <p className="text-xs leading-relaxed text-ink-subtle">
              To see what changed, the first document you selected is treated as the older version.
            </p>
          )}
          {compareError && (
            <p role="alert" className="text-[13px] text-danger">
              {compareError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
