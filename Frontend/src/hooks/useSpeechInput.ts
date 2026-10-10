"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/** The parts of the browser's speech recognition that this app uses. */
interface RecognitionResult {
  readonly 0: { readonly transcript: string };
  readonly isFinal: boolean;
}
interface RecognitionEvent {
  readonly results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionConstructor = new () => Recognition;

function constructorOrNull(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

const noSubscription = () => () => {};

const ERROR_MESSAGES: Record<string, string> = {
  "not-allowed": "Microphone access is blocked. Allow it in the browser's site settings, then try again.",
  "service-not-allowed": "Microphone access is blocked. Allow it in the browser's site settings, then try again.",
  "no-speech": "Nothing was heard. Check your microphone and try again.",
  "audio-capture": "No microphone was found.",
  network: "Voice input needs an internet connection: the browser sends the audio to its speech service.",
  "language-not-supported": "This browser cannot recognise speech in your language.",
};

interface SpeechInputOptions {
  /** Called with everything recognised so far in this recording, including words still being decided. */
  onTranscript: (transcript: string) => void;
}

/**
 * Speaking a question, using the browser's own speech recognition (Chrome, Edge and Safari).
 * Nothing is sent to this app's server, and nothing is submitted: the words are handed to the caller
 * to put in the question box for the reader to check first.
 */
export function useSpeechInput({ onTranscript }: SpeechInputOptions) {
  const supported = useSyncExternalStore(noSubscription, () => constructorOrNull() !== null, () => false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const onTranscriptRef = useRef(onTranscript);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => () => recognition.current?.abort(), []);

  const start = useCallback(() => {
    const Ctor = constructorOrNull();
    if (!Ctor || recognition.current) return;
    setError(null);

    const session = new Ctor();
    session.lang = typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
    session.continuous = false;
    session.interimResults = true;
    session.maxAlternatives = 1;
    session.onstart = () => setListening(true);
    session.onresult = (event) => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index++) transcript += event.results[index][0].transcript;
      onTranscriptRef.current(transcript.trim());
    };
    session.onerror = (event) => {
      // "aborted" is what stopping on purpose looks like; it is not a problem to report.
      if (event.error === "aborted") return;
      setError(ERROR_MESSAGES[event.error] ?? "Voice input stopped unexpectedly. Please try again.");
    };
    session.onend = () => {
      recognition.current = null;
      setListening(false);
    };
    recognition.current = session;
    try {
      session.start();
    } catch {
      recognition.current = null;
      setError("Voice input could not start. Please try again.");
    }
  }, []);

  /** Finishes the recording and keeps what was heard. */
  const stop = useCallback(() => recognition.current?.stop(), []);
  /** Ends it at once and throws away anything still being recognised. */
  const cancel = useCallback(() => recognition.current?.abort(), []);

  return { supported, listening, error, start, stop, cancel, clearError: () => setError(null) };
}
