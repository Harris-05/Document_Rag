"use client";

import { Info } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import type { DocumentDetail } from "@/lib/types";
import { portionsFor, type ViewerTarget } from "@/lib/viewerTarget";
import { DocumentPane } from "./DocumentPane";
import { MatchNavigator } from "./MatchNavigator";
import type { HighlightReport } from "./PdfViewer";

function ViewerLoading() {
  return (
    <div aria-hidden className="flex flex-1 flex-col items-center gap-3 px-6 py-10">
      {[100, 92, 96, 70].map((width, index) => (
        <span key={index} className="skeleton h-3.5 rounded-full" style={{ width: `${width}%`, maxWidth: 520 }} />
      ))}
    </div>
  );
}

// The viewers use browser-only APIs, so they are loaded on the client when first needed.
const PdfViewer = dynamic(() => import("./PdfViewer"), { ssr: false, loading: ViewerLoading });
const DocxViewer = dynamic(() => import("./DocxViewer"), { ssr: false, loading: ViewerLoading });

type View = "original" | "text";

interface DocumentViewerProps {
  document: DocumentDetail;
  target: ViewerTarget | null;
  onStepMatch: (delta: number) => void;
}

export function DocumentViewer({ document, target, onStepMatch }: DocumentViewerProps) {
  const [view, setView] = useState<View>("original");
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [report, setReport] = useState<HighlightReport | null>(null);

  const currentMatch = target?.matches[target.index] ?? null;
  const portions = useMemo(
    () => (currentMatch ? portionsFor(currentMatch, document.pages) : []),
    [currentMatch, document.pages],
  );
  const targetPage = portions[0]?.page ?? null;

  const handleUnavailable = useCallback((message: string) => {
    setUnavailable(message);
    setView("text");
  }, []);

  const showingOriginal = view === "original" && unavailable === null;
  const couldNotPlace =
    showingOriginal && report !== null && report.token === (target?.token ?? null) && report.found < report.total;

  const viewerProps = {
    documentId: document.id,
    portions,
    targetToken: target?.token ?? null,
    onHighlightReport: setReport,
    onUnavailable: handleUnavailable,
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2 sm:px-6">
        <div role="tablist" aria-label="Document view" className="flex rounded-ctl bg-surface-2 p-1">
          {(
            [
              ["original", "Original"],
              ["text", "Extracted text"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              disabled={key === "original" && unavailable !== null}
              onClick={() => setView(key)}
              className={`min-h-9 cursor-pointer rounded-[7px] px-3 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                view === key ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {target && <MatchNavigator index={target.index} count={target.matches.length} onStep={onStepMatch} />}
      </div>

      {unavailable && (
        <p role="note" className="flex items-start gap-2 bg-warn-soft px-4 py-2.5 text-[13px] leading-relaxed text-warn sm:px-6">
          <Info size={16} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          {unavailable}
        </p>
      )}

      {couldNotPlace && (
        <p role="note" className="flex flex-wrap items-start gap-x-2 gap-y-1 bg-warn-soft px-4 py-2.5 text-[13px] leading-relaxed text-warn sm:px-6">
          <Info size={16} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          <span>
            The quote is verified, but it could not be located on the rendered page
            {report && report.total > 1 ? ` (${report.found} of ${report.total} parts placed)` : ""}.
          </span>
          <button type="button" onClick={() => setView("text")} className="cursor-pointer font-medium underline underline-offset-2">
            Show it in the extracted text
          </button>
        </p>
      )}

      {showingOriginal && document.file_kind === "pdf" && (
        <PdfViewer {...viewerProps} targetPage={targetPage} />
      )}
      {showingOriginal && document.file_kind === "docx" && <DocxViewer {...viewerProps} />}
      {!showingOriginal && (
        <DocumentPane
          document={document}
          highlight={target && currentMatch ? { ranges: currentMatch, token: target.token } : null}
        />
      )}
    </div>
  );
}
