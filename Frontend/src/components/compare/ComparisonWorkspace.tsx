"use client";

import { ArrowLeft, ArrowsLeftRight, FileText, ListChecks } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { DocumentTabs } from "@/components/document/DocumentTabs";
import { DocumentViewer } from "@/components/document/DocumentViewer";
import { Notice, WorkspaceSkeleton } from "@/components/document/DocumentWorkspace";
import { Button, LinkButton } from "@/components/ui/Button";
import { useComparison } from "@/hooks/useComparison";
import { useDocumentTexts } from "@/hooks/useDocumentTexts";
import { ApiError, createComparison } from "@/lib/api";
import {
  categoriesIn,
  countBySignificance,
  defaultFilters,
  filterChanges,
  sortChanges,
  type ChangeFilters,
  type SortMode,
} from "@/lib/changes";
import type { Change, ComparisonDetail } from "@/lib/types";
import type { ViewerTarget } from "@/lib/viewerTarget";
import { ChangeCard } from "./ChangeCard";
import { ChangeFilterBar } from "./ChangeFilters";
import { ComparisonProgress } from "./ComparisonProgress";
import { SummaryCard } from "./SummaryCard";

type MobileView = "changes" | "document";

export function ComparisonWorkspace({ id }: { id: string }) {
  const router = useRouter();
  const { state, reload } = useComparison(id);
  const [retrying, startRetry] = useTransition();
  const [retryError, setRetryError] = useState<string | null>(null);

  if (state.status === "loading") return <WorkspaceSkeleton />;
  if (state.status === "missing") {
    return (
      <Notice
        title="Comparison not found"
        message="It may have been deleted, or one of its documents may have been removed."
        action={<LinkButton href="/">Back to library</LinkButton>}
      />
    );
  }
  if (state.status === "error") {
    return (
      <Notice title="Couldn't load this comparison" message={state.message} action={<Button onClick={reload}>Try again</Button>} />
    );
  }

  const { comparison } = state;
  if (comparison.status === "processing") return <ComparisonProgress comparison={comparison} />;

  if (comparison.status === "failed") {
    const runAgain = async () => {
      setRetryError(null);
      try {
        const next = await createComparison(comparison.old_document.id, comparison.new_document.id);
        startRetry(() => router.push(`/comparisons/${next.id}`));
      } catch (error) {
        setRetryError(error instanceof ApiError ? error.message : "Could not start the comparison again.");
      }
    };
    return (
      <Notice
        title="This comparison could not be completed"
        message={`${comparison.error_message ?? "Something went wrong."}${retryError ? ` ${retryError}` : ""}`}
        action={
          <div className="flex flex-wrap gap-3">
            <Button onClick={runAgain} disabled={retrying}>
              {retrying ? "Starting" : "Run it again"}
            </Button>
            <LinkButton href="/" variant="secondary">
              Back to library
            </LinkButton>
          </div>
        }
      />
    );
  }

  return <Review comparison={comparison} />;
}

function Review({ comparison }: { comparison: ComparisonDetail }) {
  const router = useRouter();
  const [filters, setFilters] = useState<ChangeFilters>(defaultFilters);
  const [sort, setSort] = useState<SortMode>("significance");
  const [view, setView] = useState<MobileView>("changes");
  const [activeChangeId, setActiveChangeId] = useState<number | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState(comparison.old_document.id);
  const [target, setTarget] = useState<ViewerTarget | null>(null);
  const { details, ensureLoaded, retry } = useDocumentTexts();
  const [swapping, startSwap] = useTransition();
  const [swapError, setSwapError] = useState<string | null>(null);

  const counts = useMemo(() => countBySignificance(comparison.changes), [comparison.changes]);
  const categories = useMemo(() => categoriesIn(comparison.changes), [comparison.changes]);
  const visible = useMemo(
    () => sortChanges(filterChanges(comparison.changes, filters), sort),
    [comparison.changes, filters, sort],
  );

  useEffect(() => {
    ensureLoaded(activeDocumentId);
  }, [activeDocumentId, ensureLoaded]);

  const viewSide = useCallback(
    (change: Change, side: "old" | "new") => {
      const data = side === "old" ? change.old : change.new;
      if (!data) return;
      const documentId = side === "old" ? comparison.old_document.id : comparison.new_document.id;
      setActiveChangeId(change.id);
      setActiveDocumentId(documentId);
      setTarget((previous) => ({
        token: (previous?.token ?? 0) + 1,
        citationKey: `change:${change.id}:${side}`,
        documentId,
        matches: [data.ranges],
        index: 0,
      }));
      setView("document");
    },
    [comparison.old_document.id, comparison.new_document.id],
  );

  const swap = async () => {
    setSwapError(null);
    try {
      const next = await createComparison(comparison.new_document.id, comparison.old_document.id);
      startSwap(() => router.push(`/comparisons/${next.id}`));
    } catch (error) {
      setSwapError(error instanceof ApiError ? error.message : "Could not swap the versions.");
    }
  };

  const detail = details[activeDocumentId];
  const paneBase = "min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-line bg-surface shadow-card lg:flex";
  const nothingChanged = comparison.changes.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link
          href="/"
          className="-ml-2 flex min-h-11 items-center gap-2 rounded-ctl px-2 text-sm text-ink-muted transition-colors hover:text-ink"
        >
          <ArrowLeft size={16} aria-hidden />
          Library
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold tracking-tight text-ink">What changed between the versions</h1>
          <p className="truncate text-xs text-ink-subtle">
            Old: {comparison.old_document.filename}. New: {comparison.new_document.filename}.
          </p>
        </div>
        <Button variant="secondary" onClick={swap} disabled={swapping} className="min-h-10 px-3 text-[13px]">
          <ArrowsLeftRight size={16} aria-hidden />
          {swapping ? "Swapping" : "Swap old and new"}
        </Button>

        <div role="tablist" aria-label="Switch view" className="flex rounded-ctl bg-surface-2 p-1 lg:hidden">
          {(
            [
              ["changes", "Changes", ListChecks],
              ["document", "Documents", FileText],
            ] as const
          ).map(([key, label, TabIcon]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-[7px] px-3.5 text-sm font-medium transition-colors ${
                view === key ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              <TabIcon size={16} aria-hidden />
              {label}
            </button>
          ))}
        </div>
      </div>
      {swapError && (
        <p role="alert" className="text-[13px] text-danger">
          {swapError}
        </p>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <section aria-label="Changes" className={`${paneBase} ${view === "changes" ? "flex" : "hidden"}`}>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="flex flex-col gap-6 px-4 pt-5 sm:px-6">
              <SummaryCard comparison={comparison} />
            </div>

            {nothingChanged ? (
              <div className="flex flex-col items-start gap-2 px-4 py-8 sm:px-6">
                <h2 className="text-[15px] font-medium text-ink">No differences found</h2>
                <p className="max-w-[48ch] text-sm leading-relaxed text-ink-muted">
                  Every clause in the old version appears in the new one with the same wording. Differences in
                  numbering, capitalisation or punctuation are not counted.
                </p>
              </div>
            ) : (
              <>
                <div className="sticky top-0 z-10 mt-5 border-y border-line bg-surface px-4 py-3 sm:px-6">
                  <ChangeFilterBar
                    filters={filters}
                    onFilters={setFilters}
                    sort={sort}
                    onSort={setSort}
                    counts={counts}
                    categories={categories}
                    shown={visible.length}
                    total={comparison.changes.length}
                  />
                </div>
                {visible.length === 0 ? (
                  <div className="flex flex-col items-start gap-3 px-4 py-8 sm:px-6">
                    <h2 className="text-[15px] font-medium text-ink">No changes match these filters</h2>
                    <Button variant="secondary" onClick={() => setFilters(defaultFilters())}>
                      Clear filters
                    </Button>
                  </div>
                ) : (
                  <ol aria-label="Changes" className="flex flex-col gap-4 px-4 py-5 sm:px-6">
                    {visible.map((change) => (
                      <ChangeCard key={change.id} change={change} active={change.id === activeChangeId} onView={viewSide} />
                    ))}
                  </ol>
                )}
              </>
            )}
          </div>
        </section>

        <section aria-label="Documents" className={`${paneBase} ${view === "document" ? "flex" : "hidden"}`}>
          <DocumentTabs
            ariaLabel="Versions"
            tabs={[
              { id: comparison.old_document.id, label: comparison.old_document.filename, badge: "Old" },
              { id: comparison.new_document.id, label: comparison.new_document.filename, badge: "New" },
            ]}
            activeId={activeDocumentId}
            onSelect={setActiveDocumentId}
          />
          {detail === undefined && (
            <div role="status" aria-label="Loading document" className="flex flex-1 flex-col items-center gap-3 px-6 py-10">
              {[100, 92, 96, 70].map((width, index) => (
                <span key={index} className="skeleton h-3.5 rounded-full" style={{ width: `${width}%`, maxWidth: 520 }} />
              ))}
            </div>
          )}
          {detail?.status === "error" && (
            <div role="alert" className="flex flex-col items-start gap-3 p-6">
              <p className="text-[15px] text-ink">{detail.message}</p>
              <Button variant="secondary" onClick={() => retry(activeDocumentId)}>
                Try again
              </Button>
            </div>
          )}
          {detail?.status === "ready" && (
            <DocumentViewer
              key={detail.document.id}
              document={detail.document}
              target={target?.documentId === activeDocumentId ? target : null}
              onStepMatch={() => undefined}
            />
          )}
        </section>
      </div>
    </div>
  );
}
