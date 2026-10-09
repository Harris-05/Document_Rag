"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError } from "@/lib/api";
import type { ChatSource } from "@/lib/chatSource";
import type {
  AnswerQuality,
  ChatEvent,
  Citation,
  Coverage,
  ErrorCode,
  ServerChatMessage,
  TraceStep,
} from "@/lib/types";

export type MessageStatus = "streaming" | "complete" | "stopped" | "error";

export interface ChatMessageView {
  key: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  quality: AnswerQuality | null;
  citations: Citation[];
  trace: TraceStep[];
  coverage: Coverage | null;
  errorMessage: string | null;
  errorCode: ErrorCode | null;
  /** For assistant messages: the question that produced it, so a failed answer can be retried. */
  question: string | null;
}

type HistoryState = "loading" | "ready" | "error";

interface ChatState {
  history: HistoryState;
  historyError: string | null;
  messages: ChatMessageView[];
}

type Action =
  | { type: "historyLoaded"; messages: ChatMessageView[] }
  | { type: "historyFailed"; message: string }
  | { type: "asked"; question: string; userKey: string; assistantKey: string }
  | { type: "event"; key: string; event: ChatEvent }
  | { type: "stopped"; key: string }
  | { type: "failed"; key: string; message: string; code: ErrorCode | null };

function fromServer(messages: ServerChatMessage[]): ChatMessageView[] {
  let lastQuestion: string | null = null;
  return messages.map((message) => {
    if (message.role === "user") lastQuestion = message.content;
    return {
      key: `server-${message.id}`,
      role: message.role,
      content: message.content,
      status: message.status,
      quality: message.quality,
      citations: message.citations,
      trace: message.trace,
      coverage: message.coverage,
      errorMessage: message.error_message,
      errorCode: null,
      question: message.role === "assistant" ? lastQuestion : null,
    };
  });
}

function updateMessage(
  state: ChatState,
  key: string,
  change: (message: ChatMessageView) => ChatMessageView,
): ChatState {
  return { ...state, messages: state.messages.map((m) => (m.key === key ? change(m) : m)) };
}

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "historyLoaded":
      return { ...state, history: "ready", historyError: null, messages: action.messages };
    case "historyFailed":
      return { ...state, history: "error", historyError: action.message };
    case "asked":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            key: action.userKey,
            role: "user",
            content: action.question,
            status: "complete",
            quality: null,
            citations: [],
            trace: [],
            coverage: null,
            errorMessage: null,
            errorCode: null,
            question: null,
          },
          {
            key: action.assistantKey,
            role: "assistant",
            content: "",
            status: "streaming",
            quality: null,
            citations: [],
            trace: [],
            coverage: null,
            errorMessage: null,
            errorCode: null,
            question: action.question,
          },
        ],
      };
    case "event":
      return updateMessage(state, action.key, (message) => {
        const { event } = action;
        switch (event.event) {
          case "step":
            return { ...message, trace: [...message.trace, event.data] };
          case "token":
            return { ...message, content: message.content + event.data.text };
          case "citations":
            return { ...message, citations: event.data };
          case "done":
            return {
              ...message,
              status: "complete",
              quality: event.data.quality,
              coverage: event.data.coverage,
              content: message.content.trim(),
            };
          case "error":
            return {
              ...message,
              status: "error",
              errorMessage: event.data.message,
              content: message.content.trim(),
            };
          default:
            return message;
        }
      });
    case "stopped":
      return updateMessage(state, action.key, (message) =>
        message.status === "streaming"
          ? { ...message, status: "stopped", content: message.content.trim() }
          : message,
      );
    case "failed":
      return updateMessage(state, action.key, (message) => ({
        ...message,
        status: "error",
        errorMessage: action.message,
        errorCode: action.code,
      }));
  }
}

let counter = 0;
const nextKey = (prefix: string) => `${prefix}-${Date.now()}-${counter++}`;

export function useChat(source: ChatSource) {
  const [state, dispatch] = useReducer(reducer, {
    history: "loading",
    historyError: null,
    messages: [],
  } as ChatState);
  const controller = useRef<AbortController | null>(null);
  const activeKey = useRef<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      dispatch({ type: "historyLoaded", messages: fromServer(await source.load()) });
    } catch (error) {
      dispatch({
        type: "historyFailed",
        message: error instanceof ApiError ? error.message : "Could not load the conversation.",
      });
    }
  }, [source]);

  useEffect(() => {
    void loadHistory();
    return () => controller.current?.abort();
  }, [loadHistory]);

  const streaming = state.messages.some((message) => message.status === "streaming");

  const ask = useCallback(
    async (rawQuestion: string) => {
      const question = rawQuestion.trim();
      if (!question || controller.current) return;

      const userKey = nextKey("user");
      const assistantKey = nextKey("assistant");
      const run = new AbortController();
      controller.current = run;
      activeKey.current = assistantKey;
      dispatch({ type: "asked", question, userKey, assistantKey });

      try {
        await source.stream(
          question,
          (event) => dispatch({ type: "event", key: assistantKey, event }),
          run.signal,
        );
        // A stream that ends without a final event (dropped connection) must not look finished.
        dispatch({ type: "stopped", key: assistantKey });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          dispatch({ type: "stopped", key: assistantKey });
        } else {
          dispatch({
            type: "failed",
            key: assistantKey,
            message: error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
            code: error instanceof ApiError ? error.code : null,
          });
        }
      } finally {
        controller.current = null;
        activeKey.current = null;
      }
    },
    [source],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  return { ...state, streaming, ask, stop, reloadHistory: loadHistory };
}
