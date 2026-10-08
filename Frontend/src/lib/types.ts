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
  | "NETWORK"
  | "UNKNOWN";

export interface UserFacingError {
  code: ErrorCode;
  message: string;
}
