"use client";

import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";

export interface HistoryTab {
  id: string;
  label: string;
  count: number | null;
  content: ReactNode;
}

/**
 * Documents, questions across documents and version comparisons in one place, one tab each, so the
 * library reads as a single history instead of three stacked lists.
 */
export function HistoryTabs({ tabs }: { tabs: HistoryTab[] }) {
  const [activeId, setActiveId] = useState(tabs[0].id);
  const base = useId();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  const move = (event: KeyboardEvent, index: number) => {
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : event.key === "ArrowLeft"
          ? (index - 1 + tabs.length) % tabs.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? tabs.length - 1
              : null;
    if (next === null) return;
    event.preventDefault();
    setActiveId(tabs[next].id);
    buttons.current[next]?.focus();
  };

  return (
    <section className="flex flex-col gap-0">
      <div role="tablist" aria-label="Your library" className="flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((tab, index) => {
          const selected = tab.id === active.id;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                buttons.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveId(tab.id)}
              onKeyDown={(event) => move(event, index)}
              className={`-mb-px flex min-h-12 shrink-0 cursor-pointer items-center gap-2 border-b-2 px-4 text-[13px] font-medium transition-colors ${
                selected ? "border-ink text-ink" : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              {tab.label}
              {tab.count !== null && (
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-[11px] tabular-nums ${
                    selected ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-subtle"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${base}-panel-${active.id}`}
        aria-labelledby={`${base}-tab-${active.id}`}
        className="mt-5 overflow-hidden rounded-card border border-line bg-surface shadow-card"
      >
        {active.content}
      </div>
    </section>
  );
}
