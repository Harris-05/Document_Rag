import type { DiffSegment } from "@/lib/types";

interface DiffTextProps {
  segments: DiffSegment[];
  /** Which version to show: the old text marks what was removed, the new text marks what was added. */
  side: "old" | "new";
  /** Used when there is no word diff, for a clause that exists in only one version. */
  fallback: string;
}

/**
 * One version of a changed clause with its changed words marked. The two sides are shown next to each
 * other so the reader can see what the clause said and what it says now.
 */
export function DiffText({ segments, side, fallback }: DiffTextProps) {
  if (segments.length === 0) return <>{fallback}</>;
  const keep = side === "old" ? "delete" : "insert";
  return (
    <>
      {segments
        .filter((segment) => segment.op === "equal" || segment.op === keep)
        .map((segment, index) => {
          const text = index > 0 ? ` ${segment.text}` : segment.text;
          if (segment.op === "equal") return <span key={index}>{text}</span>;
          return side === "old" ? (
            <del key={index} className="diff-del">
              {text}
            </del>
          ) : (
            <ins key={index} className="diff-ins no-underline">
              {text}
            </ins>
          );
        })}
    </>
  );
}
