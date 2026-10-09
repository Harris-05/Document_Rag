import { describe, expect, it, vi } from "vitest";
import { splitByRanges } from "./highlight";
import { EXPLANATION_LABEL, splitCitations, splitExplanation, splitParagraphs } from "./messageText";
import { pruneSelection, toggleSelection } from "./selection";
import { createSseParser, type SseFrame } from "./sse";
import { validateFile } from "./validation";

function collect(...chunks: string[]): SseFrame[] {
  const frames: SseFrame[] = [];
  const parser = createSseParser((frame) => frames.push(frame));
  chunks.forEach((chunk) => parser.push(chunk));
  return frames;
}

describe("SSE parser", () => {
  it("parses a complete frame", () => {
    expect(collect('event: token\ndata: {"text":"Hi"}\n\n')).toEqual([{ event: "token", data: { text: "Hi" } }]);
  });

  it("buffers a frame that arrives in several network chunks", () => {
    const frames = collect('event: tok', 'en\ndata: {"te', 'xt":"Hi"}\n', "\n");
    expect(frames).toEqual([{ event: "token", data: { text: "Hi" } }]);
  });

  it("handles several frames in one chunk and CRLF line endings", () => {
    const frames = collect('event: a\r\ndata: {"n":1}\r\n\r\nevent: b\r\ndata: {"n":2}\r\n\r\n');
    expect(frames.map((frame) => frame.event)).toEqual(["a", "b"]);
  });

  it("skips malformed frames without breaking the stream", () => {
    const frames = collect("event: bad\ndata: {oops\n\n", 'event: ok\ndata: {"fine":true}\n\n');
    expect(frames).toEqual([{ event: "ok", data: { fine: true } }]);
  });

  it("keeps unicode intact", () => {
    expect(collect('event: token\ndata: {"text":"\u201cquoted\u201d"}\n\n')[0].data).toEqual({ text: "\u201cquoted\u201d" });
  });
});

describe("splitByRanges", () => {
  it("returns plain text when there is nothing to highlight", () => {
    expect(splitByRanges("hello", [])).toEqual([{ text: "hello", highlighted: false }]);
  });

  it("splits around a range", () => {
    expect(splitByRanges("abcdef", [{ start: 2, end: 4 }])).toEqual([
      { text: "ab", highlighted: false },
      { text: "cd", highlighted: true },
      { text: "ef", highlighted: false },
    ]);
  });

  it("merges overlapping and touching ranges", () => {
    const segments = splitByRanges("abcdefgh", [
      { start: 4, end: 6 },
      { start: 1, end: 3 },
      { start: 2, end: 5 },
    ]);
    expect(segments.filter((s) => s.highlighted).map((s) => s.text)).toEqual(["bcdef"]);
  });

  it("clamps ranges that run past the text and ignores empty ones", () => {
    expect(splitByRanges("abc", [{ start: 1, end: 99 }, { start: 2, end: 2 }])).toEqual([
      { text: "a", highlighted: false },
      { text: "bc", highlighted: true },
    ]);
  });
});

describe("splitCitations", () => {
  it("separates markers from text", () => {
    expect(splitCitations("Ninety days [1] and a cap [2].")).toEqual([
      { type: "text", value: "Ninety days " },
      { type: "cite", n: 1 },
      { type: "text", value: " and a cap " },
      { type: "cite", n: 2 },
      { type: "text", value: "." },
    ]);
  });

  it("leaves other bracketed text alone", () => {
    expect(splitCitations("See [Schedule A] for details")).toEqual([{ type: "text", value: "See [Schedule A] for details" }]);
  });

  it("splits paragraphs on blank lines", () => {
    expect(splitParagraphs("One.\n\nTwo.\n\n\nThree.")).toEqual(["One.", "Two.", "Three."]);
  });
});

describe("validateFile", () => {
  const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);

  it("accepts PDF and DOCX regardless of case", () => {
    expect(validateFile(file("a.pdf"))).toBeNull();
    expect(validateFile(file("B.DOCX"))).toBeNull();
  });

  it("rejects other types with the file name in the message", () => {
    const result = validateFile(file("sheet.xlsx"));
    expect(result?.code).toBe("UNSUPPORTED_TYPE");
    expect(result?.message).toContain("sheet.xlsx");
  });

  it("rejects empty and oversized files", () => {
    expect(validateFile(file("a.pdf", 0))?.code).toBe("EMPTY_FILE");
    const big = new File([new Uint8Array(1)], "a.pdf");
    vi.spyOn(big, "size", "get").mockReturnValue(26 * 1024 * 1024);
    expect(validateFile(big)?.code).toBe("FILE_TOO_LARGE");
  });
});

describe("splitExplanation", () => {
  it("returns everything as the answer when there is no explanation", () => {
    expect(splitExplanation("Ninety days [1].")).toEqual({ answer: "Ninety days [1].", explanation: null });
  });

  it("separates the labelled explanation from the document-based answer", () => {
    const content = `Either party may terminate on 90 days notice [1].\n\n${EXPLANATION_LABEL}\nIn general, termination for convenience lets a party leave without proving fault.`;
    expect(splitExplanation(content)).toEqual({
      answer: "Either party may terminate on 90 days notice [1].",
      explanation: "In general, termination for convenience lets a party leave without proving fault.",
    });
  });

  it("accepts text on the same line as the label", () => {
    const result = splitExplanation(`Answer [1].\n${EXPLANATION_LABEL} Typically this means X.`);
    expect(result.explanation).toBe("Typically this means X.");
  });

  it("hides a half-streamed label so it never flashes on screen", () => {
    expect(splitExplanation("Answer [1].\n\nGeneral expla")).toEqual({ answer: "Answer [1].", explanation: null });
    expect(splitExplanation("Answer [1].\n\nGeneral explanation (not from")).toEqual({
      answer: "Answer [1].",
      explanation: null,
    });
  });

  it("does not hide ordinary text that merely starts with the same letters", () => {
    expect(splitExplanation("Answer.\n\nGeneral liability applies.").explanation).toBeNull();
    expect(splitExplanation("Answer.\n\nGeneral liability applies.").answer).toBe("Answer.\n\nGeneral liability applies.");
  });

  it("shows an explanation that is still streaming in", () => {
    expect(splitExplanation(`Answer [1].\n\n${EXPLANATION_LABEL}\nIn gen`).explanation).toBe("In gen");
  });
});

describe("document selection", () => {
  it("adds documents in the order they are chosen and removes them when chosen again", () => {
    let selected: string[] = [];
    selected = toggleSelection(selected, "b");
    selected = toggleSelection(selected, "a");
    expect(selected).toEqual(["b", "a"]);
    expect(toggleSelection(selected, "b")).toEqual(["a"]);
  });

  it("stops at the limit but still lets a chosen document be removed", () => {
    const full = ["1", "2", "3", "4", "5"];
    expect(toggleSelection(full, "6")).toEqual(full);
    expect(toggleSelection(full, "3")).toEqual(["1", "2", "4", "5"]);
    expect(toggleSelection(["1", "2"], "3", 2)).toEqual(["1", "2"]);
  });

  it("forgets documents that no longer exist, and keeps the same array when nothing changed", () => {
    const selected = ["a", "b", "c"];
    expect(pruneSelection(selected, ["a", "c"])).toEqual(["a", "c"]);
    expect(pruneSelection(selected, ["a", "b", "c", "d"])).toBe(selected);
  });
});
