"use client";

import { ArrowLeft, ChatsCircle, FileText, Info } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatPane } from "@/components/chat/ChatPane";
import { Button, LinkButton } from "@/components/ui/Button";
import { ApiError, getConversation, getDocumentText } from "@/lib/api";
import { conversationChatSource } from "@/lib/chatSource";
import type { Citation, Conversation, DocumentDetail } from "@/lib/types";
import { matchesOf, type ViewerTarget } from "@/lib/viewerTarget";
import { DocumentViewer } from "./DocumentViewer";
import { Notice, WorkspaceSkeleton } from "./DocumentWorkspace";

type ConversationState =
  | { status: "loading" }
  | { status: "ready"; conversation: Conversation }
  | { status: "missing" }
  | { status: "error"; message: string };

type DetailState = { status: "ready"; document: DocumentDetail } | { status: "error"; message: string };

type MobileView = "chat" | "document";

export function ConversationWorkspace({ id }: { id: string }) {
  const [state, setState] = useState<ConversationState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", conversation: await getConversation(id) });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) setState({ status: "missing" });
      else
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "Could not load this comparison.",
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
        title="Comparison not found"
        message="It may have been deleted, or all of its documents may have been removed."
        action={<LinkButton href="/">Back to library</LinkButton>}
      />
    );
  }
  if (state.status === "error") {
    return (
      <Notice
        title="Couldn't load this comparison"
        message={state.message}
        action={<Button onClick={() => void load()}>Try again</Button>}
      />
    );
  }
  return <Comparison conversation={state.conversation} />;
}

function DocumentTabs({
  documents,
  activeId,
  onSelect,
}: {
  documents: Conversation["documents"];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div role="tablist" aria-label="Documents in this comparison" className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2">
      {documents.map((document, index) => (
        <button
          key={document.id}
          type="button"
          role="tab"
          aria-selected={document.id === activeId}
          onClick={() => onSelect(document.id)}
          className={`flex min-h-10 max-w-56 shrink-0 cursor-pointer items-center gap-2 rounded-ctl px-3 text-[13px] font-medium transition-colors ${
            document.id === activeId ? "bg-accent-soft text-accent" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
          }`}
        >
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-surface font-mono text-[10px]">{index + 1}</span>
          <span className="truncate" title={document.filename}>
            {document.filename}
          </span>
        </button>
      ))}
    </div>
  );
}

function Comparison({ conversation }: { conversation: Conversation }) {
  const source = useMemo(() => conversationChatSource(conversation.id), [conversation.id]);
  const [view, setView] = useState<MobileView>("chat");
  const [activeDocumentId, setActiveDocumentId] = useState(conversation.documents[0]?.id ?? "");
  const [details, setDetails] = useState<Record<string, DetailState>>({});
  const [target, setTarget] = useState<ViewerTarget | null>(null);
  const [active, setActive] = useState<{ messageKey: string; n: number } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requested = useRef(new Set<string>());

  // Each document's text is fetched the first time it is needed, not all up front.
  const ensureLoaded = useCallback((documentId: string) => {
    if (!documentId || requested.current.has(documentId)) return;
    requested.current.add(documentId);
    getDocumentText(documentId)
      .then((document) => setDetails((current) => ({ ...current, [documentId]: { status: "ready", document } })))
      .catch((error: unknown) =>
        setDetails((current) => ({
          ...current,
          [documentId]: {
            status: "error",
            message: error instanceof ApiError ? error.message : "Could not load this document.",
          },
        })),
      );
  }, []);

  useEffect(() => {
    ensureLoaded(activeDocumentId);
  }, [activeDocumentId, ensureLoaded]);

  const retry = (documentId: string) => {
    requested.current.delete(documentId);
    setDetails((current) => {
      const next = { ...current };
      delete next[documentId];
      return next;
    });
    ensureLoaded(documentId);
  };

  const openCitation = useCallback(
    (messageKey: string, citation: Citation) => {
      const documentId = citation.document_id ?? conversation.documents[0]?.id;
      const matches = matchesOf(citation);
      if (!documentId || matches.length === 0) return;
      if (!conversation.documents.some((document) => document.id === documentId)) {
        setNotice(`${citation.document_name ?? "That document"} has been deleted, so this quote can no longer be opened.`);
        return;
      }
      setNotice(null);
      setActive({ messageKey, n: citation.n });
      setActiveDocumentId(documentId);
      setTarget((previous) => ({
        token: (previous?.token ?? 0) + 1,
        citationKey: `${messageKey}:${citation.n}`,
        documentId,
        matches,
        index: Math.min(Math.max(citation.primary_index ?? 0, 0), matches.length - 1),
      }));
      setView("document");
    },
    [conversation.documents],
  );

  const stepMatch = useCallback((delta: number) => {
    setTarget((previous) => {
      if (!previous) return previous;
      const count = previous.matches.length;
      return { ...previous, token: previous.token + 1, index: (previous.index + delta + count) % count };
    });
  }, []);

  const detail = details[activeDocumentId];
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
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold tracking-tight text-ink">
            Comparing {conversation.documents.length} {conversation.documents.length === 1 ? "document" : "documents"}
          </h1>
          <p className="truncate text-xs text-ink-subtle">{conversation.documents.map((d) => d.filename).join(", ")}</p>
        </div>

        <div role="tablist" aria-label="Switch view" className="flex rounded-ctl bg-surface-2 p-1 lg:hidden">
          {(
            [
              ["chat", "Chat", ChatsCircle],
              ["document", "Documents", FileText],
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
          <ChatPane source={source} multi activeCitation={active} onOpenCitation={openCitation} />
        </section>

        <section aria-label="Documents" className={`${paneBase} ${view === "document" ? "flex" : "hidden"}`}>
          <DocumentTabs documents={conversation.documents} activeId={activeDocumentId} onSelect={setActiveDocumentId} />
          {notice && (
            <p role="note" className="flex items-start gap-2 bg-warn-soft px-4 py-2.5 text-[13px] leading-relaxed text-warn sm:px-6">
              <Info size={16} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
              {notice}
            </p>
          )}
          {detail === undefined && (
            <div role="status" aria-label="Loading document" className="flex flex-1 flex-col items-center gap-3 px-6 py-10">
              {[100, 92, 96, 70].map((width, index) => (
                <span key={index} className="skeleton h-3.5 rounded-full" style={{ width: `${width}%`, maxWidth: 520 }} />
              ))}
            </div>
          )}
          {detail?.status === "error" && (
            <div role="alert" className="flex flex-col items-start gap-3 p-6">
              <p className="text-[15px] text-ink">{detail.message}</p>
              <Button variant="secondary" onClick={() => retry(activeDocumentId)}>
                Try again
              </Button>
            </div>
          )}
          {detail?.status === "ready" && (
            <DocumentViewer
              key={detail.document.id}
              document={detail.document}
              target={target?.documentId === activeDocumentId ? target : null}
              onStepMatch={stepMatch}
            />
          )}
        </section>
      </div>
    </div>
  );
}
