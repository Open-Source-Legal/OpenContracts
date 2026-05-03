/**
 * Subprotocol marker the client sends and the server echoes for WS auth
 * handshake. Versioned so we can roll a v2 protocol without breaking
 * existing clients.
 */
export const WS_AUTH_SUBPROTOCOL = "opencontracts.jwt.v1";

/** Server-side close codes (kept in sync with config/websocket/middleware.py). */
export const WS_CLOSE_NORMAL = 1000;
export const WS_CLOSE_UNAUTHENTICATED = 4000;
export const WS_CLOSE_TOKEN_EXPIRED = 4001;
export const WS_CLOSE_TOKEN_INVALID = 4002;
export const WS_CLOSE_PERMISSION_DENIED = 4003;
export const WS_CLOSE_RATE_LIMITED = 4029;

/** Frame types added by the auth handshake. */
export type AuthFrame =
  | {
      type: "AUTH_OK";
      user_id: number | null;
      username?: string;
      anonymous: boolean;
      refreshed: boolean;
    }
  | {
      type: "AUTH_FAILED";
      reason: "EXPIRED" | "INVALID" | "USER_MISMATCH" | "PERMISSION_REVOKED";
    }
  | { type: "AUTH_REFRESH_REQUIRED"; grace_seconds: number };

/** Build the `protocols` array for `new WebSocket(url, protocols)`. */
export function buildAuthProtocols(token?: string | null): string[] {
  if (!token) return [WS_AUTH_SUBPROTOCOL];
  return [WS_AUTH_SUBPROTOCOL, token];
}

/** Build a client→server AUTH refresh frame. */
export function buildAuthMessage(token: string): {
  type: "AUTH";
  token: string;
} {
  return { type: "AUTH", token };
}

/** Parse an incoming text frame; return AuthFrame if it's an auth frame, else null. */
export function parseAuthMessage(text: string): AuthFrame | null {
  try {
    const obj = JSON.parse(text);
    if (
      obj &&
      typeof obj === "object" &&
      typeof obj.type === "string" &&
      (obj.type === "AUTH_OK" ||
        obj.type === "AUTH_FAILED" ||
        obj.type === "AUTH_REFRESH_REQUIRED")
    ) {
      return obj as AuthFrame;
    }
    return null;
  } catch {
    return null;
  }
}
