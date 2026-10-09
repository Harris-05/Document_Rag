"use client";

import { Warning } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import { formatCount } from "@/lib/format";
import { splitByRanges } from "@/lib/highlight";
import type { CitationRange, DocumentDetail } from "@/lib/types";

export interface Highlight {
  ranges: CitationRange[];
  /** Changes on every click so the same citation can be re-opened and re-scrolled to. */
  token: number;
}

interface DocumentPaneProps {
  document: DocumentDetail;
  highlight: Highlight | null;
}

export function DocumentPane({ document, highlight }: DocumentPaneProps) {
  const showPageLabels = document.file_kind === "pdf";
  const container = useRef<HTMLDivElement>(null);
  const token = highlight?.token;

  useEffect(() => {
    if (token === undefined || !container.current) return;
    const root = container.current;
    const firstPage = root.querySelector<HTMLElement>("[data-has-highlight]");
    // Scroll the page into view first: pages far off screen skip rendering until reached.
    firstPage?.scrollIntoView({ block: "start" });
    const frame = requestAnimationFrame(() => {
      root.querySelector<HTMLElement>("mark[data-first]")?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [token]);

  return (
    <div ref={container} className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
      {document.empty_page_count > 0 && (
        <p
          role="note"
          className="mb-4 flex items-start gap-2 rounded-ctl bg-warn-soft px-4 py-3 text-sm leading-relaxed text-warn"
        >
          <Warning size={18} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          {document.empty_page_count === 1
            ? "1 page in this PDF had no readable text and may be a scan. It is shown as empty."
            : `${formatCount(document.empty_page_count)} pages in this PDF had no readable text and may be scans. They are shown as empty.`}
        </p>
      )}

      <article aria-label="Extracted text" className="flex flex-col gap-4">
        {document.pages.map((page) => {
          const ranges = highlight?.ranges.filter((range) => range.page === page.page_number) ?? [];
          const segments = splitByRanges(page.text, ranges);
          const firstHighlighted = segments.findIndex((segment) => segment.highlighted);
          const isFirstPageWithHighlight =
            highlight !== null &&
            ranges.length > 0 &&
            page.page_number === Math.min(...highlight.ranges.map((range) => range.page));

          return (
            <section
              key={page.page_number}
              id={`page-${page.page_number}`}
              data-has-highlight={isFirstPageWithHighlight ? "" : undefined}
              className="page-block rounded-card border border-line bg-surface p-5 sm:p-6"
            >
              {showPageLabels && (
                <p className="mb-3 font-mono text-xs tabular-nums text-ink-subtle">Page {page.page_number}</p>
              )}
              {page.text ? (
                <p className="whitespace-pre-wrap text-[15px] leading-7 text-ink">
                  {segments.map((segment, index) =>
                    segment.highlighted ? (
                      <mark
                        key={index}
                        data-first={isFirstPageWithHighlight && index === firstHighlighted ? "" : undefined}
                        className="cite-mark"
                      >
                        {segment.text}
                      </mark>
                    ) : (
                      <span key={index}>{segment.text}</span>
                    ),
                  )}
                </p>
              ) : (
                <p className="text-sm italic text-ink-subtle">No readable text on this page.</p>
              )}
            </section>
          );
        })}
      </article>
    </div>
  );
}
