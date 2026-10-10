"use client";

import { ArrowUp, Microphone, Stop } from "@phosphor-icons/react";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";
import { useSpeechInput } from "@/hooks/useSpeechInput";
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
  // What was already typed when recording began; spoken words are added after it, not over it.
  const typedBefore = useRef("");

  const resize = () => {
    const element = field.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  };

  const voice = useSpeechInput({
    onTranscript: (transcript) => {
      const before = typedBefore.current;
      setValue(before && transcript ? `${before} ${transcript}` : before || transcript);
      requestAnimationFrame(resize);
    },
  });

  const toggleVoice = () => {
    if (voice.listening) {
      voice.stop();
      return;
    }
    typedBefore.current = value.trim();
    voice.start();
    field.current?.focus();
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;
    voice.cancel();
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
            // Typing takes over from the microphone, so the next transcript cannot overwrite the edit.
            if (voice.listening) voice.cancel();
            if (voice.error) voice.clearError();
            setValue(event.target.value);
            resize();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask about a clause, party, date or figure"
          className="no-focus-ring max-h-42 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-ink outline-none placeholder:text-ink-subtle"
        />
        {voice.supported ? (
          <button
            type="button"
            onClick={toggleVoice}
            disabled={disabled || streaming}
            aria-pressed={voice.listening}
            aria-label={voice.listening ? "Stop voice input" : "Ask by voice"}
            title={voice.listening ? "Stop listening" : "Ask by voice"}
            className={`relative grid size-11 shrink-0 cursor-pointer place-items-center rounded-ctl border transition-[background-color,color,transform] duration-150 active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40 ${
              voice.listening
                ? "border-accent bg-accent-soft text-accent"
                : "border-line-strong bg-surface text-ink-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {voice.listening && (
              <span aria-hidden className="absolute inset-0 animate-ping rounded-ctl bg-accent/20 motion-reduce:animate-none" />
            )}
            <Microphone size={20} weight={voice.listening ? "fill" : "regular"} className="relative" aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            disabled
            aria-label="Voice input is not available in this browser"
            title="Voice input needs a browser with speech recognition, such as Chrome, Edge or Safari"
            className="grid size-11 shrink-0 place-items-center rounded-ctl border border-line text-ink-subtle opacity-40"
          >
            <Microphone size={20} aria-hidden />
          </button>
        )}
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
        {voice.error ? (
          <span role="alert" className="text-danger">
            {voice.error}
          </span>
        ) : voice.listening ? (
          <span role="status" className="text-accent">
            Listening. Speak your question; it stops when you pause.
          </span>
        ) : (
          <span>Enter to send, Shift+Enter for a new line</span>
        )}
        {value.length > MAX_LENGTH * 0.8 && (
          <span className="font-mono tabular-nums">
            {value.length}/{MAX_LENGTH}
          </span>
        )}
      </p>
    </form>
  );
}
