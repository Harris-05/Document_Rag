"use client";

import { ChatsCircle, CloudSlash } from "@phosphor-icons/react";
import { useCallback, useLayoutEffect, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { useChat } from "@/hooks/useChat";
import type { ChatSource } from "@/lib/chatSource";
import type { Citation } from "@/lib/types";
import { AssistantMessage } from "./AssistantMessage";
import { Composer } from "./Composer";

const SUGGESTIONS = [
  "What are the termination provisions?",
  "Is liability capped, and at what amount?",
  "Which law governs this agreement?",
];

const STICK_THRESHOLD_PX = 140;

interface ChatPaneProps {
  source: ChatSource;
  /** True when the chat spans several documents, so answers show which document each quote is from. */
  multi?: boolean;
  activeCitation: { messageKey: string; n: number } | null;
  onOpenCitation: (messageKey: string, citation: Citation) => void;
}

function HistorySkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-6">
      <div className="skeleton ml-auto h-10 w-2/5 rounded-card" />
      <div className="flex flex-col gap-2.5">
        <span className="skeleton h-3.5 w-full rounded-full" />
        <span className="skeleton h-3.5 w-11/12 rounded-full" />
        <span className="skeleton h-3.5 w-3/5 rounded-full" />
      </div>
    </div>
  );
}

function EmptyChat({ onPick, disabled }: { onPick: (question: string) => void; disabled: boolean }) {
  return (
    <div className="flex h-full flex-col justify-center gap-6 py-8">
      <div className="flex flex-col gap-3">
        <span className="grid size-12 place-items-center rounded-card bg-accent-soft text-accent">
          <ChatsCircle size={26} weight="duotone" aria-hidden />
        </span>
        <h2 className="text-xl font-semibold tracking-tight text-ink">Ask about this contract</h2>
        <p className="max-w-[44ch] text-[15px] leading-relaxed text-ink-muted">
          Answers come only from this document, and every quote is checked against its text before it is shown
          as verified.
        </p>
      </div>
      <ul className="flex flex-col items-start gap-2">
        {SUGGESTIONS.map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(suggestion)}
              className="min-h-11 cursor-pointer rounded-ctl border border-line bg-surface px-4 py-2 text-left text-sm text-ink transition-[background-color,border-color,transform] duration-150 hover:border-line-strong hover:bg-surface-2 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ChatPane({ source, multi = false, activeCitation, onOpenCitation }: ChatPaneProps) {
  const chat = useChat(source);
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const handleScroll = useCallback(() => {
    const element = scroller.current;
    if (!element) return;
    stickToBottom.current =
      element.scrollHeight - element.scrollTop - element.clientHeight < STICK_THRESHOLD_PX;
  }, []);

  // Follow new content only while the reader is already at the bottom; never yank them back down.
  useLayoutEffect(() => {
    const element = scroller.current;
    if (element && stickToBottom.current) element.scrollTop = element.scrollHeight;
  }, [chat.messages]);

  const send = useCallback(
    (question: string) => {
      stickToBottom.current = true;
      void chat.ask(question);
    },
    [chat],
  );

  const isEmpty = chat.history === "ready" && chat.messages.length === 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={scroller}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6"
        role="log"
        aria-label="Conversation"
        aria-live="polite"
      >
        {chat.history === "loading" && <HistorySkeleton />}

        {chat.history === "error" && (
          <div role="alert" className="flex flex-col items-start gap-3 py-6">
            <span className="grid size-12 place-items-center rounded-card bg-danger-soft text-danger">
              <CloudSlash size={24} weight="duotone" aria-hidden />
            </span>
            <h2 className="text-[15px] font-medium text-ink">Couldn&apos;t load the conversation</h2>
            <p className="max-w-[40ch] text-sm leading-relaxed text-ink-muted">{chat.historyError}</p>
            <Button variant="secondary" onClick={() => void chat.reloadHistory()}>
              Try again
            </Button>
          </div>
        )}

        {isEmpty && <EmptyChat onPick={send} disabled={chat.streaming} />}

        {chat.history === "ready" && chat.messages.length > 0 && (
          <ol className="flex flex-col gap-8">
            {chat.messages.map((message) => (
              <li key={message.key} className="flex flex-col">
                {message.role === "user" ? (
                  <p className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-card bg-accent-soft px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                    {message.content}
                  </p>
                ) : (
                  <AssistantMessage
                    message={message}
                    activeCitation={activeCitation}
                    multi={multi}
                    onOpenCitation={onOpenCitation}
                    onRetry={send}
                    retryDisabled={chat.streaming}
                  />
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="border-t border-line bg-bg/60 px-4 py-4 sm:px-6">
        <Composer
          streaming={chat.streaming}
          disabled={chat.history !== "ready"}
          onSend={send}
          onStop={chat.stop}
        />
      </div>
    </div>
  );
}
