"use client";

import {
  CheckCircle,
  CloudSlash,
  FileDashed,
  FileX,
  LockSimple,
  Warning,
  type Icon,
} from "@phosphor-icons/react";
import { Button, LinkButton } from "@/components/ui/Button";
import { formatBytes, formatCount } from "@/lib/format";
import type { DocumentSummary, ErrorCode, UserFacingError } from "@/lib/types";
import type { FileInfo } from "@/hooks/useUpload";
import { FileBadge, kindFromName } from "./FileBadge";

const ERROR_PRESENTATION: Record<ErrorCode, { title: string; icon: Icon }> = {
  UNSUPPORTED_TYPE: { title: "This file type isn't supported", icon: FileX },
  FILE_TOO_LARGE: { title: "This file is too large", icon: FileX },
  EMPTY_FILE: { title: "This file is empty", icon: FileDashed },
  NO_TEXT: { title: "No readable text found", icon: FileDashed },
  PASSWORD_PROTECTED: { title: "This PDF is password protected", icon: LockSimple },
  CORRUPT_FILE: { title: "This file couldn't be read", icon: FileX },
  INTERRUPTED: { title: "Processing was interrupted", icon: Warning },
  NETWORK: { title: "Can't reach the server", icon: CloudSlash },
  AI_NOT_CONFIGURED: { title: "The AI provider is not set up", icon: Warning },
  TOO_MANY_DOCUMENTS: { title: "Too many documents selected", icon: Warning },
  DOCUMENT_NOT_READY: { title: "A document is not ready", icon: Warning },
  SAME_DOCUMENT: { title: "Choose two different documents", icon: Warning },
  INTERNAL: { title: "Something went wrong", icon: Warning },
  UNKNOWN: { title: "Something went wrong", icon: Warning },
};

interface ErrorViewProps {
  file: FileInfo | null;
  error: UserFacingError;
  onRetry: () => void;
}

export function ErrorView({ file, error, onRetry }: ErrorViewProps) {
  const { title, icon: ErrorIcon } = ERROR_PRESENTATION[error.code] ?? ERROR_PRESENTATION.UNKNOWN;

  return (
    <div
      role="alert"
      className="flex min-h-[19rem] flex-col justify-between gap-8 rounded-card border border-danger/40 bg-danger-soft p-6 sm:p-8"
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-ctl bg-surface text-danger">
            <ErrorIcon size={24} weight="duotone" aria-hidden />
          </span>
          <h2 className="text-xl font-semibold tracking-tight text-ink">{title}</h2>
        </div>
        <p className="max-w-[60ch] text-[15px] leading-relaxed text-ink">{error.message}</p>
        {file && (
          <p className="flex w-fit max-w-full items-center gap-2 rounded-ctl bg-surface px-3 py-2 text-[13px] text-ink-muted">
            <span className="truncate font-medium text-ink" title={file.name}>
              {file.name}
            </span>
            <span className="shrink-0 font-mono">{formatBytes(file.size)}</span>
          </p>
        )}
      </div>
      <div>
        <Button onClick={onRetry}>Choose another file</Button>
      </div>
    </div>
  );
}

interface SuccessViewProps {
  file: FileInfo;
  document: DocumentSummary;
  onReset: () => void;
}

export function SuccessView({ file, document, onReset }: SuccessViewProps) {
  const pages =
    document.page_count !== null
      ? `${formatCount(document.page_count)} ${document.page_count === 1 ? "page" : "pages"}`
      : "Word document";

  return (
    <div className="flex min-h-[19rem] flex-col justify-between gap-8 rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-ctl bg-success-soft text-success">
            <CheckCircle size={26} weight="fill" aria-hidden />
          </span>
          <h2 className="text-xl font-semibold tracking-tight text-ink" role="status">
            Added to your library
          </h2>
        </div>

        <div className="flex items-center gap-3">
          <FileBadge kind={kindFromName(file.name)} size={44} />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-medium text-ink" title={document.filename}>
              {document.filename}
            </p>
            <p className="flex flex-wrap gap-x-3 text-[13px] text-ink-subtle">
              <span>{pages}</span>
              <span>{formatCount(document.word_count)} words</span>
              <span>{formatBytes(document.size_bytes)}</span>
            </p>
          </div>
        </div>

        {document.empty_page_count > 0 && (
          <p className="flex items-start gap-2 rounded-ctl bg-warn-soft px-3 py-2.5 text-[13px] leading-relaxed text-warn">
            <Warning size={18} weight="fill" className="mt-px shrink-0" aria-hidden />
            {document.empty_page_count === 1
              ? "1 page had no readable text and may be a scan. Anything on it will not be searchable."
              : `${formatCount(document.empty_page_count)} pages had no readable text and may be scans. Anything on them will not be searchable.`}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <LinkButton href={`/documents/${document.id}`} variant="primary">
          Open document
        </LinkButton>
        <Button variant="secondary" onClick={onReset}>
          Upload another
        </Button>
      </div>
    </div>
  );
}
