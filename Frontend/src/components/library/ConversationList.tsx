"use client";

import { Scales, Trash } from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { formatRelativeTime } from "@/lib/format";
import type { Conversation } from "@/lib/types";

interface ConversationListProps {
  conversations: Conversation[];
  onDelete: (id: string) => Promise<string | null>;
}

function ConversationRow({ conversation, onDelete }: { conversation: Conversation; onDelete: ConversationListProps["onDelete"] }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const names = conversation.documents.map((document) => document.filename);
  const title = names.join(", ") || "Documents removed";

  const confirmDelete = async () => {
    setBusy(true);
    const failure = await onDelete(conversation.id);
    if (failure) {
      setError(failure);
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:px-5">
      <div className="flex items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-ctl bg-accent-soft text-accent">
          <Scales size={18} weight="duotone" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <Link
            href={`/conversations/${conversation.id}`}
            className="block truncate rounded-ctl text-[14px] font-medium text-ink hover:text-accent"
            title={title}
          >
            {title}
          </Link>
          <p className="flex flex-wrap gap-x-3 text-[12px] text-ink-subtle">
            <span>{conversation.documents.length} documents</span>
            <span>
              {conversation.message_count} {conversation.message_count === 1 ? "message" : "messages"}
            </span>
            <span>{formatRelativeTime(conversation.created_at)}</span>
          </p>
        </div>
        {!confirming && (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setConfirming(true);
            }}
            aria-label={`Delete the comparison of ${title}`}
            className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-ctl text-ink-subtle transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <Trash size={18} aria-hidden />
          </button>
        )}
      </div>

      {confirming && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-ctl bg-danger-soft px-3 py-2">
          <p className="text-sm text-ink">Delete this comparison and its messages? The documents stay.</p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>
              Keep
            </Button>
            <Button variant="danger" onClick={confirmDelete} disabled={busy}>
              {busy ? "Deleting" : "Delete"}
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function ConversationList({ conversations, onDelete }: ConversationListProps) {
  if (conversations.length === 0) return null;
  return (
    <section aria-labelledby="comparisons-heading" className="flex flex-col gap-3">
      <h2 id="comparisons-heading" className="text-lg font-semibold tracking-tight text-ink">
        Questions across documents
      </h2>
      <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {conversations.map((conversation) => (
          <ConversationRow key={conversation.id} conversation={conversation} onDelete={onDelete} />
        ))}
      </ul>
    </section>
  );
}
