import type { Change, ChangeType, Significance } from "./types";

/** Most serious first. "Not rated" sits above "minor" because a person needs to look at it. */
export const SIGNIFICANCE_ORDER: Significance[] = ["critical", "major", "unrated", "minor", "cosmetic"];

export const SIGNIFICANCE_LABEL: Record<Significance, string> = {
  critical: "Critical",
  major: "Major",
  unrated: "Not rated",
  minor: "Minor",
  cosmetic: "Wording only",
};

export const TYPE_LABEL: Record<ChangeType, string> = {
  modified: "Modified",
  added: "Added",
  removed: "Removed",
  moved: "Moved",
};

export const CATEGORY_LABEL: Record<string, string> = {
  payment: "Payment",
  liability: "Liability",
  indemnity: "Indemnity",
  termination: "Termination",
  term_renewal: "Term and renewal",
  confidentiality: "Confidentiality",
  ip: "Intellectual property",
  governing_law: "Governing law",
  disputes: "Disputes",
  warranties: "Warranties",
  data_protection: "Data protection",
  scope_services: "Scope and services",
  definitions: "Definitions",
  other: "Other",
};

export const FIGURE_LABEL: Record<string, string> = {
  money: "Amount",
  percent: "Percentage",
  duration: "Period",
  date: "Date",
};

export type SortMode = "significance" | "document" | "category";

export const SORT_LABEL: Record<SortMode, string> = {
  significance: "Most significant first",
  document: "Order in the document",
  category: "Category",
};

export interface ChangeFilters {
  /** Significance levels to show. An empty set shows nothing. */
  significance: Set<Significance>;
  type: ChangeType | "all";
  category: string | "all";
}

export function rank(significance: Significance): number {
  const index = SIGNIFICANCE_ORDER.indexOf(significance);
  return index === -1 ? SIGNIFICANCE_ORDER.length : index;
}

export function allSignificances(): Set<Significance> {
  return new Set(SIGNIFICANCE_ORDER);
}

export function defaultFilters(): ChangeFilters {
  return { significance: allSignificances(), type: "all", category: "all" };
}

export function filtersAreActive(filters: ChangeFilters): boolean {
  return filters.significance.size !== SIGNIFICANCE_ORDER.length || filters.type !== "all" || filters.category !== "all";
}

export function filterChanges(changes: Change[], filters: ChangeFilters): Change[] {
  return changes.filter(
    (change) =>
      filters.significance.has(change.significance) &&
      (filters.type === "all" || change.type === filters.type) &&
      (filters.category === "all" || change.category === filters.category),
  );
}

/** Returns a new array. Ties always fall back to document order, so the result is stable. */
export function sortChanges(changes: Change[], mode: SortMode): Change[] {
  const byPosition = (a: Change, b: Change) => a.position - b.position || a.id - b.id;
  const sorted = [...changes];
  if (mode === "document") return sorted.sort(byPosition);
  if (mode === "category") {
    return sorted.sort(
      (a, b) =>
        (CATEGORY_LABEL[a.category] ?? a.category).localeCompare(CATEGORY_LABEL[b.category] ?? b.category) ||
        rank(a.significance) - rank(b.significance) ||
        byPosition(a, b),
    );
  }
  return sorted.sort((a, b) => rank(a.significance) - rank(b.significance) || byPosition(a, b));
}

/** A clause heading without its leading number: "12. Termination" becomes "Termination". */
export function headingTitle(heading: string): string {
  return heading.replace(/^\s*(?:\d+(?:\.\d+)*\.?|\([a-z0-9]{1,4}\)|[a-z]\.)\s+/i, "").trim();
}

export function countBySignificance(changes: Change[]): Record<Significance, number> {
  const counts: Record<Significance, number> = { critical: 0, major: 0, unrated: 0, minor: 0, cosmetic: 0 };
  for (const change of changes) counts[change.significance] += 1;
  return counts;
}

/** The categories that actually occur, for the filter menu, most common first. */
export function categoriesIn(changes: Change[]): string[] {
  const counts = new Map<string, number>();
  for (const change of changes) counts.set(change.category, (counts.get(change.category) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([category]) => category);
}

/** Turns one significance chip on or off. */
export function toggleSignificance(current: Set<Significance>, level: Significance): Set<Significance> {
  const next = new Set(current);
  if (next.has(level)) next.delete(level);
  else next.add(level);
  return next;
}
