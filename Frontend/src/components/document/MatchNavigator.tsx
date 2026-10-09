import { CaretLeft, CaretRight } from "@phosphor-icons/react";

interface MatchNavigatorProps {
  index: number;
  count: number;
  onStep: (delta: number) => void;
}

/** Steps through every place a quoted passage occurs. Shown only when there is more than one. */
export function MatchNavigator({ index, count, onStep }: MatchNavigatorProps) {
  if (count < 2) return null;
  return (
    <div
      role="group"
      aria-label="Occurrences of this quote"
      className="flex items-center gap-1 rounded-ctl bg-accent-soft px-1 text-[13px] text-accent"
    >
      <button
        type="button"
        onClick={() => onStep(-1)}
        aria-label="Previous occurrence"
        className="grid size-9 cursor-pointer place-items-center rounded-ctl hover:brightness-95"
      >
        <CaretLeft size={16} weight="bold" aria-hidden />
      </button>
      <span className="px-1 font-mono tabular-nums" aria-live="polite">
        {index + 1} of {count}
      </span>
      <button
        type="button"
        onClick={() => onStep(1)}
        aria-label="Next occurrence"
        className="grid size-9 cursor-pointer place-items-center rounded-ctl hover:brightness-95"
      >
        <CaretRight size={16} weight="bold" aria-hidden />
      </button>
    </div>
  );
}
