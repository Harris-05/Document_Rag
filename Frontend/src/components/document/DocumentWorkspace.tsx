"use client";

import { ArrowLeft, ChatsCircle, FileText, FileX } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChatPane } from "@/components/chat/ChatPane";
import { Button, LinkButton } from "@/components/ui/Button";
import { FileBadge } from "@/components/upload/FileBadge";
import { ApiError, getDocumentText } from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";
import type { Citation, DocumentDetail } from "@/lib/types";
import { DocumentPane, type Highlight } from "./DocumentPane";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; document: DocumentDetail }
  | { status: "missing" }
  | { status: "error"; message: string };

type MobileView = "chat" | "document";

export function WorkspaceSkeleton() {
  return (
    <div aria-hidden className="grid h-full gap-4 lg:grid-cols-2">
      <div className="rounded-card border border-line bg-surface p-6">
        <span className="skeleton block h-5 w-1/3 rounded-full" />
      </div>
      <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-6">
        {[92, 100, 85, 96, 70, 100, 88, 60].map((width, index) => (
          <span key={index} className="skeleton h-3.5 rounded-full" style={{ width: `${width}%` }} />
        ))}
      </div>
    </div>
  );
}

function Notice({ title, message, action }: { title: string; message: string; action: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="mx-auto mt-10 flex max-w-xl flex-col items-start gap-4 rounded-card border border-line bg-surface p-8 shadow-card"
    >
      <span className="grid size-12 place-items-center rounded-card bg-surface-2 text-ink-subtle">
        <FileX size={24} weight="duotone" aria-hidden />
      </span>
      <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
      <p className="max-w-[52ch] text-[15px] leading-relaxed text-ink-muted">{message}</p>
      {action}
    </div>
  );
}

export function DocumentWorkspace({ id }: { id: string }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", document: await getDocumentText(id) });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) setState({ status: "missing" });
      else
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "Could not load this document.",
        });
    }
  }, [id]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load on mount
    void load();
  }, [load]);

  if (state.status === "loading") return <WorkspaceSkeleton />;

  if (state.status === "missing") {
    return (
      <Notice
        title="Document not found"
        message="It may have been deleted, or it may still be processing. Head back to the library to see what is available."
        action={<LinkButton href="/">Back to library</LinkButton>}
      />
    );
  }

  if (state.status === "error") {
    return (
      <Notice
        title="Couldn't load this document"
        message={state.message}
        action={<Button onClick={() => void load()}>Try again</Button>}
      />
    );
  }

  return <Workspace document={state.document} />;
}

function Workspace({ document }: { document: DocumentDetail }) {
  const [view, setView] = useState<MobileView>("chat");
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [active, setActive] = useState<{ messageKey: string; n: number } | null>(null);

  const openCitation = useCallback((messageKey: string, citation: Citation) => {
    setActive({ messageKey, n: citation.n });
    setHighlight((previous) => ({ ranges: citation.ranges, token: (previous?.token ?? 0) + 1 }));
    setView("document");
  }, []);

  const paneBase = "min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-line bg-surface shadow-card lg:flex";

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link
          href="/"
          className="-ml-2 flex min-h-11 items-center gap-2 rounded-ctl px-2 text-sm text-ink-muted transition-colors hover:text-ink"
        >
          <ArrowLeft size={16} aria-hidden />
          Library
        </Link>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <FileBadge kind={document.file_kind} size={36} />
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold tracking-tight text-ink" title={document.filename}>
              {document.filename}
            </h1>
            <p className="flex flex-wrap gap-x-3 text-xs text-ink-subtle">
              {document.page_count !== null && (
                <span>
                  {formatCount(document.page_count)} {document.page_count === 1 ? "page" : "pages"}
                </span>
              )}
              <span>{formatCount(document.word_count)} words</span>
              <span>{formatBytes(document.size_bytes)}</span>
            </p>
          </div>
        </div>

        <div role="tablist" aria-label="Switch view" className="flex rounded-ctl bg-surface-2 p-1 lg:hidden">
          {(
            [
              ["chat", "Chat", ChatsCircle],
              ["document", "Document", FileText],
            ] as const
          ).map(([key, label, TabIcon]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-[7px] px-3.5 text-sm font-medium transition-colors ${
                view === key ? "bg-surface text-ink shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              <TabIcon size={16} aria-hidden />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <section aria-label="Chat" className={`${paneBase} ${view === "chat" ? "flex" : "hidden"}`}>
          <ChatPane documentId={document.id} activeCitation={active} onOpenCitation={openCitation} />
        </section>
        <section aria-label="Document" className={`${paneBase} ${view === "document" ? "flex" : "hidden"}`}>
          <DocumentPane document={document} highlight={highlight} />
        </section>
      </div>
    </div>
  );
}
