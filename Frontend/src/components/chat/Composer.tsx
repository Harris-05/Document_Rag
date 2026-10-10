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

  const modeHint = MODES.find((option) => option.value === mode)?.hint;

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor="question" className="sr-only">
        Your question about this document
      </label>
      <div className="flex flex-col rounded-card border border-line-strong bg-surface shadow-sm transition-colors focus-within:border-ink">
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
          placeholder="Ask a question about this document"
          aria-describedby="composer-help"
          className="no-focus-ring max-h-42 min-h-12 w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[15px] leading-6 text-ink outline-none placeholder:text-ink-subtle"
        />
        <div className="flex items-center justify-between gap-3 px-2.5 pb-2.5">
          {onModeChange ? (
            <div
              role="radiogroup"
              aria-label="How to answer"
              title={modeHint}
              className="flex rounded-full bg-surface-2 p-0.5"
            >
              {MODES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={mode === option.value}
                  aria-label={option.label}
                  title={option.hint}
                  disabled={streaming}
                  onClick={() => onModeChange(option.value)}
                  className={`min-h-8 cursor-pointer rounded-full px-3.5 text-[12px] font-medium transition-[background-color,color] duration-150 disabled:cursor-not-allowed disabled:opacity-60 ${
                    mode === option.value ? "bg-surface text-ink shadow-sm" : "text-ink-subtle hover:text-ink"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : (
            <span />
          )}

          <div className="flex items-center gap-1.5">
            {voice.supported ? (
              <button
                type="button"
                onClick={toggleVoice}
                disabled={disabled || streaming}
                aria-pressed={voice.listening}
                aria-label={voice.listening ? "Stop voice input" : "Ask by voice"}
                title={voice.listening ? "Stop listening" : "Ask by voice"}
                className={`relative grid size-10 shrink-0 cursor-pointer place-items-center rounded-full transition-[background-color,color,transform] duration-150 active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40 ${
                  voice.listening ? "bg-accent-soft text-ink" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {voice.listening && (
                  <span
                    aria-hidden
                    className="absolute inset-0 animate-ping rounded-full bg-ink/10 motion-reduce:animate-none"
                  />
                )}
                <Microphone size={20} weight={voice.listening ? "fill" : "regular"} className="relative" aria-hidden />
              </button>
            ) : (
              <button
                type="button"
                disabled
                aria-label="Voice input is not available in this browser"
                title="Voice input needs a browser with speech recognition, such as Chrome, Edge or Safari"
                className="grid size-10 shrink-0 place-items-center rounded-full text-ink-subtle opacity-40"
              >
                <Microphone size={20} aria-hidden />
              </button>
            )}
            {streaming ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop answering"
                className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full bg-surface-2 text-ink transition-[background-color,transform] duration-150 hover:bg-line active:scale-[0.96]"
              >
                <Stop size={16} weight="fill" aria-hidden />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSend}
                aria-label="Send question"
                className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full bg-accent text-accent-ink transition-[filter,transform,opacity] duration-150 hover:brightness-110 active:scale-[0.96] disabled:pointer-events-none disabled:opacity-30"
              >
                <ArrowUp size={18} weight="bold" aria-hidden />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Quiet by default: this line only appears when there is something to say. */}
      <p id="composer-help" className="flex justify-between gap-4 px-1 text-xs text-ink-subtle">
        {voice.error ? (
          <span role="alert" className="text-danger">
            {voice.error}
          </span>
        ) : voice.listening ? (
          <span role="status" className="text-ink">
            Listening. Speak your question; it stops when you pause.
          </span>
        ) : onModeChange && mode === "research" ? (
          <span>{modeHint}</span>
        ) : (
          <span className="sr-only">Press Enter to send, Shift and Enter for a new line.</span>
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
