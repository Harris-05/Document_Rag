"use client";

import { ArrowRight, Info } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { CATEGORY_LABEL, FIGURE_LABEL, SIGNIFICANCE_LABEL, TYPE_LABEL, headingTitle } from "@/lib/changes";
import type { Change } from "@/lib/types";
import { DiffText } from "./DiffText";
import { SignificanceBadge } from "./SignificanceBadge";

interface ChangeCardProps {
  change: Change;
  active: boolean;
  onView: (change: Change, side: "old" | "new") => void;
}

function FigureChip({ figure }: { figure: Change["figures"][number] }) {
  const label = FIGURE_LABEL[figure.kind] ?? figure.kind;
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-ctl bg-surface-2 px-3 py-2 text-[13px]">
      <span className="text-ink-subtle">{label}</span>
      {figure.old && <span className="diff-del font-mono">{figure.old}</span>}
      {figure.old && figure.new && <ArrowRight size={14} className="text-ink-subtle" aria-label="changed to" />}
      {figure.new && <span className="diff-ins font-mono">{figure.new}</span>}
      {!figure.old && <span className="text-ink-subtle">added</span>}
      {!figure.new && <span className="text-ink-subtle">removed</span>}
    </li>
  );
}

function pageLabel(change: Change): string {
  const before = change.old?.page;
  const after = change.new?.page;
  if (before && after) return before === after ? `Page ${before}` : `Page ${before} to ${after}`;
  return `Page ${before ?? after}`;
}

export function ChangeCard({ change, active, onView }: ChangeCardProps) {
  const [expanded, setExpanded] = useState(false);
  const twoSides = change.old !== null && change.new !== null;
  const clamp = expanded ? "" : "line-clamp-6";
  const headingRenamed =
    twoSides &&
    Boolean(change.old?.heading) &&
    Boolean(change.new?.heading) &&
    headingTitle(change.old?.heading ?? "").toLowerCase() !== headingTitle(change.new?.heading ?? "").toLowerCase();
  const longClause = Math.max(change.old?.text.length ?? 0, change.new?.text.length ?? 0) > 420;

  return (
    <li
      id={`change-${change.id}`}
      aria-label={`${SIGNIFICANCE_LABEL[change.significance]} change: ${change.title}`}
      className={`flex flex-col gap-4 rounded-card border p-4 transition-colors duration-200 sm:p-5 ${
        active ? "border-accent bg-accent-soft/40" : "border-line bg-surface"
      }`}
    >
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <SignificanceBadge significance={change.significance} />
          <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-muted">
            {TYPE_LABEL[change.type]}
            {change.moved && change.type !== "moved" ? ", moved" : ""}
          </span>
          <span className="text-xs text-ink-subtle">{CATEGORY_LABEL[change.category] ?? change.category}</span>
          <span className="ml-auto font-mono text-xs tabular-nums text-ink-subtle">{pageLabel(change)}</span>
        </div>
        <h3 className="text-[15px] font-semibold tracking-tight text-ink">{change.title}</h3>
        <p className="max-w-[72ch] text-[14px] leading-relaxed text-ink-muted">{change.summary}</p>
      </div>

      {change.figures.length > 0 && (
        <ul aria-label="Figures that changed" className="flex flex-col gap-1.5">
          {change.figures.map((figure, index) => (
            <FigureChip key={index} figure={figure} />
          ))}
        </ul>
      )}

      {change.obligations.length > 0 && (
        <p className="text-[13px] text-ink-muted">
          Obligation wording changed:{" "}
          {change.obligations.map((o) => `"${o.word}" ${o.old} to ${o.new}`).join(", ")}.
        </p>
      )}

      {headingRenamed && (
        <p className="text-[13px] text-ink-muted">
          Heading changed from &ldquo;{headingTitle(change.old?.heading ?? "")}&rdquo; to &ldquo;
          {headingTitle(change.new?.heading ?? "")}&rdquo;.
        </p>
      )}

      {change.raised_by_rules && (
        <p className="flex items-start gap-1.5 text-[12px] leading-relaxed text-ink-subtle">
          <Info size={14} weight="fill" className="mt-px shrink-0" aria-hidden />
          Rated at least {SIGNIFICANCE_LABEL[change.significance].toLowerCase()} because a figure or an obligation
          word changed, whatever the wording around it looks like.
        </p>
      )}

      <div className={`grid gap-3 ${twoSides ? "md:grid-cols-2" : ""}`}>
        {change.old && (
          <section aria-label="Before" className="flex flex-col gap-1.5 rounded-ctl bg-surface-2 p-3">
            <h4 className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              {change.new ? "Before" : "Removed clause"}
            </h4>
            {change.old.heading && <p className="text-[13px] font-semibold text-ink">{headingTitle(change.old.heading)}</p>}
            <p className={`whitespace-pre-wrap text-[13px] leading-relaxed text-ink ${clamp}`}>
              <DiffText segments={change.diff} side="old" fallback={change.old.text} />
            </p>
          </section>
        )}
        {change.new && (
          <section aria-label="After" className="flex flex-col gap-1.5 rounded-ctl bg-surface-2 p-3">
            <h4 className="text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
              {change.old ? "After" : "New clause"}
            </h4>
            {change.new.heading && <p className="text-[13px] font-semibold text-ink">{headingTitle(change.new.heading)}</p>}
            <p className={`whitespace-pre-wrap text-[13px] leading-relaxed text-ink ${clamp}`}>
              <DiffText segments={change.diff} side="new" fallback={change.new.text} />
            </p>
          </section>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {change.old && (
          <Button variant="secondary" onClick={() => onView(change, "old")} className="min-h-10 px-3 text-[13px]">
            View in the old version
          </Button>
        )}
        {change.new && (
          <Button variant="secondary" onClick={() => onView(change, "new")} className="min-h-10 px-3 text-[13px]">
            View in the new version
          </Button>
        )}
        {longClause && (
          <Button variant="ghost" onClick={() => setExpanded((value) => !value)} className="min-h-10 px-3 text-[13px]" aria-expanded={expanded}>
            {expanded ? "Show less" : "Show the whole clause"}
          </Button>
        )}
      </div>
    </li>
  );
}
