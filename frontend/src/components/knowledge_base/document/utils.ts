import { getUnifiedAgentWebSocket } from "../../chat/get_websockets";

/**
 * Get WebSocket URL for document queries.
 *
 * @param documentId - Document identifier.
 * @param conversationId - (Optional) If provided, the conversation id to load from.
 * @param corpusId - (Optional) If provided, scopes the document to a corpus.
 * @returns WebSocket URL with necessary query parameters.
 */
export const getWebSocketUrl = (
  documentId: string,
  conversationId?: string,
  corpusId?: string
): string => {
  return getUnifiedAgentWebSocket({ documentId, corpusId, conversationId });
};
