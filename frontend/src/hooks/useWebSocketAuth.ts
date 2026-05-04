/**
 * useWebSocketAuth — shared hook that owns a single WebSocket and the auth
 * handshake/refresh lifecycle on top of it.
 *
 * Other hooks (useAgentChat, useNotificationWebSocket, etc.) compose this
 * to get:
 *   - Sec-WebSocket-Protocol auth on initial connect (no token in URL)
 *   - In-band AUTH frame refresh when the authToken reactive var rotates
 *   - Server-nudged refresh via AUTH_REFRESH_REQUIRED
 *   - Close-code-aware reconnect policy
 *
 * Caller passes an `onMessage` callback for non-auth frames; this hook
 * intercepts AUTH_OK / AUTH_FAILED / AUTH_REFRESH_REQUIRED itself.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { authToken } from "../graphql/cache";
import {
  WS_CLOSE_NORMAL,
  WS_CLOSE_UNAUTHENTICATED,
  WS_CLOSE_TOKEN_EXPIRED,
  WS_CLOSE_TOKEN_INVALID,
  WS_CLOSE_PERMISSION_DENIED,
  WS_CLOSE_RATE_LIMITED,
  buildAuthProtocols,
  buildAuthMessage,
  parseAuthMessage,
} from "../utils/websocketAuth";

export interface UseWebSocketAuthOptions {
  /** Full WS URL with all query params EXCEPT token. Token never goes here. */
  url: string;
  /** Called for every non-auth text frame. */
  onMessage?: (event: MessageEvent) => void;
  /** Called on socket open. */
  onOpen?: () => void;
  /** Called on socket close, with the close code. */
  onClose?: (code: number) => void;
  /**
   * Called when the server rejects auth — close codes 4000
   * (UNAUTHENTICATED), 4001 (TOKEN_EXPIRED), or 4002 (TOKEN_INVALID).
   *
   * Reconnect contract: when this fires the hook stops scheduling
   * reconnects, because reconnecting with the same stale token would
   * just be rejected in a tight loop. The caller is responsible for
   * obtaining a fresh token (e.g. Auth0 silent renewal) and then
   * calling the returned ``reconnect()`` to resume — or doing nothing
   * if the user must re-authenticate via the login flow.
   */
  onAuthInvalid?: () => void;
  /** Skip everything (e.g. while context not ready). */
  enabled?: boolean;
  /**
   * When true, the hook will NOT open a socket while the auth token
   * reactive var is empty. Use this for endpoints that reject anonymous
   * connections (e.g. /ws/notification-updates/) — without this gate,
   * the hook would open a token-less socket on first render, the
   * consumer would reject 4000/4001, the close would land in the
   * auth-failure family, and reconnects would be suppressed for the
   * rest of the session even after login completes.
   *
   * The hook still re-opens automatically when the token transitions
   * empty → non-empty (e.g. login completes after mount).
   *
   * Default: false (preserves existing behavior for endpoints that
   * accept anonymous connections like /ws/agent-chat/ on public docs).
   */
  requireAuth?: boolean;
  /** Initial reconnect delay (ms). Doubled per failure up to 8x. */
  reconnectDelayMs?: number;
}

export interface UseWebSocketAuthReturn {
  isConnected: boolean;
  isAuthenticated: boolean;
  lastError: string | null;
  send: (data: string) => boolean;
  /** Force a reconnect (e.g. on page resume). */
  reconnect: () => void;
}

export function useWebSocketAuth(
  options: UseWebSocketAuthOptions
): UseWebSocketAuthReturn {
  const {
    url,
    onMessage,
    onOpen,
    onClose,
    onAuthInvalid,
    enabled = true,
    requireAuth = false,
    reconnectDelayMs = 3000,
  } = options;

  const token = useReactiveVar(authToken);
  const tokenRef = useRef<string>(token || "");
  useEffect(() => {
    tokenRef.current = token || "";
  }, [token]);

  // Hold callbacks in refs so the long-lived ws.onopen/onmessage/onclose
  // handlers always invoke the latest version. Without this, a consumer
  // re-rendering with a new callback identity would silently keep firing
  // the stale closure captured when the connection effect ran.
  const onMessageRef = useRef(onMessage);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  const onAuthInvalidRef = useRef(onAuthInvalid);
  useEffect(() => {
    onMessageRef.current = onMessage;
    onOpenRef.current = onOpen;
    onCloseRef.current = onClose;
    onAuthInvalidRef.current = onAuthInvalid;
  }, [onMessage, onOpen, onClose, onAuthInvalid]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failureCountRef = useRef(0);
  const [reconnectTrigger, setReconnectTrigger] = useState(0);

  const [isConnected, setIsConnected] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const reconnect = useCallback(() => {
    setReconnectTrigger((n) => n + 1);
  }, []);

  // Whether the connect effect is currently allowed to open a socket.
  // We re-evaluate `requireAuth` against the live token here (rather
  // than against `tokenRef`, which doesn't trigger re-renders) so the
  // effect re-runs when the token transitions empty → non-empty after
  // login completes.
  const shouldConnect = enabled && (!requireAuth || Boolean(token));

  // Open / replace the socket whenever url, enabled, or reconnectTrigger changes.
  // Token changes do NOT trigger reconnect — they fire an in-band AUTH frame
  // (via the second effect below). The exception is `requireAuth`: token
  // empty → non-empty re-runs this effect because `shouldConnect` flips.
  useEffect(() => {
    if (!shouldConnect) {
      setIsConnected(false);
      setIsAuthenticated(false);
      return;
    }

    clearReconnectTimer();
    const protocols = buildAuthProtocols(tokenRef.current);
    const ws = new WebSocket(url, protocols);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setLastError(null);
      failureCountRef.current = 0;
      onOpenRef.current?.();
    };

    ws.onmessage = (event) => {
      const auth = parseAuthMessage(event.data);
      if (auth) {
        if (auth.type === "AUTH_OK") {
          setIsAuthenticated(!auth.anonymous);
        } else if (auth.type === "AUTH_FAILED") {
          setIsAuthenticated(false);
          setLastError(`AUTH_FAILED: ${auth.reason}`);
        } else if (auth.type === "AUTH_REFRESH_REQUIRED") {
          if (tokenRef.current && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(buildAuthMessage(tokenRef.current)));
          }
        }
        return;
      }
      onMessageRef.current?.(event);
    };

    ws.onerror = () => {
      setLastError("WebSocket transport error");
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      setIsAuthenticated(false);
      onCloseRef.current?.(event.code);

      const code = event.code;
      // 1000 (NORMAL) is a clean close — no reconnect needed.
      // 4003 (PERMISSION_DENIED) means the server explicitly revoked
      // access to this resource; reconnecting would just be rejected
      // again. We deliberately do NOT fire onAuthInvalid here because
      // the user's auth is fine — the resource permission isn't —
      // so the caller should react via its own error UI (e.g., a
      // toast or a route redirect) rather than treating it as a
      // session-expired event. The user must reload or navigate away
      // to recover; transient 4003s require a manual reconnect().
      if (code === WS_CLOSE_NORMAL || code === WS_CLOSE_PERMISSION_DENIED) {
        return;
      }
      // Auth-failure family — reconnecting will just be rejected the same way
      // until the user signs in again, so surface the failure and stop.
      if (
        code === WS_CLOSE_UNAUTHENTICATED ||
        code === WS_CLOSE_TOKEN_EXPIRED ||
        code === WS_CLOSE_TOKEN_INVALID
      ) {
        onAuthInvalidRef.current?.();
        return;
      }

      const baseDelay =
        code === WS_CLOSE_RATE_LIMITED
          ? reconnectDelayMs * 4
          : reconnectDelayMs;
      const delay = baseDelay * Math.min(2 ** failureCountRef.current, 8);
      failureCountRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        setReconnectTrigger((n) => n + 1);
      }, delay);
    };

    return () => {
      clearReconnectTimer();
      try {
        ws.close(WS_CLOSE_NORMAL, "hook unmount");
      } catch {
        // socket already closed
      }
      wsRef.current = null;
    };
  }, [
    url,
    shouldConnect,
    reconnectTrigger,
    clearReconnectTimer,
    reconnectDelayMs,
  ]);

  // Token rotation → in-band AUTH refresh (no reconnect).
  useEffect(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!token) return;
    ws.send(JSON.stringify(buildAuthMessage(token)));
  }, [token]);

  const send = useCallback((data: string): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(data);
    return true;
  }, []);

  return {
    isConnected,
    isAuthenticated,
    lastError,
    send,
    reconnect,
  };
}

export default useWebSocketAuth;
