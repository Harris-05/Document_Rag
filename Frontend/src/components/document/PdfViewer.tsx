"use client";

import "pdfjs-dist/web/pdf_viewer.css";
import { MagnifyingGlassMinus, MagnifyingGlassPlus } from "@phosphor-icons/react";
import {
  getDocument,
  GlobalWorkerOptions,
  RenderingCancelledException,
  TextLayer,
  type PDFDocumentProxy,
} from "pdfjs-dist/legacy/build/pdf.mjs";
import { useCallback, useEffect, useRef, useState } from "react";
import { fileUrl } from "@/lib/api";
import { computeHighlights, scrollHighlightsIntoView, type HighlightRect } from "@/lib/domHighlight";
import { portionsKey, portionsOnPage, type Portion } from "@/lib/viewerTarget";
import { HighlightOverlay } from "./HighlightOverlay";

// The legacy build includes fallbacks for browsers a version or two behind (for example Chrome 138,
// which lacks Uint8Array.toHex). It costs nothing on newer browsers.
GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";

/** One shared empty list, so "no highlight" is the same value on every render. */
const NO_RECTS: HighlightRect[] = [];
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
const PAGE_PADDING = 32;
/** Pages this far outside the visible area stay rendered, so scrolling never shows a blank page. */
const RENDER_MARGIN = "1200px 0px";

export interface HighlightReport {
  found: number;
  total: number;
  /** Which citation click this report belongs to, so a stale one is never shown for a newer click. */
  token: number | null;
}

interface PdfViewerProps {
  documentId: string;
  portions: Portion[];
  /** The page to bring into view, and a token that changes on each navigation. */
  targetPage: number | null;
  targetToken: number | null;
  onHighlightReport: (report: HighlightReport | null) => void;
  onUnavailable: (message: string) => void;
}

interface PageProps {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  scale: number;
  baseSize: { w: number; h: number };
  scroller: React.RefObject<HTMLDivElement | null>;
  portions: Portion[];
  token: number | null;
  onPlaced: (token: number | null, pageNumber: number, found: number, total: number) => void;
}

function PdfPage({ pdf, pageNumber, scale, baseSize, scroller, portions, token, onPlaced }: PageProps) {
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);

  const [near, setNear] = useState(pageNumber <= 2);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [renderedScale, setRenderedScale] = useState<number | null>(null);
  const [placed, setPlaced] = useState<{ key: string; rects: HighlightRect[] } | null>(null);

  const key = `${portionsKey(portions)}@${scale}`;
  const isTargetPage = portions.length > 0;

  useEffect(() => {
    const element = wrapper.current;
    const root = scroller.current;
    if (!element || !root) return;
    const observer = new IntersectionObserver((entries) => setNear(entries.some((entry) => entry.isIntersecting)), {
      root,
      rootMargin: RENDER_MARGIN,
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [scroller]);

  useEffect(() => {
    if (!near) return;
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;
    let text: TextLayer | null = null;
    const canvasElement = canvas.current;
    const textElement = textLayer.current;
    if (!canvasElement || !textElement) return;

    (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
      const viewport = page.getViewport({ scale });
      setSize({ w: viewport.width, h: viewport.height });

      const ratio = window.devicePixelRatio || 1;
      canvasElement.width = Math.floor(viewport.width * ratio);
      canvasElement.height = Math.floor(viewport.height * ratio);
      canvasElement.style.width = `${viewport.width}px`;
      canvasElement.style.height = `${viewport.height}px`;

      textElement.replaceChildren();
      renderTask = page.render({
        canvas: canvasElement,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      });
      text = new TextLayer({ textContentSource: page.streamTextContent(), container: textElement, viewport });
      await Promise.all([renderTask.promise, text.render()]);
      if (!cancelled) setRenderedScale(scale);
    })().catch((error) => {
      if (!(error instanceof RenderingCancelledException)) console.error(`Could not render page ${pageNumber}`, error);
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
      text?.cancel();
      // Free the bitmap and text of pages that scroll far away, so a long contract stays light.
      canvasElement.width = 0;
      canvasElement.height = 0;
      textElement.replaceChildren();
      setRenderedScale(null);
    };
  }, [near, pdf, pageNumber, scale]);

  useEffect(() => {
    if (renderedScale !== scale || !isTargetPage) return;
    const text = textLayer.current;
    const frame = wrapper.current;
    if (!text || !frame) return;
    const result = computeHighlights(text, frame, portions);
    setPlaced({ key, rects: result.rects });
    onPlaced(token, pageNumber, result.found, result.total);
    // `key` already captures the portions and the scale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderedScale, scale, key, isTargetPage, pageNumber, token, onPlaced]);

  const rects = placed?.key === key && isTargetPage ? placed.rects : NO_RECTS;

  return (
    <div
      ref={wrapper}
      data-page={pageNumber}
      className="pdf-page"
      style={
        {
          width: size?.w ?? baseSize.w * scale,
          height: size?.h ?? baseSize.h * scale,
          "--scale-factor": scale,
          "--total-scale-factor": scale,
        } as React.CSSProperties
      }
    >
      <canvas ref={canvas} className="pdf-canvas" />
      <div ref={textLayer} className="textLayer" />
      <HighlightOverlay rects={rects} />
      {renderedScale !== scale && (
        <span className="pdf-page-label" aria-hidden>
          Page {pageNumber}
        </span>
      )}
    </div>
  );
}

export default function PdfViewer({
  documentId,
  portions,
  targetPage,
  targetToken,
  onHighlightReport,
  onUnavailable,
}: PdfViewerProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const handledToken = useRef<number | null>(null);
  const reports = useRef(new Map<number, { found: number; total: number }>());

  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadedFraction, setLoadedFraction] = useState<number | null>(null);
  const [width, setWidth] = useState(0);
  const [baseSize, setBaseSize] = useState({ w: 612, h: 792 });
  const [zoom, setZoom] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    const task = getDocument({
      url: fileUrl(documentId),
      cMapUrl: "/pdfjs/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdfjs/standard_fonts/",
      wasmUrl: "/pdfjs/wasm/",
      iccUrl: "/pdfjs/iccs/",
    });
    task.onProgress = ({ loaded, total }: { loaded: number; total?: number }) => {
      if (total) setLoadedFraction(loaded / total);
    };
    task.promise
      .then(async (document) => {
        const first = await document.getPage(1);
        const viewport = first.getViewport({ scale: 1 });
        if (cancelled) return;
        setBaseSize({ w: viewport.width, h: viewport.height });
        setPdf(document);
        setLoading(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        console.error("Could not open the PDF in the viewer", error);
        const name = error instanceof Error ? error.name : "";
        onUnavailable(
          name === "PasswordException"
            ? "This PDF is password protected, so it cannot be shown here."
            : "The original file could not be displayed. The extracted text is still available.",
        );
        setLoading(false);
      });
    return () => {
      cancelled = true;
      void task.destroy();
    };
  }, [documentId, onUnavailable]);

  useEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const fit = width > 0 ? Math.max(0.3, (width - PAGE_PADDING) / baseSize.w) : 1;
  const scale = fit * zoom;

  // Bring the cited page into view. The page renders as it arrives, and its highlight then scrolls
  // itself to the middle of the screen.
  useEffect(() => {
    if (!pdf || targetToken === null || targetPage === null || handledToken.current === targetToken) return;
    handledToken.current = targetToken;
    const root = scroller.current;
    const pageElement = root?.querySelector<HTMLElement>(`[data-page="${targetPage}"]`);
    if (root && pageElement) {
      root.scrollTo({ top: root.scrollTop + pageElement.getBoundingClientRect().top - root.getBoundingClientRect().top - 8 });
    }
  }, [pdf, targetPage, targetToken]);

  const scrolledFor = useRef<number | null>(null);
  const reportsToken = useRef<number | null>(null);
  // Set once every part of the current quote has been drawn. Scrolling happens in an effect, after
  // React has committed the highlight bars to the page, so they can be measured.
  const [allPlacedFor, setAllPlacedFor] = useState<number | null>(null);

  const scrollOnce = useCallback(() => {
    const root = scroller.current;
    if (!root || targetToken === null || scrolledFor.current === targetToken) return;
    if (scrollHighlightsIntoView(root)) scrolledFor.current = targetToken;
  }, [targetToken]);

  const expectedParts = portions.length;
  const handlePlaced = useCallback(
    (token: number | null, pageNumber: number, found: number, total: number) => {
      if (token === null) return;
      // Each citation click starts a fresh tally, so an earlier quote's results never linger.
      if (reportsToken.current !== token) {
        reports.current.clear();
        reportsToken.current = token;
      }
      reports.current.set(pageNumber, { found, total });
      let foundAll = 0;
      let totalAll = 0;
      reports.current.forEach((value) => {
        foundAll += value.found;
        totalAll += value.total;
      });
      onHighlightReport({ found: foundAll, total: totalAll, token });
      // Only when every page's part is in, so a quote across a page break is centred as a whole.
      if (expectedParts > 0 && foundAll === expectedParts) setAllPlacedFor(token);
    },
    [onHighlightReport, expectedParts],
  );

  useEffect(() => {
    if (allPlacedFor !== null && allPlacedFor === targetToken) scrollOnce();
  }, [allPlacedFor, targetToken, scrollOnce]);

  // If some part of the quote can never be placed, still scroll to what was.
  useEffect(() => {
    if (targetToken === null) return;
    const timer = setTimeout(scrollOnce, 2500);
    return () => clearTimeout(timer);
  }, [targetToken, scrollOnce]);

  const handleScroll = useCallback(() => {
    const element = scroller.current;
    if (!element) return;
    const pages = element.querySelectorAll<HTMLElement>("[data-page]");
    const limit = element.getBoundingClientRect().top + element.clientHeight * 0.3;
    let current = 1;
    for (const page of pages) {
      if (page.getBoundingClientRect().top <= limit) current = Number(page.dataset.page);
      else break;
    }
    setCurrentPage(current);
  }, []);

  const changeZoom = (delta: number) => setZoom((value) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value + delta)));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2 text-[13px] text-ink-muted sm:px-6">
        <p className="font-mono tabular-nums" aria-live="polite">
          {pdf ? `Page ${currentPage} of ${pdf.numPages}` : "Loading"}
        </p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => changeZoom(-ZOOM_STEP)}
            disabled={zoom <= MIN_ZOOM}
            aria-label="Zoom out"
            className="grid size-9 cursor-pointer place-items-center rounded-ctl hover:bg-surface-2 disabled:pointer-events-none disabled:opacity-40"
          >
            <MagnifyingGlassMinus size={18} aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            aria-label="Reset zoom to fit width"
            className="min-w-14 cursor-pointer rounded-ctl px-2 py-1.5 font-mono text-xs tabular-nums hover:bg-surface-2"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            onClick={() => changeZoom(ZOOM_STEP)}
            disabled={zoom >= MAX_ZOOM}
            aria-label="Zoom in"
            className="grid size-9 cursor-pointer place-items-center rounded-ctl hover:bg-surface-2 disabled:pointer-events-none disabled:opacity-40"
          >
            <MagnifyingGlassPlus size={18} aria-hidden />
          </button>
        </div>
      </div>

      <div ref={scroller} onScroll={handleScroll} className="pdf-scroller min-h-0 flex-1 overflow-auto">
        {loading && (
          <div role="status" className="flex flex-col items-center gap-3 py-16 text-sm text-ink-subtle">
            <span className="skeleton h-3.5 w-48 rounded-full" />
            {loadedFraction !== null ? `Loading document, ${Math.round(loadedFraction * 100)}%` : "Loading document"}
          </div>
        )}
        {pdf && (
          <div className="pdf-pages" style={{ minWidth: baseSize.w * scale + PAGE_PADDING }}>
            {Array.from({ length: pdf.numPages }, (_, index) => {
              const pageNumber = index + 1;
              return (
                <PdfPage
                  key={pageNumber}
                  pdf={pdf}
                  pageNumber={pageNumber}
                  scale={scale}
                  baseSize={baseSize}
                  scroller={scroller}
                  portions={portionsOnPage(portions, pageNumber)}
                  token={targetToken}
                  onPlaced={handlePlaced}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
