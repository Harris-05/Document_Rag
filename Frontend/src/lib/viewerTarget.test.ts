import { describe, expect, it } from "vitest";
import { matchesOf, portionsFor, portionsKey } from "./viewerTarget";
import type { Citation } from "./types";

const pages = [
  { page_number: 1, text: "Notice in writing. Filler. Notice in writing. The Supplier shall deliver the goods and" },
  { page_number: 2, text: "services within thirty days of the Effective Date." },
];

const citation = (overrides: Partial<Citation>): Citation => ({
  n: 1,
  quote: "q",
  verified: true,
  page: 1,
  ranges: [],
  matches: [],
  primary_index: 0,
  occurrences: 1,
  ...overrides,
});

describe("matchesOf", () => {
  it("uses the full list of matches when present", () => {
    const matches = [[{ page: 1, start: 0, end: 5 }], [{ page: 2, start: 0, end: 5 }]];
    expect(matchesOf(citation({ matches }))).toEqual(matches);
  });

  it("falls back to the single range for messages saved before matches existed", () => {
    const ranges = [{ page: 1, start: 0, end: 5 }];
    expect(matchesOf(citation({ ranges }))).toEqual([ranges]);
  });

  it("is empty for an unverified citation", () => {
    expect(matchesOf(citation({}))).toEqual([]);
  });
});

describe("portionsFor", () => {
  it("cuts the quoted text out of each page the match touches", () => {
    const start = pages[0].text.indexOf("The Supplier");
    const portions = portionsFor(
      [
        { page: 1, start, end: pages[0].text.length },
        { page: 2, start: 0, end: pages[1].text.length },
      ],
      pages,
    );
    expect(portions.map((p) => p.page)).toEqual([1, 2]);
    expect(portions[0].text).toBe("The Supplier shall deliver the goods and");
    expect(portions[1].text).toBe("services within thirty days of the Effective Date.");
  });

  it("works out which repeat on the page is meant", () => {
    const first = pages[0].text.indexOf("Notice in writing.");
    const second = pages[0].text.indexOf("Notice in writing.", first + 1);
    expect(portionsFor([{ page: 1, start: first, end: first + 18 }], pages)[0].occurrence).toBe(0);
    expect(portionsFor([{ page: 1, start: second, end: second + 18 }], pages)[0].occurrence).toBe(1);
  });

  it("skips pages it does not have and blank ranges", () => {
    expect(portionsFor([{ page: 9, start: 0, end: 5 }], pages)).toEqual([]);
    expect(portionsFor([{ page: 1, start: 0, end: 0 }], pages)).toEqual([]);
  });
});

describe("portionsKey", () => {
  it("changes when the highlighted content changes and not otherwise", () => {
    const a = [{ page: 1, text: "alpha beta gamma", occurrence: 0 }];
    expect(portionsKey(a)).toBe(portionsKey([{ ...a[0] }]));
    expect(portionsKey(a)).not.toBe(portionsKey([{ ...a[0], occurrence: 1 }]));
  });
});
