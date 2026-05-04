/**
 * WebSocket URL builders. Tokens are NEVER included in the URL — auth is
 * carried via the Sec-WebSocket-Protocol handshake header (see
 * frontend/src/utils/websocketAuth.ts and useWebSocketAuth hook).
 */

function getEnvVar(...keys: string[]): string | undefined {
  if (typeof import.meta !== "undefined" && (import.meta as any).env) {
    for (const k of keys) {
      const v = (import.meta as any).env[k];
      if (v !== undefined) return v as string;
    }
  }
  if (typeof process !== "undefined" && (process as any).env) {
    for (const k of keys) {
      const v = (process as any).env[k];
      if (v !== undefined) return v as string;
    }
  }
  return undefined;
}

function resolveWsBaseUrl(): string {
  const envUrl =
    getEnvVar("VITE_WS_URL", "REACT_APP_WS_URL") ||
    getEnvVar("VITE_API_URL", "REACT_APP_API_URL");
  if (envUrl) return envUrl.replace(/\/+$/, "");
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${
    window.location.host
  }`;
}

function normalizeBase(): string {
  return resolveWsBaseUrl()
    .replace(/\/+$/, "")
    .replace(/^http/, "ws")
    .replace(/^https/, "wss");
}

export interface UnifiedAgentContext {
  corpusId?: string;
  documentId?: string;
  agentId?: string;
  conversationId?: string;
}

export function getUnifiedAgentWebSocket(context: UnifiedAgentContext): string {
  let url = `${normalizeBase()}/ws/agent-chat/`;
  const params: string[] = [];
  if (context.corpusId)
    params.push(`corpus_id=${encodeURIComponent(context.corpusId)}`);
  if (context.documentId)
    params.push(`document_id=${encodeURIComponent(context.documentId)}`);
  if (context.agentId)
    params.push(`agent_id=${encodeURIComponent(context.agentId)}`);
  if (context.conversationId)
    params.push(
      `conversation_id=${encodeURIComponent(context.conversationId)}`
    );
  if (params.length) url += `?${params.join("&")}`;
  return url;
}

export function getThreadUpdatesWebSocket(conversationId: string): string {
  return `${normalizeBase()}/ws/thread-updates/?conversation_id=${encodeURIComponent(
    conversationId
  )}`;
}

export function getNotificationUpdatesWebSocket(): string {
  return `${normalizeBase()}/ws/notification-updates/`;
}
