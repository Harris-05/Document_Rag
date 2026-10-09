import { Lightbulb } from "@phosphor-icons/react/dist/ssr";
import type { Citation } from "@/lib/types";
import { splitCitations, splitExplanation, splitParagraphs } from "@/lib/messageText";

interface AnswerTextProps {
  content: string;
  citations: Citation[];
  streaming: boolean;
  onSelectCitation: (n: number) => void;
}

function Marker({ n, citation, onSelect }: { n: number; citation?: Citation; onSelect: (n: number) => void }) {
  const tone = !citation
    ? "bg-surface-2 text-ink-subtle"
    : citation.verified
      ? "bg-accent-soft text-accent hover:brightness-95"
      : "bg-warn-soft text-warn hover:brightness-95";
  const label = !citation
    ? `Citation ${n}`
    : citation.verified
      ? `Citation ${n}, verified. Show quote`
      : `Citation ${n}, not verified. Show quote`;

  return (
    <button
      type="button"
      onClick={() => onSelect(n)}
      disabled={!citation}
      aria-label={label}
      className={`mx-0.5 inline-grid min-w-6 -translate-y-px cursor-pointer place-items-center rounded-full px-1.5 py-px align-baseline font-mono text-[11px] font-medium transition-[filter] disabled:cursor-default ${tone}`}
    >
      {n}
    </button>
  );
}

function Caret() {
  return (
    <span
      aria-hidden
      className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[3px] animate-pulse bg-ink motion-reduce:animate-none"
    />
  );
}

interface ParagraphsProps {
  text: string;
  byNumber: Map<number, Citation>;
  caret: boolean;
  onSelectCitation: (n: number) => void;
  markers: boolean;
}

function Paragraphs({ text, byNumber, caret, onSelectCitation, markers }: ParagraphsProps) {
  const paragraphs = splitParagraphs(text);
  return (
    <>
      {paragraphs.map((paragraph, paragraphIndex) => (
        <p key={paragraphIndex} className="max-w-[68ch] whitespace-pre-wrap">
          {markers ? (
            splitCitations(paragraph).map((part, partIndex) =>
              part.type === "text" ? (
                <span key={partIndex}>{part.value}</span>
              ) : (
                <Marker key={partIndex} n={part.n} citation={byNumber.get(part.n)} onSelect={onSelectCitation} />
              ),
            )
          ) : (
            paragraph
          )}
          {caret && paragraphIndex === paragraphs.length - 1 && <Caret />}
        </p>
      ))}
    </>
  );
}

export function AnswerText({ content, citations, streaming, onSelectCitation }: AnswerTextProps) {
  const byNumber = new Map(citations.map((citation) => [citation.n, citation]));
  const { answer, explanation } = splitExplanation(content);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 text-[15px] leading-7 text-ink">
        <Paragraphs
          text={answer}
          byNumber={byNumber}
          caret={streaming && explanation === null}
          onSelectCitation={onSelectCitation}
          markers
        />
      </div>

      {explanation !== null && (
        <aside
          aria-label="General explanation, not from the document"
          className="flex flex-col gap-2 rounded-card border border-line bg-surface-2 p-4"
        >
          <p className="flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            <Lightbulb size={14} weight="fill" aria-hidden />
            General explanation, not from the document
          </p>
          <div className="flex flex-col gap-3 text-[14px] leading-relaxed text-ink-muted">
            <Paragraphs
              text={explanation}
              byNumber={byNumber}
              caret={streaming}
              onSelectCitation={onSelectCitation}
              markers={false}
            />
          </div>
        </aside>
      )}
    </div>
  );
}
