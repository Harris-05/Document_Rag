import {
  listConversationMessages,
  listMessages,
  streamConversationChat,
  streamDocumentChat,
} from "./api";
import type { ChatEvent, ChatMode, ServerChatMessage } from "./types";

/** Where a chat loads its history from and sends its questions to: one document, or a comparison. */
export interface ChatSource {
  /** Stable identity, so the chat reloads when the source changes. */
  key: string;
  load: () => Promise<ServerChatMessage[]>;
  /** Whether the model can be let loose with tools here. Only a single document supports it. */
  supportsResearch: boolean;
  stream: (
    question: string,
    onEvent: (event: ChatEvent) => void,
    signal: AbortSignal,
    mode: ChatMode,
  ) => Promise<void>;
}

export const documentChatSource = (documentId: string): ChatSource => ({
  key: `document:${documentId}`,
  load: () => listMessages(documentId),
  supportsResearch: true,
  stream: (question, onEvent, signal, mode) => streamDocumentChat(documentId, question, onEvent, signal, mode),
});

export const conversationChatSource = (conversationId: string): ChatSource => ({
  key: `conversation:${conversationId}`,
  load: () => listConversationMessages(conversationId),
  supportsResearch: false,
  stream: (question, onEvent, signal) => streamConversationChat(conversationId, question, onEvent, signal),
});
