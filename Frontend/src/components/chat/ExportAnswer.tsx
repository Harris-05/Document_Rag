"use client";

import { CircleNotch, DownloadSimple, FileDoc, FilePdf } from "@phosphor-icons/react";
import { useState } from "react";
import { ApiError, exportAnswer, type ExportFormat } from "@/lib/api";

const FORMATS: { value: ExportFormat; label: string; Icon: typeof FilePdf }[] = [
  { value: "pdf", label: "PDF", Icon: FilePdf },
  { value: "docx", label: "Word", Icon: FileDoc },
];

function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next turn so the browser has started the download first.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Download this answer, with each quote and whether it was verified, as a PDF or a Word file. */
export function ExportAnswer({ messageId }: { messageId: number }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const download = async (format: ExportFormat) => {
    if (busy) return;
    setBusy(format);
    setError(null);
    try {
      const { blob, filename } = await exportAnswer(messageId, format);
      saveFile(blob, filename);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not export this answer. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div role="group" aria-label="Export this answer" className="flex items-center gap-0.5">
        <span className="mr-1 flex items-center gap-1.5 text-[12px] text-ink-subtle">
          <DownloadSimple size={14} aria-hidden />
          Export
        </span>
        {FORMATS.map(({ value, label, Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => void download(value)}
            disabled={busy !== null}
            aria-label={`Export as ${label}`}
            title={`Download this answer with its quotes as a ${label === "Word" ? "Word document" : "PDF"}`}
            className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-full px-3 text-[12px] font-medium text-ink-muted transition-[background-color,color,transform] duration-150 hover:bg-surface-2 hover:text-ink active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === value ? (
              <CircleNotch size={14} weight="bold" className="animate-spin motion-reduce:animate-none" aria-hidden />
            ) : (
              <Icon size={15} aria-hidden />
            )}
            {busy === value ? "Preparing" : label}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-[12px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
