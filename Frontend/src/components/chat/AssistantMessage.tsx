"use client";

import { ArrowClockwise, CircleNotch, Info, Stop, WarningOctagon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import type { ChatMessageView } from "@/hooks/useChat";
import { useSmoothedText } from "@/hooks/useSmoothedText";
import { formatCount } from "@/lib/format";
import type { AnswerQuality, Citation, Coverage } from "@/lib/types";
import { AgentTrace } from "./AgentTrace";
import { AnswerText } from "./AnswerText";
import { CitationCard } from "./CitationCard";

const QUALITY_BADGE: Partial<Record<AnswerQuality, { label: string; className: string }>> = {
  sufficient: { label: "Strong evidence", className: "bg-success-soft text-success" },
  partial: { label: "Partial evidence", className: "bg-warn-soft text-warn" },
  insufficient: { label: "Nothing found", className: "bg-surface-2 text-ink-muted" },
};

function CoverageLine({ coverage }: { coverage: Coverage }) {
  const pages = `${formatCount(coverage.pages)} ${coverage.pages === 1 ? "page" : "pages"}`;
  const sections = `${formatCount(coverage.sections)} sections`;
  const rounds = `${coverage.rounds} ${coverage.rounds === 1 ? "search round" : "search rounds"}`;
  return (
    <div className="flex flex-col gap-1 text-xs text-ink-subtle">
      <p className="font-mono tabular-nums">
        Searched {sections} across {pages}, {rounds}
      </p>
      {coverage.keyword_only && <p>Semantic search was unavailable, so keyword search was used.</p>}
      {coverage.unreadable_pages > 0 && (
        <p>
          {formatCount(coverage.unreadable_pages)} {coverage.unreadable_pages === 1 ? "page" : "pages"} had no
          readable text and could not be searched.
        </p>
      )}
    </div>
  );
}

interface AssistantMessageProps {
  message: ChatMessageView;
  activeCitation: { messageKey: string; n: number } | null;
  onOpenCitation: (messageKey: string, citation: Citation) => void;
  onRetry: (question: string) => void;
  retryDisabled: boolean;
}

export function AssistantMessage({
  message,
  activeCitation,
  onOpenCitation,
  onRetry,
  retryDisabled,
}: AssistantMessageProps) {
  const streaming = message.status === "streaming";
  const hasText = message.content.length > 0;
  const shownText = useSmoothedText(message.content, streaming);
  const latestStep = message.trace[message.trace.length - 1];
  const badge = message.quality ? QUALITY_BADGE[message.quality] : undefined;
  const unverified = message.citations.filter((citation) => !citation.verified).length;
  const citationId = (n: number) => `cite-${message.key}-${n}`;

  const handleSelectMarker = (n: number) => {
    const citation = message.citations.find((c) => c.n === n);
    if (citation?.verified) onOpenCitation(message.key, citation);
    document.getElementById(citationId(n))?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  return (
    <article className="flex flex-col gap-4" aria-label="Answer" aria-busy={streaming}>
      <AgentTrace steps={message.trace} working={streaming && !hasText} />

      {streaming && !hasText && message.trace.length === 0 && (
        <p className="text-[13px] text-ink-subtle" role="status">
          Starting
        </p>
      )}

      {hasText && (
        <AnswerText
          content={shownText}
          citations={message.citations}
          streaming={streaming}
          onSelectCitation={handleSelectMarker}
        />
      )}

      {streaming && hasText && latestStep && (
        <p className="flex items-center gap-2 text-[13px] text-ink-subtle" role="status">
          <CircleNotch size={14} weight="bold" className="animate-spin motion-reduce:animate-none" aria-hidden />
          {latestStep.text}
        </p>
      )}

      {message.status === "stopped" && (
        <p className="flex w-fit items-center gap-2 rounded-ctl bg-surface-2 px-3 py-2 text-[13px] text-ink-muted">
          <Stop size={14} weight="fill" aria-hidden />
          {hasText ? "Stopped. The partial answer above is kept, and its quotes were not checked." : "Stopped before an answer was written."}
        </p>
      )}

      {message.status === "error" && (
        <div role="alert" className="flex flex-col gap-3 rounded-card border border-danger/40 bg-danger-soft p-4">
          <p className="flex items-start gap-2 text-[14px] leading-relaxed text-ink">
            <WarningOctagon size={20} weight="fill" className="mt-px shrink-0 text-danger" aria-hidden />
            <span>
              {message.errorMessage ?? "Something went wrong while answering."}
              {hasText && " The partial answer above is kept and was not verified."}
            </span>
          </p>
          {message.question && message.errorCode !== "AI_NOT_CONFIGURED" && (
            <div>
              <Button
                variant="secondary"
                onClick={() => onRetry(message.question as string)}
                disabled={retryDisabled}
                className="min-h-10 px-3 text-[13px]"
              >
                <ArrowClockwise size={16} aria-hidden />
                Try again
              </Button>
            </div>
          )}
        </div>
      )}

      {badge && message.status === "complete" && (
        <div className="flex flex-wrap items-center gap-3">
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>{badge.label}</span>
        </div>
      )}

      {unverified > 0 && message.status === "complete" && (
        <p
          role="note"
          className="flex items-start gap-2 rounded-ctl bg-warn-soft px-3 py-2.5 text-[13px] leading-relaxed text-warn"
        >
          <Info size={16} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          {unverified === 1
            ? "1 quote could not be found in the document. Treat the claim that cites it with caution."
            : `${unverified} quotes could not be found in the document. Treat the claims that cite them with caution.`}
        </p>
      )}

      {message.citations.length > 0 && (
        <section aria-label="Quotes from the document" className="flex flex-col gap-3">
          <h3 className="text-[13px] font-medium text-ink-muted">Quotes</h3>
          <ul className="flex flex-col gap-3">
            {message.citations.map((citation) => (
              <CitationCard
                key={citation.n}
                id={citationId(citation.n)}
                citation={citation}
                active={activeCitation?.messageKey === message.key && activeCitation.n === citation.n}
                onOpen={(c) => onOpenCitation(message.key, c)}
              />
            ))}
          </ul>
        </section>
      )}

      {message.coverage && message.status === "complete" && message.quality !== "not_applicable" && (
        <CoverageLine coverage={message.coverage} />
      )}
    </article>
  );
}
