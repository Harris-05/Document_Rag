"use client";

import { LibraryPanel } from "@/components/library/LibraryPanel";
import { UploadPanel } from "@/components/upload/UploadPanel";
import { useDocuments } from "@/hooks/useDocuments";
import { useUpload } from "@/hooks/useUpload";

export function Workspace() {
  const { documents, status, error, refresh, remove } = useDocuments();
  const upload = useUpload(refresh);

  // The panel on the left already shows live progress for the file being processed,
  // so keep it out of the library list until it has finished.
  const activeId = upload.state.phase === "processing" ? upload.state.document.id : null;
  const visibleDocuments = documents.filter((document) => document.id !== activeId);

  return (
    <div className="grid gap-12 lg:grid-cols-12 lg:gap-14">
      <section className="flex flex-col gap-8 lg:col-span-7 lg:pt-6">
        <div className="flex flex-col gap-4">
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-tighter text-ink md:text-5xl">
            Bring in a contract.
          </h1>
          <p className="max-w-[46ch] text-base leading-relaxed text-ink-muted">
            Upload a PDF or Word file. The text is extracted and saved to your library.
          </p>
        </div>
        <UploadPanel
          state={upload.state}
          onFiles={upload.start}
          onCancel={upload.cancel}
          onReset={upload.reset}
        />
      </section>

      <div className="lg:col-span-5 lg:pt-6">
        <LibraryPanel
          documents={visibleDocuments}
          status={status}
          error={error}
          onRetry={refresh}
          onDelete={remove}
        />
      </div>
    </div>
  );
}
