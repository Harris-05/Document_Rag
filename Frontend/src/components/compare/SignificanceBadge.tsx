import { SIGNIFICANCE_LABEL } from "@/lib/changes";
import type { Significance } from "@/lib/types";

const STYLE: Record<Significance, string> = {
  critical: "bg-danger-soft text-danger",
  major: "bg-warn-soft text-warn",
  unrated: "border border-dashed border-line-strong bg-surface text-ink-muted",
  minor: "bg-accent-soft text-accent",
  cosmetic: "bg-surface-2 text-ink-subtle",
};

export function SignificanceBadge({ significance }: { significance: Significance }) {
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${STYLE[significance]}`}>
      {SIGNIFICANCE_LABEL[significance]}
    </span>
  );
}
