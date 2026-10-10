export type DocumentStatus = "processing" | "ready" | "failed";
export type FileKind = "pdf" | "docx";

export interface DocumentSummary {
  id: string;
  filename: string;
  file_kind: FileKind;
  size_bytes: number;
  status: DocumentStatus;
  stage: string;
  progress_done: number;
  progress_total: number | null;
  page_count: number | null;
  empty_page_count: number;
  word_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
}

export interface PageText {
  page_number: number;
  text: string;
}

export interface DocumentDetail extends DocumentSummary {
  char_count: number;
  pages: PageText[];
}

export type ErrorCode =
  | "UNSUPPORTED_TYPE"
  | "FILE_TOO_LARGE"
  | "EMPTY_FILE"
  | "NO_TEXT"
  | "PASSWORD_PROTECTED"
  | "CORRUPT_FILE"
  | "INTERRUPTED"
  | "INTERNAL"
  | "AI_NOT_CONFIGURED"
  | "TOO_MANY_DOCUMENTS"
  | "DOCUMENT_NOT_READY"
  | "SAME_DOCUMENT"
  | "NETWORK"
  | "UNKNOWN";

export interface UserFacingError {
  code: ErrorCode;
  message: string;
}

export type AnswerQuality = "sufficient" | "partial" | "insufficient" | "not_applicable";

export interface CitationRange {
  page: number;
  start: number;
  end: number;
}

export interface Citation {
  n: number;
  quote: string;
  verified: boolean;
  page: number | null;
  /** The match to show first. Kept for older saved messages that have no `matches`. */
  ranges: CitationRange[];
  /** Every place the quote occurs, in document order. Each match may span pages. */
  matches: CitationRange[][];
  primary_index: number;
  occurrences: number;
  /** Which document the quote belongs to. Set for every quote, in one-document and multi-document chats. */
  document_id?: string | null;
  document_name?: string | null;
  /** The short label used inside the prompt (D1, D2). Only for comparisons. */
  document_label?: string | null;
}

export interface TraceStep {
  kind: string;
  round: number | null;
  text: string;
  detail: Record<string, unknown> | null;
}

export interface DocumentCoverage {
  document_id: string;
  name: string;
  pages: number;
  sections: number;
  unreadable_pages: number;
  evidence: "sufficient" | "partial" | "none";
}

/** "standard" grades retrieval in a fixed loop; "research" lets the model call tools to look things up. */
export type ChatMode = "standard" | "research";

export interface Coverage {
  pages: number;
  sections: number;
  unreadable_pages: number;
  rounds: number;
  /** Tool calls the model made. Present in research mode only. */
  tool_calls?: number;
  keyword_only: boolean;
  /** Per-document results, present when a question was asked across several documents. */
  documents?: DocumentCoverage[] | null;
}

/** A chat about one document ("single") or several ("multi"). */
export interface Conversation {
  id: string;
  kind: "single" | "multi";
  created_at: string;
  message_count: number;
  documents: DocumentSummary[];
}

export interface ServerChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "stopped" | "error";
  quality: AnswerQuality | null;
  citations: Citation[];
  trace: TraceStep[];
  coverage: Coverage | null;
  error_message: string | null;
  created_at: string;
}

/** Events streamed by POST /api/documents/{id}/chat. */
export type ChatEvent =
  | { event: "start"; data: { user_message_id: number } }
  | { event: "step"; data: TraceStep }
  | { event: "token"; data: { text: string } }
  | { event: "citations"; data: Citation[] }
  | {
      event: "done";
      data: {
        quality: AnswerQuality;
        coverage: Coverage;
        verification: { verified: number; unverified: number } | null;
        message_id: number;
      };
    }
  | { event: "error"; data: { message: string; message_id?: number } };

// ---- Comparing two versions of a contract ----

export type Significance = "critical" | "major" | "minor" | "cosmetic" | "unrated";
export type ChangeType = "modified" | "added" | "removed" | "moved";

export interface DocumentBrief {
  id: string;
  filename: string;
  file_kind: FileKind;
  page_count: number | null;
}

export interface FigureChange {
  kind: "money" | "percent" | "duration" | "date" | string;
  old: string | null;
  new: string | null;
}

export interface ObligationChange {
  word: string;
  old: number;
  new: number;
}

export interface ChangeSide {
  text: string;
  heading: string;
  page: number;
  ranges: CitationRange[];
}

export interface DiffSegment {
  op: "equal" | "delete" | "insert";
  text: string;
}

export interface Change {
  id: number;
  type: ChangeType;
  moved: boolean;
  significance: Significance;
  ai_rated: boolean;
  raised_by_rules: boolean;
  category: string;
  title: string;
  summary: string;
  similarity: number;
  figures: FigureChange[];
  figure_text: string[];
  obligations: ObligationChange[];
  old: ChangeSide | null;
  new: ChangeSide | null;
  diff: DiffSegment[];
  /** Reading order in the new version, with removed clauses placed where they used to be. */
  position: number;
}

export interface ComparisonStats {
  old_clauses: number;
  new_clauses: number;
  unchanged: number;
  modified: number;
  added: number;
  removed: number;
  moved: number;
  by_significance: Record<string, number>;
}

export interface ComparisonSummary {
  id: string;
  old_document: DocumentBrief;
  new_document: DocumentBrief;
  status: DocumentStatus;
  stage: string;
  progress_done: number;
  progress_total: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  stats: ComparisonStats | null;
  ai_used: boolean | null;
}

export interface ComparisonDetail extends ComparisonSummary {
  summary: { headline: string; key_points: string[] } | null;
  ai_notice: string | null;
  changes: Change[];
}
