"use client";

import { ArrowLeft, FileX, Warning } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, getDocumentText } from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";
import { Button, LinkButton } from "@/components/ui/Button";
import { FileBadge } from "@/components/upload/FileBadge";

type State =
  | { status: "loading" }
  | { status: "ready"; document: DocumentDetail }
  | { status: "missing" }
  | { status: "error"; message: string };

export function ReaderSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-8">
      <div className="flex items-center gap-4">
        <span className="skeleton size-12 rounded-ctl" />
        <span className="flex flex-1 flex-col gap-2">
          <span className="skeleton h-5 w-1/2 rounded-full" />
          <span className="skeleton h-3.5 w-1/3 rounded-full" />
        </span>
      </div>
      <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-8">
        {[92, 100, 85, 96, 70, 100, 88, 60].map((width, index) => (
          <span key={index} className="skeleton h-3.5 rounded-full" style={{ width: `${width}%` }} />
        ))}
      </div>
    </div>
  );
}

function Notice({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-8 shadow-card"
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

export function DocumentReader({ id }: { id: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

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

  return (
    <div className="flex flex-col gap-8">
      <Link
        href="/"
        className="-ml-2 flex min-h-11 w-fit items-center gap-2 rounded-ctl px-2 text-sm text-ink-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={16} aria-hidden />
        Library
      </Link>

      {state.status === "loading" && <ReaderSkeleton />}

      {state.status === "missing" && (
        <Notice
          title="Document not found"
          message="It may have been deleted, or it may still be processing. Head back to the library to see what is available."
          action={<LinkButton href="/">Back to library</LinkButton>}
        />
      )}

      {state.status === "error" && (
        <Notice
          title="Couldn't load this document"
          message={state.message}
          action={<Button onClick={() => void load()}>Try again</Button>}
        />
      )}

      {state.status === "ready" && <ReaderBody document={state.document} />}
    </div>
  );
}

function ReaderBody({ document }: { document: DocumentDetail }) {
  const showPageLabels = document.file_kind === "pdf";

  return (
    <>
      <header className="flex items-center gap-4">
        <FileBadge kind={document.file_kind} size={48} />
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight text-ink" title={document.filename}>
            {document.filename}
          </h1>
          <p className="mt-1 flex flex-wrap gap-x-4 text-sm text-ink-subtle">
            {document.page_count !== null && (
              <span>
                {formatCount(document.page_count)} {document.page_count === 1 ? "page" : "pages"}
              </span>
            )}
            <span>{formatCount(document.word_count)} words</span>
            <span>{formatBytes(document.size_bytes)}</span>
          </p>
        </div>
      </header>

      {document.empty_page_count > 0 && (
        <p
          role="note"
          className="flex items-start gap-2 rounded-ctl bg-warn-soft px-4 py-3 text-sm leading-relaxed text-warn"
        >
          <Warning size={18} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
          {document.empty_page_count === 1
            ? "1 page in this PDF had no readable text and may be a scan. It is shown below as empty."
            : `${formatCount(document.empty_page_count)} pages in this PDF had no readable text and may be scans. They are shown below as empty.`}
        </p>
      )}

      <article aria-label="Extracted text" className="flex flex-col gap-4">
        {document.pages.map((page) => (
          <section
            key={page.page_number}
            id={`page-${page.page_number}`}
            className="page-block rounded-card border border-line bg-surface p-6 sm:p-8"
          >
            {showPageLabels && (
              <p className="mb-4 font-mono text-xs tabular-nums text-ink-subtle">
                Page {page.page_number}
              </p>
            )}
            {page.text ? (
              <p className="max-w-[75ch] whitespace-pre-wrap text-[15px] leading-7 text-ink">
                {page.text}
              </p>
            ) : (
              <p className="text-sm italic text-ink-subtle">No readable text on this page.</p>
            )}
          </section>
        ))}
      </article>
    </>
  );
}
