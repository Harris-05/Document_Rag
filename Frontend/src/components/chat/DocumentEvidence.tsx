import { CheckCircle, MinusCircle, WarningCircle } from "@phosphor-icons/react/dist/ssr";
import type { DocumentCoverage } from "@/lib/types";

const PRESENTATION = {
  sufficient: { label: "Strong evidence", icon: CheckCircle, className: "text-success", weight: "fill" as const },
  partial: { label: "Partial evidence", icon: WarningCircle, className: "text-warn", weight: "fill" as const },
  none: { label: "Nothing found", icon: MinusCircle, className: "text-ink-subtle", weight: "regular" as const },
};

/** For a question asked across several documents: how well each one answered it. */
export function DocumentEvidence({ documents }: { documents: DocumentCoverage[] }) {
  return (
    <section aria-label="Evidence by document" className="flex flex-col gap-2">
      <h3 className="text-[13px] font-medium text-ink-muted">Evidence by document</h3>
      <ul className="flex flex-col gap-1.5">
        {documents.map((document, index) => {
          const { label, icon: Icon, className, weight } = PRESENTATION[document.evidence];
          return (
            <li key={document.document_id} className="flex items-center gap-2 text-[13px]">
              <Icon size={16} weight={weight} className={className} aria-hidden />
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-surface-2 font-mono text-[10px] text-ink-muted">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-ink" title={document.name}>
                {document.name}
              </span>
              <span className={className}>{label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
