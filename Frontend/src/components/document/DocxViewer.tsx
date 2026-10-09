"use client";

import { renderAsync } from "docx-preview";
import { useEffect, useRef, useState } from "react";
import { fileUrl } from "@/lib/api";
import { computeHighlights, scrollHighlightsIntoView, type HighlightRect } from "@/lib/domHighlight";
import { portionsKey, type Portion } from "@/lib/viewerTarget";
import type { HighlightReport } from "./PdfViewer";
import { HighlightOverlay } from "./HighlightOverlay";

/** One shared empty list, so "no highlight" is the same value on every render. */
const NO_RECTS: HighlightRect[] = [];
const SIDE_PADDING = 32;
const MIN_FIT = 0.4;

interface DocxViewerProps {
  documentId: string;
  portions: Portion[];
  targetToken: number | null;
  onHighlightReport: (report: HighlightReport | null) => void;
  onUnavailable: (message: string) => void;
}

export default function DocxViewer({
  documentId,
  portions,
  targetToken,
  onHighlightReport,
  onUnavailable,
}: DocxViewerProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const scrolledFor = useRef<number | null>(null);

  const [ready, setReady] = useState(false);
  const [fit, setFit] = useState(1);
  const [placed, setPlaced] = useState<{ key: string; rects: HighlightRect[] } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const target = content.current;
    if (!target) return;

    (async () => {
      const response = await fetch(fileUrl(documentId));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      if (cancelled) return;
      target.replaceChildren();
      await renderAsync(blob, target, undefined, {
        className: "docx",
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: true,
        breakPages: true,
        renderHeaders: true,
        renderFooters: true,
        renderFootnotes: true,
      });
      if (!cancelled) setReady(true);
    })().catch((error: unknown) => {
      console.error("Could not open the Word file in the viewer", error);
      if (!cancelled) onUnavailable("The original Word file could not be displayed. The extracted text is still available.");
    });

    return () => {
      cancelled = true;
      target.replaceChildren();
      setReady(false);
    };
  }, [documentId, onUnavailable]);

  // Shrink wide Word pages to the width of the pane, the way the PDF view fits to width.
  useEffect(() => {
    const frame = scroller.current;
    const root = content.current;
    if (!ready || !frame || !root) return;

    const update = () => {
      const page = root.querySelector<HTMLElement>("section.docx");
      if (!page) return;
      setFit((current) => {
        const naturalWidth = page.getBoundingClientRect().width / current;
        const next = Math.min(1, Math.max(MIN_FIT, (frame.clientWidth - SIDE_PADDING) / naturalWidth));
        return Math.abs(next - current) < 0.005 ? current : next;
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [ready]);

  const key = `${portionsKey(portions)}@${fit.toFixed(3)}`;
  const active = portions.length > 0;

  useEffect(() => {
    if (!ready || !active) return;
    const root = content.current;
    if (!root) return;
    // Wait a frame so the new zoom has been laid out before positions are measured.
    const frame = requestAnimationFrame(() => {
      const result = computeHighlights(root, root, portions);
      setPlaced({ key, rects: result.rects });
      onHighlightReport({ found: result.found, total: result.total, token: targetToken });
    });
    return () => cancelAnimationFrame(frame);
    // `key` already captures the portions and the zoom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, key, active, onHighlightReport, targetToken]);

  useEffect(() => {
    if (!active) onHighlightReport(null);
  }, [active, onHighlightReport]);

  const rects = placed?.key === key && active ? placed.rects : NO_RECTS;

  useEffect(() => {
    const root = scroller.current;
    if (!root || rects.length === 0 || targetToken === null || scrolledFor.current === targetToken) return;
    scrolledFor.current = targetToken;
    scrollHighlightsIntoView(root);
  }, [rects, targetToken]);

  return (
    <div ref={scroller} className="docx-scroller min-h-0 flex-1 overflow-auto">
      {!ready && (
        <p role="status" className="py-16 text-center text-sm text-ink-subtle">
          Loading document
        </p>
      )}
      <div className="docx-frame">
        <div ref={content} className="docx-content" style={{ zoom: fit }} />
        <HighlightOverlay rects={rects} />
      </div>
    </div>
  );
}
