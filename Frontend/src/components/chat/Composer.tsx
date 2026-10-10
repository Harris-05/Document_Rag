"use client";

import { ArrowUp, Stop } from "@phosphor-icons/react";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";
import type { ChatMode } from "@/lib/types";

const MAX_LENGTH = 2000;

interface ComposerProps {
  streaming: boolean;
  disabled: boolean;
  onSend: (question: string) => void;
  onStop: () => void;
  mode: ChatMode;
  /** Omitted when the chat has no choice of mode (several documents). */
  onModeChange?: (mode: ChatMode) => void;
}

const MODES: { value: ChatMode; label: string; hint: string }[] = [
  { value: "standard", label: "Standard", hint: "Searches, checks the passages are relevant, then answers." },
  {
    value: "research",
    label: "Research",
    hint: "The model looks things up itself, step by step, and follows cross-references. Slower.",
  },
];

export function Composer({ streaming, disabled, onSend, onStop, mode, onModeChange }: ComposerProps) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !streaming && !disabled;

  const resize = () => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;
    onSend(value);
    setValue("");
    requestAnimationFrame(resize);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      {onModeChange && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-1">
          <div role="radiogroup" aria-label="How to answer" className="flex rounded-ctl border border-line bg-surface-2 p-0.5">
            {MODES.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={mode === option.value}
                disabled={streaming}
                onClick={() => onModeChange(option.value)}
                className={`min-h-8 cursor-pointer rounded-[8px] px-3 text-[13px] font-medium transition-[background-color,color] duration-150 disabled:cursor-not-allowed disabled:opacity-60 ${
                  mode === option.value ? "bg-surface text-ink shadow-sm" : "text-ink-subtle hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <span className="min-w-0 flex-1 text-xs leading-snug text-ink-subtle">
            {MODES.find((option) => option.value === mode)?.hint}
          </span>
        </div>
      )}
      <label htmlFor="question" className="sr-only">
        Your question about this document
      </label>
      <div className="flex items-end gap-2 rounded-card border border-line-strong bg-surface p-2 transition-colors focus-within:border-accent focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent">
        <textarea
          id="question"
          ref={field}
          rows={1}
          value={value}
          maxLength={MAX_LENGTH}
          onChange={(event) => {
            setValue(event.target.value);
            resize();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask about a clause, party, date or figure"
          className="no-focus-ring max-h-42 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-ink outline-none placeholder:text-ink-subtle"
        />
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop answering"
            className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-ctl border border-line-strong bg-surface-2 text-ink transition-[background-color,transform] duration-150 hover:bg-line active:scale-[0.96]"
          >
            <Stop size={18} weight="fill" aria-hidden />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Send question"
            className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-ctl bg-accent text-accent-ink transition-[filter,transform,opacity] duration-150 hover:brightness-110 active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40"
          >
            <ArrowUp size={20} weight="bold" aria-hidden />
          </button>
        )}
      </div>
      <p className="flex justify-between gap-4 px-1 text-xs text-ink-subtle">
        <span>Enter to send, Shift+Enter for a new line</span>
        {value.length > MAX_LENGTH * 0.8 && (
          <span className="font-mono tabular-nums">
            {value.length}/{MAX_LENGTH}
          </span>
        )}
      </p>
    </form>
  );
}
