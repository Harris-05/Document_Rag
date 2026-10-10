import { describe, expect, it } from "vitest";
import {
  allSignificances,
  categoriesIn,
  countBySignificance,
  defaultFilters,
  filterChanges,
  filtersAreActive,
  headingTitle,
  sortChanges,
  toggleSignificance,
} from "./changes";
import type { Change, ChangeType, Significance } from "./types";

let counter = 0;
function change(significance: Significance, overrides: Partial<Change> = {}): Change {
  counter += 1;
  return {
    id: counter,
    type: "modified" as ChangeType,
    moved: false,
    significance,
    ai_rated: true,
    raised_by_rules: false,
    category: "other",
    title: `Change ${counter}`,
    summary: "",
    similarity: 0.9,
    figures: [],
    figure_text: [],
    obligations: [],
    old: null,
    new: null,
    diff: [],
    position: counter,
    ...overrides,
  };
}

const sample = [
  change("cosmetic", { position: 1, category: "scope_services" }),
  change("critical", { position: 2, category: "liability" }),
  change("minor", { position: 3, category: "payment", type: "added" }),
  change("major", { position: 4, category: "termination" }),
  change("unrated", { position: 5, category: "liability", type: "removed" }),
  change("critical", { position: 6, category: "payment" }),
];

describe("sorting by significance", () => {
  it("puts the most serious first, with not-rated above minor and wording-only last", () => {
    expect(sortChanges(sample, "significance").map((c) => c.significance)).toEqual([
      "critical",
      "critical",
      "major",
      "unrated",
      "minor",
      "cosmetic",
    ]);
  });

  it("keeps document order among changes of the same significance", () => {
    const critical = sortChanges(sample, "significance").filter((c) => c.significance === "critical");
    expect(critical.map((c) => c.position)).toEqual([2, 6]);
  });

  it("does not modify the list it was given", () => {
    const before = sample.map((c) => c.id);
    sortChanges(sample, "significance");
    expect(sample.map((c) => c.id)).toEqual(before);
  });
});

describe("other sort orders", () => {
  it("follows the order of the document", () => {
    expect(sortChanges(sample, "document").map((c) => c.position)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("groups by category, serious first inside each group", () => {
    const sorted = sortChanges(sample, "category");
    expect(sorted.map((c) => c.category)).toEqual(["liability", "liability", "payment", "payment", "scope_services", "termination"]);
    expect(sorted.slice(0, 2).map((c) => c.significance)).toEqual(["critical", "unrated"]);
  });
});

describe("filtering", () => {
  it("shows everything by default", () => {
    expect(filterChanges(sample, defaultFilters())).toHaveLength(6);
    expect(filtersAreActive(defaultFilters())).toBe(false);
  });

  it("hides the significance levels that are switched off", () => {
    const filters = { ...defaultFilters(), significance: new Set<Significance>(["critical", "major"]) };
    expect(filterChanges(sample, filters).map((c) => c.significance).sort()).toEqual(["critical", "critical", "major"]);
    expect(filtersAreActive(filters)).toBe(true);
  });

  it("can narrow by type and by category together", () => {
    const filters = { ...defaultFilters(), type: "removed" as const, category: "liability" };
    expect(filterChanges(sample, filters).map((c) => c.significance)).toEqual(["unrated"]);
  });

  it("an empty significance selection shows nothing", () => {
    expect(filterChanges(sample, { ...defaultFilters(), significance: new Set() })).toEqual([]);
  });
});

describe("helpers", () => {
  it("counts each significance level, including zero", () => {
    expect(countBySignificance(sample)).toEqual({ critical: 2, major: 1, unrated: 1, minor: 1, cosmetic: 1 });
  });

  it("lists the categories that occur, most common first", () => {
    expect(categoriesIn(sample)).toEqual(["liability", "payment", "scope_services", "termination"]);
  });

  it("toggles a significance level without changing the original set", () => {
    const original = allSignificances();
    const without = toggleSignificance(original, "cosmetic");
    expect(without.has("cosmetic")).toBe(false);
    expect(original.has("cosmetic")).toBe(true);
    expect(toggleSignificance(without, "cosmetic").has("cosmetic")).toBe(true);
  });
});

describe("headingTitle", () => {
  it("drops the clause number and keeps the title", () => {
    expect(headingTitle("12. Termination")).toBe("Termination");
    expect(headingTitle("12.1 Termination for convenience")).toBe("Termination for convenience");
    expect(headingTitle("(a) Scope")).toBe("Scope");
    expect(headingTitle("GOVERNING LAW")).toBe("GOVERNING LAW");
    expect(headingTitle("")).toBe("");
  });
});
