"use client";

import { UploadSimple } from "@phosphor-icons/react";
import { type DragEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ACCEPT_ATTRIBUTE, MAX_UPLOAD_MB } from "@/lib/validation";

interface DropzoneProps {
  onFiles: (files: File[]) => void;
}

export function Dropzone({ onFiles }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");

  const handleDragEnter = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };

  const handleDragLeave = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const handleDrop = (event: DragEvent) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    onFiles(Array.from(event.dataTransfer.files));
  };

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={(event) => hasFiles(event) && event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex min-h-[14rem] flex-col items-center justify-center gap-5 rounded-card border border-dashed px-6 py-10 text-center transition-[background-color,border-color] duration-200 md:flex-row md:justify-between md:gap-8 md:px-10 md:text-left ${
        dragging ? "border-ink bg-surface-2" : "border-line-strong bg-surface hover:border-ink-subtle"
      }`}
    >
      <div className="flex flex-col items-center gap-4 md:flex-row md:gap-6">
        <span
          className={`grid size-14 shrink-0 place-items-center rounded-full transition-colors duration-200 ${
            dragging ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink"
          }`}
        >
          <UploadSimple size={24} weight="bold" aria-hidden />
        </span>
        <div className="flex flex-col gap-1.5">
          <h2 className="text-lg font-medium tracking-tight text-ink" aria-live="polite">
            {dragging ? "Release to upload" : "Drop a contract here"}
          </h2>
          <p className="text-sm text-ink-muted">
            PDF or Word (DOCX), up to {MAX_UPLOAD_MB} MB. Scanned pages without text can&apos;t be read.
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => {
            onFiles(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
        <Button onClick={() => inputRef.current?.click()} className="rounded-full px-7">
          Upload PDF or DOCX
        </Button>
        <p className="text-xs text-ink-subtle">or drag and drop</p>
      </div>
    </div>
  );
}
