"use client";

import {
  CATEGORY_LABEL,
  SIGNIFICANCE_LABEL,
  SIGNIFICANCE_ORDER,
  SORT_LABEL,
  TYPE_LABEL,
  filtersAreActive,
  toggleSignificance,
  type ChangeFilters,
  type SortMode,
} from "@/lib/changes";
import type { ChangeType, Significance } from "@/lib/types";

interface ChangeFiltersProps {
  filters: ChangeFilters;
  onFilters: (filters: ChangeFilters) => void;
  sort: SortMode;
  onSort: (sort: SortMode) => void;
  counts: Record<Significance, number>;
  categories: string[];
  shown: number;
  total: number;
}

const SELECT =
  "min-h-10 cursor-pointer rounded-ctl border border-line-strong bg-surface px-3 text-[13px] text-ink hover:bg-surface-2";

export function ChangeFilterBar({ filters, onFilters, sort, onSort, counts, categories, shown, total }: ChangeFiltersProps) {
  const levels = SIGNIFICANCE_ORDER.filter((level) => counts[level] > 0);

  return (
    <section aria-label="Filter and sort the changes" className="flex flex-col gap-3">
      <div role="group" aria-label="Significance" className="flex flex-wrap gap-2">
        {levels.map((level) => {
          const on = filters.significance.has(level);
          return (
            <button
              key={level}
              type="button"
              aria-pressed={on}
              onClick={() => onFilters({ ...filters, significance: toggleSignificance(filters.significance, level) })}
              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-full border px-3.5 text-[13px] font-medium transition-colors ${
                on ? "border-accent bg-accent-soft text-accent" : "border-line-strong bg-surface text-ink-muted hover:bg-surface-2"
              }`}
            >
              {SIGNIFICANCE_LABEL[level]}
              <span className="font-mono text-xs tabular-nums">{counts[level]}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="filter-type">
          Type of change
        </label>
        <select
          id="filter-type"
          className={SELECT}
          value={filters.type}
          onChange={(event) => onFilters({ ...filters, type: event.target.value as ChangeType | "all" })}
        >
          <option value="all">All types</option>
          {(Object.keys(TYPE_LABEL) as ChangeType[]).map((type) => (
            <option key={type} value={type}>
              {TYPE_LABEL[type]}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="filter-category">
          Category
        </label>
        <select
          id="filter-category"
          className={SELECT}
          value={filters.category}
          onChange={(event) => onFilters({ ...filters, category: event.target.value })}
        >
          <option value="all">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {CATEGORY_LABEL[category] ?? category}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="sort-changes">
          Sort by
        </label>
        <select id="sort-changes" className={SELECT} value={sort} onChange={(event) => onSort(event.target.value as SortMode)}>
          {(Object.keys(SORT_LABEL) as SortMode[]).map((mode) => (
            <option key={mode} value={mode}>
              {SORT_LABEL[mode]}
            </option>
          ))}
        </select>

        <p className="ml-auto text-[13px] text-ink-subtle" aria-live="polite">
          Showing <span className="font-mono tabular-nums text-ink-muted">{shown}</span> of{" "}
          <span className="font-mono tabular-nums text-ink-muted">{total}</span>
        </p>
      </div>

      {filtersAreActive(filters) && (
        <div>
          <button
            type="button"
            onClick={() => onFilters({ significance: new Set(SIGNIFICANCE_ORDER), type: "all", category: "all" })}
            className="min-h-9 cursor-pointer rounded-ctl text-[13px] font-medium text-accent underline underline-offset-2"
          >
            Clear filters
          </button>
        </div>
      )}
    </section>
  );
}
