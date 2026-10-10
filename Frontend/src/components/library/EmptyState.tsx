import type { Icon } from "@phosphor-icons/react";

interface EmptyStateProps {
  icon: Icon;
  title: string;
  body: string;
}

/** What a list shows when there is nothing in it yet. */
export function EmptyState({ icon: Glyph, title, body }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-surface-2 text-ink-subtle">
        <Glyph size={22} aria-hidden />
      </span>
      <h3 className="text-[15px] font-medium text-ink">{title}</h3>
      <p className="max-w-[40ch] text-sm leading-relaxed text-ink-muted">{body}</p>
    </div>
  );
}
