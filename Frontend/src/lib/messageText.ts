export type TextPart = { type: "text"; value: string } | { type: "cite"; n: number };

/** Splits answer text into plain parts and `[n]` citation markers. */
export function splitCitations(content: string): TextPart[] {
  const parts: TextPart[] = [];
  const pattern = /\[(\d{1,2})\]/g;
  let cursor = 0;
  for (const match of content.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) parts.push({ type: "text", value: content.slice(cursor, index) });
    parts.push({ type: "cite", n: Number(match[1]) });
    cursor = index + match[0].length;
  }
  if (cursor < content.length) parts.push({ type: "text", value: content.slice(cursor) });
  return parts;
}

export function splitParagraphs(content: string): string[] {
  return content.split(/\n{2,}/).filter((paragraph) => paragraph.trim().length > 0);
}

/** The exact line the model writes before its general (non-document) explanation. */
export const EXPLANATION_LABEL = "General explanation (not from the document):";

export interface SplitAnswer {
  /** The part that rests on the document and carries citations. */
  answer: string;
  /** Plain-language background from general knowledge, shown separately. Null when absent. */
  explanation: string | null;
}

/**
 * Separates the document-based answer from the labelled general explanation. While text is still
 * streaming, a half-written label at the very end is hidden so it does not flash on screen.
 */
export function splitExplanation(content: string): SplitAnswer {
  const labelAt = content.search(/^[ \t]*General explanation \(not from the document\):/im);
  if (labelAt !== -1) {
    const afterLabel = content.slice(labelAt).replace(/^[ \t]*General explanation \(not from the document\):[ \t]*/i, "");
    return { answer: content.slice(0, labelAt).trim(), explanation: afterLabel.trim() };
  }

  const lastLineStart = content.lastIndexOf("\n") + 1;
  const lastLine = content.slice(lastLineStart).trim();
  if (lastLine.length >= 3 && EXPLANATION_LABEL.toLowerCase().startsWith(lastLine.toLowerCase())) {
    return { answer: content.slice(0, lastLineStart).trim(), explanation: null };
  }
  return { answer: content, explanation: null };
}
