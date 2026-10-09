import { describe, expect, it } from "vitest";
import { buildCompactIndex, compactText, findAll, locate, occurrenceIndex } from "./textMatch";

/** What the located span actually covers, read back out of the segments. */
function covered(segments: string[], found: ReturnType<typeof locate>): string {
  if (!found) return "";
  const { start, end } = found.span;
  if (start.segment === end.segment) return segments[start.segment].slice(start.offset, end.offset);
  const parts = [segments[start.segment].slice(start.offset)];
  for (let i = start.segment + 1; i < end.segment; i++) parts.push(segments[i]);
  parts.push(segments[end.segment].slice(0, end.offset));
  return parts.join("");
}

describe("compactText", () => {
  it("removes whitespace and folds case, quotes, dashes and ligatures", () => {
    expect(compactText("  The “Supplier”\n shall — oﬃce ")).toBe('the"supplier"shall-office');
  });

  it("ignores soft hyphens and zero-width characters", () => {
    expect(compactText("indem­ni​fy")).toBe("indemnify");
  });

  it("can drop hyphens too", () => {
    expect(compactText("indem-nify", { dropHyphens: true })).toBe("indemnify");
  });
});

describe("buildCompactIndex", () => {
  it("remembers which segment and offset each character came from", () => {
    const index = buildCompactIndex(["ab ", "c d"]);
    expect(index.text).toBe("abcd");
    expect(index.origin).toEqual([
      { segment: 0, offset: 0 },
      { segment: 0, offset: 1 },
      { segment: 1, offset: 0 },
      { segment: 1, offset: 2 },
    ]);
  });
});

describe("locate", () => {
  it("finds a quote inside one text segment", () => {
    const segments = ["The Supplier shall indemnify the Customer against all losses."];
    const found = locate(segments, "shall indemnify the Customer");
    expect(covered(segments, found)).toBe("shall indemnify the Customer");
    expect(found?.method).toBe("exact");
  });

  it("finds a quote that the renderer split across many spans with no spaces between them", () => {
    const segments = ["The Supp", "lier shall", "indem", "nify the", "Customer."];
    const found = locate(segments, "The Supplier shall indemnify the Customer.");
    expect(found).not.toBeNull();
    expect(found?.span.start).toEqual({ segment: 0, offset: 0 });
    expect(found?.span.end).toEqual({ segment: 4, offset: 9 });
  });

  it("finds a quote that wraps over several lines", () => {
    const segments = ["Either party may terminate this", "Agreement on ninety (90) days", "written notice to the other."];
    const found = locate(segments, "terminate this Agreement on ninety (90) days written notice");
    expect(found?.span.start).toEqual({ segment: 0, offset: segments[0].indexOf("terminate") });
    expect(found?.span.end).toEqual({ segment: 2, offset: 14 });
  });

  it("tolerates curly quotes and dashes in the rendered text", () => {
    const segments = ["The Supplier’s liability – capped at AED 100,000."];
    expect(locate(segments, "The Supplier's liability - capped at AED 100,000.")).not.toBeNull();
  });

  it("finds a word split by a hyphen at the end of a line", () => {
    const segments = ["The Supplier shall indem-", "nify the Customer."];
    const found = locate(segments, "The Supplier shall indemnify the Customer.");
    expect(found?.method).toBe("without-hyphens");
  });

  it("picks the requested occurrence when a phrase repeats", () => {
    const segments = ["Notice must be given in writing.", "Other text.", "Notice must be given in writing."];
    expect(locate(segments, "Notice must be given in writing.", 0)?.span.start.segment).toBe(0);
    expect(locate(segments, "Notice must be given in writing.", 1)?.span.start.segment).toBe(2);
  });

  it("falls back to the last occurrence if asked for one that does not exist", () => {
    const segments = ["Only once: payment is due in thirty days."];
    expect(locate(segments, "payment is due in thirty days", 5)).not.toBeNull();
  });

  it("returns null when the text is not there", () => {
    expect(locate(["Entirely different content about delivery."], "The Supplier shall indemnify the Customer")).toBeNull();
  });

  it("returns null for a portion too short to mean anything", () => {
    expect(locate(["abc def ghi"], "de")).toBeNull();
  });

  it("uses the start and end of a long quote when the middle was reordered by the renderer", () => {
    const quote =
      "The Supplier shall deliver the Goods to the Customer within thirty days of the Effective Date and shall bear all costs of carriage insurance and delivery.";
    const rendered = [
      "The Supplier shall deliver the Goods to the Customer within thirty days of the",
      "Effective Date [table footnote 4] and shall bear all costs of",
      "carriage insurance and delivery.",
    ];
    const found = locate(rendered, quote);
    expect(found?.method).toBe("by-ends");
    expect(found?.span.start).toEqual({ segment: 0, offset: 0 });
    expect(found?.span.end.segment).toBe(2);
  });

  it("refuses a start-and-end match when the stretch between them is implausibly long", () => {
    const quote = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma";
    const filler = "lorem ipsum dolor sit amet ".repeat(40);
    const rendered = ["Alpha beta gamma delta epsilon zeta eta theta " + filler + " lambda mu nu xi omicron pi rho sigma"];
    expect(locate(rendered, quote)).toBeNull();
  });
});

describe("occurrenceIndex", () => {
  const page = "Notice in writing. Middle part. Notice in writing. End part. Notice in writing.";

  it("is 0 for the first occurrence and counts earlier identical ones for later ones", () => {
    expect(occurrenceIndex(page, "Notice in writing.", page.indexOf("Notice in writing."))).toBe(0);
    expect(occurrenceIndex(page, "Notice in writing.", page.indexOf("Notice in writing.", 20))).toBe(1);
    expect(occurrenceIndex(page, "Notice in writing.", page.lastIndexOf("Notice in writing."))).toBe(2);
  });

  it("is 0 when the portion is unique or not found", () => {
    expect(occurrenceIndex(page, "End part.", page.indexOf("End part."))).toBe(0);
    expect(occurrenceIndex(page, "never appears here", 10)).toBe(0);
  });

  it("is not thrown off by line breaks in the server text", () => {
    const text = "Notice in\nwriting. Filler. Notice in\nwriting.";
    expect(occurrenceIndex(text, "Notice in\nwriting.", text.lastIndexOf("Notice in"))).toBe(1);
  });
});

describe("findAll", () => {
  it("returns every start, including overlapping ones", () => {
    expect(findAll("aaaa", "aa")).toEqual([0, 1, 2]);
    expect(findAll("abc", "")).toEqual([]);
  });
});
