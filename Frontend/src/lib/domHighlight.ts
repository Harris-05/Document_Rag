import { locate } from "./textMatch";
import type { Portion } from "./viewerTarget";

export interface HighlightRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface HighlightResult {
  rects: HighlightRect[];
  /** How many of the requested portions were located in the rendered text. */
  found: number;
  total: number;
}

export function collectTextNodes(root: Element): Text[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if ((node as Text).data.length > 0) nodes.push(node as Text);
  }
  return nodes;
}

/** Joins the boxes of one line into a single bar, so a highlight is a few clean strips not many slivers. */
function mergeLine(rects: HighlightRect[]): HighlightRect[] {
  const sorted = [...rects].sort((a, b) => a.top - b.top || a.left - b.left);
  const merged: HighlightRect[] = [];
  for (const rect of sorted) {
    const last = merged[merged.length - 1];
    const sameLine = last && Math.abs(rect.top - last.top) < Math.max(3, last.height * 0.4);
    if (last && sameLine && rect.left <= last.left + last.width + 6) {
      const right = Math.max(last.left + last.width, rect.left + rect.width);
      const bottom = Math.max(last.top + last.height, rect.top + rect.height);
      last.top = Math.min(last.top, rect.top);
      last.height = bottom - last.top;
      last.width = right - last.left;
    } else {
      merged.push({ ...rect });
    }
  }
  return merged;
}

/**
 * Finds each portion in the text rendered under `textRoot` and returns where it sits, in pixels,
 * relative to `coordinateRoot` (the positioned element the highlight overlays are drawn inside).
 */
export function computeHighlights(
  textRoot: Element,
  coordinateRoot: Element,
  portions: Portion[],
): HighlightResult {
  const nodes = collectTextNodes(textRoot);
  const segments = nodes.map((node) => node.data);
  const origin = coordinateRoot.getBoundingClientRect();
  const rects: HighlightRect[] = [];
  let found = 0;

  for (const portion of portions) {
    const located = locate(segments, portion.text, portion.occurrence);
    if (!located) continue;
    const { start, end } = located.span;
    const startNode = nodes[start.segment];
    const endNode = nodes[end.segment];
    if (!startNode || !endNode) continue;

    const range = document.createRange();
    range.setStart(startNode, start.offset);
    range.setEnd(endNode, end.offset);
    const boxes = Array.from(range.getClientRects())
      .filter((box) => box.width > 1 && box.height > 1)
      .map((box) => ({
        left: box.left - origin.left,
        top: box.top - origin.top,
        width: box.width,
        height: box.height,
      }));
    if (boxes.length === 0) continue;
    found += 1;
    rects.push(...mergeLine(boxes));
  }

  return { rects, found, total: portions.length };
}

/**
 * Scrolls the viewer (and only the viewer, never the surrounding page) so the highlight is in view.
 * When a quote spans pages, the whole span is centred if it fits on screen; otherwise its start is.
 */
export function scrollHighlightsIntoView(scroller: HTMLElement, behavior: ScrollBehavior = "smooth"): boolean {
  const bars = Array.from(scroller.querySelectorAll<HTMLElement>("[data-highlight]"));
  if (bars.length === 0) return false;

  const boxes = bars.map((bar) => bar.getBoundingClientRect());
  const spanTop = Math.min(...boxes.map((box) => box.top));
  const spanBottom = Math.max(...boxes.map((box) => box.bottom));
  const fits = spanBottom - spanTop <= scroller.clientHeight * 0.85;
  const target = fits ? (spanTop + spanBottom) / 2 : (boxes[0].top + boxes[0].bottom) / 2;

  const view = scroller.getBoundingClientRect();
  scroller.scrollBy({ top: target - (view.top + scroller.clientHeight / 2), behavior });
  return true;
}
