"use client";

import { Trash, Warning } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { FileBadge } from "@/components/upload/FileBadge";
import { formatBytes, formatCount, formatRelativeTime } from "@/lib/format";
import type { DocumentSummary } from "@/lib/types";

interface DocumentRowProps {
  document: DocumentSummary;
  onDelete: (id: string) => Promise<string | null>;
}

export function DocumentRow({ document, onDelete }: DocumentRowProps) {
  const reduceMotion = useReducedMotion();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const processing = document.status === "processing";
  const pages =
    document.page_count !== null
      ? `${formatCount(document.page_count)} ${document.page_count === 1 ? "page" : "pages"}`
      : "Word document";

  const confirmDelete = async () => {
    setDeleting(true);
    const failure = await onDelete(document.id);
    if (failure) {
      setDeleteError(failure);
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <motion.li
      layout={reduceMotion ? false : "position"}
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col gap-3 px-4 py-4 sm:px-5"
    >
      <div className="flex items-center gap-3">
        <FileBadge kind={document.file_kind} />
        <div className="min-w-0 flex-1">
          {processing ? (
            <p className="truncate text-[15px] font-medium text-ink" title={document.filename}>
              {document.filename}
            </p>
          ) : (
            <Link
              href={`/documents/${document.id}`}
              className="block truncate rounded-ctl text-[15px] font-medium text-ink hover:text-accent"
              title={document.filename}
            >
              {document.filename}
            </Link>
          )}
          {!processing && (
            <p className="mt-0.5 flex flex-wrap gap-x-3 text-[13px] text-ink-subtle">
              <span>{pages}</span>
              <span>{formatCount(document.word_count)} words</span>
              <span>{formatBytes(document.size_bytes)}</span>
              <span>{formatRelativeTime(document.created_at)}</span>
            </p>
          )}
        </div>
        {!processing && !confirming && (
          <button
            type="button"
            onClick={() => {
              setDeleteError(null);
              setConfirming(true);
            }}
            aria-label={`Delete ${document.filename}`}
            className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-ctl text-ink-subtle transition-colors duration-150 hover:bg-danger-soft hover:text-danger"
          >
            <Trash size={20} aria-hidden />
          </button>
        )}
      </div>

      {processing && (
        <div className="flex flex-col gap-2">
          <ProgressBar
            label={`Processing ${document.filename}`}
            value={
              document.progress_total ? document.progress_done / document.progress_total : 0.4
            }
          />
          <p className="text-[13px] text-ink-subtle" role="status">
            {document.progress_total && document.progress_done > 0
              ? `Reading page ${formatCount(document.progress_done)} of ${formatCount(document.progress_total)}`
              : "Reading the document text"}
          </p>
        </div>
      )}

      {document.empty_page_count > 0 && !processing && (
        <p className="flex w-fit items-center gap-1.5 rounded-full bg-warn-soft px-2.5 py-1 text-xs text-warn">
          <Warning size={14} weight="fill" aria-hidden />
          {document.empty_page_count === 1
            ? "1 page without readable text"
            : `${formatCount(document.empty_page_count)} pages without readable text`}
        </p>
      )}

      {confirming && (
        <div
          role="group"
          aria-label={`Confirm deleting ${document.filename}`}
          className="flex flex-wrap items-center justify-between gap-3 rounded-ctl bg-danger-soft px-3 py-2"
        >
          <p className="text-sm text-ink">Delete this document and its saved text?</p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={deleting}>
              Keep
            </Button>
            <Button variant="danger" onClick={confirmDelete} disabled={deleting}>
              {deleting ? "Deleting" : "Delete"}
            </Button>
          </div>
        </div>
      )}

      {deleteError && (
        <p role="alert" className="text-[13px] text-danger">
          {deleteError}
        </p>
      )}
    </motion.li>
  );
}
