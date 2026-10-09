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
}

export interface TraceStep {
  kind: string;
  round: number | null;
  text: string;
  detail: Record<string, unknown> | null;
}

export interface Coverage {
  pages: number;
  sections: number;
  unreadable_pages: number;
  rounds: number;
  keyword_only: boolean;
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
