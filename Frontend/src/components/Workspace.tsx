"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState, useTransition } from "react";
import { ConversationList } from "@/components/library/ConversationList";
import { LibraryPanel } from "@/components/library/LibraryPanel";
import { UploadPanel } from "@/components/upload/UploadPanel";
import { useConversations } from "@/hooks/useConversations";
import { useDocuments } from "@/hooks/useDocuments";
import { useUpload } from "@/hooks/useUpload";
import { ApiError, createConversation } from "@/lib/api";
import { pruneSelection, toggleSelection } from "@/lib/selection";

export function Workspace() {
  const router = useRouter();
  const { documents, status, error, refresh, remove } = useDocuments();
  const comparisons = useConversations();
  const upload = useUpload(refresh);

  const [chosen, setChosen] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [navigating, startNavigation] = useTransition();
  const [compareError, setCompareError] = useState<string | null>(null);
  // "Opening" lasts only while the comparison is being created and the page is on its way. It is
  // not stored as a flag that outlives the trip: this page stays mounted when you come back to it.
  const comparing = creating || navigating;

  // The panel on the left already shows live progress for the file being processed,
  // so keep it out of the library list until it has finished.
  const activeId = upload.state.phase === "processing" ? upload.state.document.id : null;
  const visibleDocuments = documents.filter((document) => document.id !== activeId);

  // A document that was deleted can no longer be part of a selection, so it is dropped on the way
  // out rather than kept in sync with an effect.
  const readyIds = useMemo(
    () => documents.filter((document) => document.status === "ready").map((document) => document.id),
    [documents],
  );
  const selected = useMemo(() => (status === "ready" ? pruneSelection(chosen, readyIds) : chosen), [chosen, readyIds, status]);

  const toggle = useCallback(
    (id: string) => {
      setCompareError(null);
      setChosen((current) => toggleSelection(pruneSelection(current, readyIds), id));
    },
    [readyIds],
  );

  const removeDocument = useCallback(
    async (id: string) => {
      const failure = await remove(id);
      // Deleting a document can remove comparisons that depended on it.
      await comparisons.refresh();
      return failure;
    },
    [remove, comparisons],
  );

  const compare = useCallback(async () => {
    setCreating(true);
    setCompareError(null);
    try {
      const conversation = await createConversation(selected);
      // The documents are now in a comparison. Starting fresh means that coming back to choose
      // two others does not find the old choice still ticked.
      setChosen([]);
      startNavigation(() => router.push(`/conversations/${conversation.id}`));
    } catch (caught) {
      setCompareError(caught instanceof ApiError ? caught.message : "Could not start the comparison.");
    } finally {
      setCreating(false);
    }
  }, [router, selected]);

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

      <div className="flex flex-col gap-10 lg:col-span-5 lg:pt-6">
        <LibraryPanel
          documents={visibleDocuments}
          status={status}
          error={error}
          onRetry={refresh}
          onDelete={removeDocument}
          selected={selected}
          onToggleSelected={toggle}
          onClearSelection={() => setChosen([])}
          onCompare={compare}
          comparing={comparing}
          compareError={compareError}
        />
        <ConversationList conversations={comparisons.conversations} onDelete={comparisons.remove} />
      </div>
    </div>
  );
}
