import {
  listConversationMessages,
  listMessages,
  streamConversationChat,
  streamDocumentChat,
} from "./api";
import type { ChatEvent, ServerChatMessage } from "./types";

/** Where a chat loads its history from and sends its questions to: one document, or a comparison. */
export interface ChatSource {
  /** Stable identity, so the chat reloads when the source changes. */
  key: string;
  load: () => Promise<ServerChatMessage[]>;
  stream: (question: string, onEvent: (event: ChatEvent) => void, signal: AbortSignal) => Promise<void>;
}

export const documentChatSource = (documentId: string): ChatSource => ({
  key: `document:${documentId}`,
  load: () => listMessages(documentId),
  stream: (question, onEvent, signal) => streamDocumentChat(documentId, question, onEvent, signal),
});

export const conversationChatSource = (conversationId: string): ChatSource => ({
  key: `conversation:${conversationId}`,
  load: () => listConversationMessages(conversationId),
  stream: (question, onEvent, signal) => streamConversationChat(conversationId, question, onEvent, signal),
});
