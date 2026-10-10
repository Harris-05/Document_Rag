interface DocumentTab {
  id: string;
  label: string;
  /** A short badge shown before the label, such as "1" or "Before". */
  badge: string;
}

interface DocumentTabsProps {
  tabs: DocumentTab[];
  activeId: string;
  onSelect: (id: string) => void;
  ariaLabel: string;
}

/** One tab per document shown in the viewer, for panes that can show several. */
export function DocumentTabs({ tabs, activeId, onSelect, ariaLabel }: DocumentTabsProps) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.id === activeId}
          onClick={() => onSelect(tab.id)}
          className={`flex min-h-10 max-w-60 shrink-0 cursor-pointer items-center gap-2 rounded-ctl px-3 text-[13px] font-medium transition-colors ${
            tab.id === activeId ? "bg-accent-soft text-accent" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
          }`}
        >
          <span className="grid min-w-5 shrink-0 place-items-center rounded-full bg-surface px-1.5 font-mono text-[10px]">
            {tab.badge}
          </span>
          <span className="truncate" title={tab.label}>
            {tab.label}
          </span>
        </button>
      ))}
    </div>
  );
}
