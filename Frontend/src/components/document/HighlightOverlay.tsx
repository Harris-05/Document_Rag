import type { HighlightRect } from "@/lib/domHighlight";

/** Translucent bars drawn over the rendered page where the quoted text sits. */
export function HighlightOverlay({ rects }: { rects: HighlightRect[] }) {
  return (
    <>
      {rects.map((rect, index) => (
        <div
          key={index}
          aria-hidden
          data-highlight
          data-first={index === 0 ? "" : undefined}
          className="cite-overlay"
          style={{ left: rect.left - 2, top: rect.top - 1, width: rect.width + 4, height: rect.height + 2 }}
        />
      ))}
    </>
  );
}
