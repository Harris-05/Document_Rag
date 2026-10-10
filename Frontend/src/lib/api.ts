import { createSseParser } from "./sse";
import type {
  ChatMode,
  ChatEvent,
  ComparisonDetail,
  ComparisonSummary,
  Conversation,
  DocumentDetail,
  DocumentSummary,
  ErrorCode,
  ServerChatMessage,
  UserFacingError,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number | null;

  constructor({ code, message }: UserFacingError, status: number | null = null) {
    super(message);
    this.code = code;
    this.status = status;
  }

  toUserFacing(): UserFacingError {
    return { code: this.code, message: this.message };
  }
}

const NETWORK_ERROR: UserFacingError = {
  code: "NETWORK",
  message: "Could not reach the server. Check that the backend is running and try again.",
};

async function parseError(response: Response): Promise<UserFacingError> {
  try {
    const body = await response.json();
    if (typeof body?.code === "string" && typeof body?.message === "string") {
      return { code: body.code as ErrorCode, message: body.message };
    }
    if (typeof body?.detail === "string") return { code: "UNKNOWN", message: body.detail };
  } catch {
    // fall through to the generic message
  }
  return { code: "UNKNOWN", message: `The server responded with an error (${response.status}).` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** URL of the original uploaded file, for the in-browser viewer. */
export const fileUrl = (id: string) => `${API_URL}/api/documents/${id}/file`;

export const listDocuments = () => request<DocumentSummary[]>("/api/documents");
export const getDocument = (id: string) => request<DocumentSummary>(`/api/documents/${id}`);
export const getDocumentText = (id: string) => request<DocumentDetail>(`/api/documents/${id}/text`);
export const deleteDocument = (id: string) =>
  request<void>(`/api/documents/${id}`, { method: "DELETE" });

/** Uses XMLHttpRequest because fetch cannot report how many bytes of an upload have been sent. */
export function uploadDocument(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<DocumentSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const body = new FormData();
    body.append("file", file);

    xhr.open("POST", `${API_URL}/api/documents`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as DocumentSummary);
        return;
      }
      const payload = xhr.response as { code?: string; message?: string; detail?: string } | null;
      reject(
        new ApiError({
          code: (payload?.code as ErrorCode) ?? "UNKNOWN",
          message:
            payload?.message ?? payload?.detail ?? `The server responded with an error (${xhr.status}).`,
        }, xhr.status),
      );
    };
    xhr.onerror = () => reject(new ApiError(NETWORK_ERROR));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(body);
  });
}

export const listMessages = (documentId: string) =>
  request<ServerChatMessage[]>(`/api/documents/${documentId}/messages`);

/**
 * Asks a question at a chat endpoint and reports each streamed event as it arrives. Aborting the
 * signal closes the connection, which tells the server to stop and keep whatever was generated.
 */
export async function streamChatAt(
  path: string,
  question: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
  mode: ChatMode = "standard",
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, mode }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(NETWORK_ERROR);
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  if (!response.body) throw new ApiError({ code: "UNKNOWN", message: "The server sent an empty response." });

  const parser = createSseParser((frame) => onEvent(frame as unknown as ChatEvent));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(NETWORK_ERROR);
  }
}

export const streamDocumentChat = (
  documentId: string,
  question: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
  mode: ChatMode = "standard",
) => streamChatAt(`/api/documents/${documentId}/chat`, question, onEvent, signal, mode);

export const streamConversationChat = (
  conversationId: string,
  question: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
) => streamChatAt(`/api/conversations/${conversationId}/chat`, question, onEvent, signal);

export const createConversation = (documentIds: string[]) =>
  request<Conversation>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });
export const getConversation = (id: string) => request<Conversation>(`/api/conversations/${id}`);
export const listConversations = () => request<Conversation[]>("/api/conversations");
export const deleteConversation = (id: string) => request<void>(`/api/conversations/${id}`, { method: "DELETE" });
export const listConversationMessages = (id: string) =>
  request<ServerChatMessage[]>(`/api/conversations/${id}/messages`);

export const createComparison = (oldDocumentId: string, newDocumentId: string) =>
  request<ComparisonSummary>("/api/comparisons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_document_id: oldDocumentId, new_document_id: newDocumentId }),
  });
export const getComparison = (id: string) => request<ComparisonDetail>(`/api/comparisons/${id}`);
export const listComparisons = () => request<ComparisonSummary[]>("/api/comparisons");
export const deleteComparison = (id: string) => request<void>(`/api/comparisons/${id}`, { method: "DELETE" });
