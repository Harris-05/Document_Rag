/**
 * Finding a quote inside the text a viewer actually rendered.
 *
 * The server verified the quote against its own extraction of the file. A viewer (pdf.js, a DOCX
 * renderer) produces the same words but in different pieces: line breaks, spacing between spans and
 * reading order can all differ. So instead of trusting offsets from one to the other, the quote is
 * located again in the rendered text, ignoring whitespace entirely.
 *
 * This module is pure (no DOM) so it can be tested directly. Text is passed in as segments, one per
 * rendered text node, and matches are reported as positions inside those segments.
 */

export interface SegmentPosition {
  segment: number;
  offset: number;
}

export interface CompactIndex {
  /** Folded text with all whitespace removed. */
  text: string;
  /** For each character of `text`, where it came from in the source segments. */
  origin: SegmentPosition[];
}

export interface SegmentSpan {
  start: SegmentPosition;
  /** Exclusive: `offset` is one past the last matched character in its segment. */
  end: SegmentPosition;
}

const CHAR_FOLDS: Record<string, string> = {
  "‘": "'",
  "’": "'",
  "‚": "'",
  "‛": "'",
  "“": '"',
  "”": '"',
  "„": '"',
  "«": '"',
  "»": '"',
  "‐": "-",
  "‑": "-",
  "‒": "-",
  "–": "-",
  "—": "-",
  "―": "-",
  "−": "-",
};

const INVISIBLE = /[­​‌‍⁠﻿]/;
const WHITESPACE = /\s/;

function foldCharacter(character: string): string {
  if (INVISIBLE.test(character)) return "";
  let out = "";
  for (const piece of character.normalize("NFKC")) {
    if (WHITESPACE.test(piece)) continue;
    out += (CHAR_FOLDS[piece] ?? piece).toLowerCase();
  }
  return out;
}

export interface FoldOptions {
  /** Also ignore hyphens, to match words split by a hyphen at a line break. */
  dropHyphens: boolean;
}

/** Builds the whitespace-free, case-folded form of the segments, remembering where each character came from. */
export function buildCompactIndex(segments: string[], options: FoldOptions = { dropHyphens: false }): CompactIndex {
  let text = "";
  const origin: SegmentPosition[] = [];

  segments.forEach((segment, segmentIndex) => {
    for (let offset = 0; offset < segment.length; offset++) {
      let folded = foldCharacter(segment[offset]);
      if (options.dropHyphens) folded = folded.replaceAll("-", "");
      for (let i = 0; i < folded.length; i++) {
        origin.push({ segment: segmentIndex, offset });
      }
      text += folded;
    }
  });
  return { text, origin };
}

export function compactText(text: string, options: FoldOptions = { dropHyphens: false }): string {
  return buildCompactIndex([text], options).text;
}

export function findAll(haystack: string, needle: string): number[] {
  if (!needle) return [];
  const positions: number[] = [];
  let at = haystack.indexOf(needle);
  while (at !== -1) {
    positions.push(at);
    at = haystack.indexOf(needle, at + 1);
  }
  return positions;
}

/**
 * Which occurrence of `portion` the server meant, counted within its own page text.
 * `rangeStart` is the portion's start offset in `pageText`. Returns 0 when the portion is unique.
 */
export function occurrenceIndex(pageText: string, portion: string, rangeStart: number): number {
  for (const options of [{ dropHyphens: false }, { dropHyphens: true }]) {
    const page = buildCompactIndex([pageText], options);
    const needle = compactText(portion, options);
    const positions = findAll(page.text, needle);
    if (positions.length === 0) continue;
    // The portion's own occurrence is the count of identical occurrences that start before it.
    return positions.filter((position) => page.origin[position].offset < rangeStart).length;
  }
  return 0;
}

export type LocateMethod = "exact" | "without-hyphens" | "by-ends";

export interface Located {
  span: SegmentSpan;
  method: LocateMethod;
}

const END_PROBE = 24;

function spanOf(index: CompactIndex, start: number, end: number): SegmentSpan {
  const last = index.origin[end - 1];
  return { start: index.origin[start], end: { segment: last.segment, offset: last.offset + 1 } };
}

/**
 * Finds `portion` in the rendered segments.
 *
 * `occurrence` picks among repeats (0 is the first). If the full text is not found, for example
 * because the viewer reordered a table, the start and the end of the portion are found separately
 * and the stretch between them is used, provided that stretch is a plausible length.
 */
export function locate(segments: string[], portion: string, occurrence = 0): Located | null {
  const attempts: { options: FoldOptions; method: LocateMethod }[] = [
    { options: { dropHyphens: false }, method: "exact" },
    { options: { dropHyphens: true }, method: "without-hyphens" },
  ];

  for (const { options, method } of attempts) {
    const needle = compactText(portion, options);
    if (needle.length < 4) continue;
    const index = buildCompactIndex(segments, options);
    const positions = findAll(index.text, needle);
    if (positions.length === 0) continue;
    const chosen = positions[Math.min(occurrence, positions.length - 1)];
    return { span: spanOf(index, chosen, chosen + needle.length), method };
  }

  const options = { dropHyphens: true };
  const needle = compactText(portion, options);
  if (needle.length < END_PROBE * 2) return null;
  const index = buildCompactIndex(segments, options);
  const head = findAll(index.text, needle.slice(0, END_PROBE));
  const tail = findAll(index.text, needle.slice(-END_PROBE));
  if (head.length === 0 || tail.length === 0) return null;

  const start = head[Math.min(occurrence, head.length - 1)];
  const end = tail.find((position) => position >= start);
  if (end === undefined) return null;
  const stop = end + END_PROBE;
  if (stop - start > needle.length * 1.5 + 80) return null;
  return { span: spanOf(index, start, stop), method: "by-ends" };
}
