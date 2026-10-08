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
      className={`flex min-h-[19rem] flex-col items-center justify-center gap-6 rounded-card border border-dashed px-6 py-10 text-center transition-colors duration-200 ${
        dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-surface"
      }`}
    >
      <span
        className={`grid size-14 place-items-center rounded-card transition-colors duration-200 ${
          dragging ? "bg-accent text-accent-ink" : "bg-accent-soft text-accent"
        }`}
      >
        <UploadSimple size={26} weight="bold" aria-hidden />
      </span>

      <div className="flex flex-col items-center gap-2">
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
        <Button onClick={() => inputRef.current?.click()} className="px-6">
          Upload PDF or DOCX
        </Button>
        <p className="text-sm text-ink-muted" aria-live="polite">
          {dragging ? "Release to upload" : "or drop a file here"}
        </p>
      </div>

      <p className="text-[13px] text-ink-subtle">PDF or DOCX, up to {MAX_UPLOAD_MB} MB</p>
    </div>
  );
}
