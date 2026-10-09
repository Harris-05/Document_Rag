export interface TextRange {
  start: number;
  end: number;
}

export interface TextSegment {
  text: string;
  highlighted: boolean;
}

/** Splits text into plain and highlighted segments. Ranges are clamped, sorted and merged. */
export function splitByRanges(text: string, ranges: TextRange[]): TextSegment[] {
  const clamped = ranges
    .map((range) => ({
      start: Math.max(0, Math.min(text.length, range.start)),
      end: Math.max(0, Math.min(text.length, range.end)),
    }))
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start);

  const merged: TextRange[] = [];
  for (const range of clamped) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
  }

  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const range of merged) {
    if (range.start > cursor) segments.push({ text: text.slice(cursor, range.start), highlighted: false });
    segments.push({ text: text.slice(range.start, range.end), highlighted: true });
    cursor = range.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), highlighted: false });
  return segments.length > 0 ? segments : [{ text, highlighted: false }];
}
