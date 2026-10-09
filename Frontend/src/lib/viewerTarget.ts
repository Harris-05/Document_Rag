import { occurrenceIndex } from "./textMatch";
import type { Citation, CitationRange, PageText } from "./types";

/** Where the document viewer should take the reader after a citation is clicked. */
export interface ViewerTarget {
  /** Changes on every navigation so the same citation can be re-opened and scrolled to again. */
  token: number;
  citationKey: string;
  /** Every place the quote occurs, in document order. */
  matches: CitationRange[][];
  /** Which of `matches` is being shown. */
  index: number;
}

/** One stretch of quoted text to find and highlight on one page. */
export interface Portion {
  page: number;
  text: string;
  /** Which repeat of this text on the page is meant (0 is the first). */
  occurrence: number;
}

export function matchesOf(citation: Citation): CitationRange[][] {
  if (citation.matches?.length > 0) return citation.matches;
  return citation.ranges?.length > 0 ? [citation.ranges] : [];
}

export function firstPageOf(target: ViewerTarget): number | null {
  return target.matches[target.index]?.[0]?.page ?? null;
}

/**
 * Turns one match into the text to look for on each page. The viewer re-finds this text in what it
 * rendered, so it only needs the words and which repeat is meant, never the server's offsets.
 */
export function portionsFor(match: CitationRange[], pages: PageText[]): Portion[] {
  const byNumber = new Map(pages.map((page) => [page.page_number, page.text]));
  const portions: Portion[] = [];
  for (const range of match) {
    const pageText = byNumber.get(range.page);
    if (pageText === undefined) continue;
    const text = pageText.slice(range.start, range.end);
    if (!text.trim()) continue;
    portions.push({ page: range.page, text, occurrence: occurrenceIndex(pageText, text, range.start) });
  }
  return portions;
}

export function portionsOnPage(portions: Portion[], page: number): Portion[] {
  return portions.filter((portion) => portion.page === page);
}

/** Stable text that changes only when the highlighted content does, for effect dependencies. */
export function portionsKey(portions: Portion[]): string {
  return portions.map((p) => `${p.page}:${p.occurrence}:${p.text.length}:${p.text.slice(0, 24)}`).join("|");
}
