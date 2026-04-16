/**
 * useNotificationWebSocket - Hook for subscribing to real-time notification updates via WebSocket.
 *
 * This hook connects to the notification updates consumer (ws/notification-updates/)
 * to receive instant notifications about:
 * - Badge awards (BADGE)
 * - Message replies (REPLY, THREAD_REPLY)
 * - Mentions (MENTION)
 * - Accepted answers (ACCEPTED)
 * - Moderation actions (THREAD_LOCKED, MESSAGE_DELETED, etc.)
 *
 * Features:
 * - Automatic WebSocket connection management
 * - Real-time notification delivery (no polling latency)
 * - Auto-reconnection on network failures
 * - Heartbeat/ping-pong for connection health
 * - Automatic reconnection on page visibility change
 * - Graceful fallback to polling on persistent failures
 *
 * Issue #637: Migrate badge notifications from polling to WebSocket
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { authToken } from "../graphql/cache";
import { getNotificationUpdatesWebSocket } from "../components/chat/get_websockets";
import { useNetworkStatus } from "./useNetworkStatus";

// ============================================================================
// Types
// ============================================================================

/**
 * Notification types that can be received from the server.
 */
export type NotificationType =
  // Message/thread related
  | "REPLY"
  | "VOTE"
  | "BADGE"
  | "MENTION"
  | "ACCEPTED"
  | "THREAD_LOCKED"
  | "THREAD_UNLOCKED"
  | "THREAD_PINNED"
  | "THREAD_UNPINNED"
  | "MESSAGE_DELETED"
  | "THREAD_DELETED"
  | "MESSAGE_RESTORED"
  | "THREAD_RESTORED"
  | "THREAD_REPLY"
  // Job/processing related (Issue #624)
  | "DOCUMENT_PROCESSED"
  | "EXTRACT_COMPLETE"
  | "ANALYSIS_COMPLETE"
  | "ANALYSIS_FAILED"
  | "EXPORT_COMPLETE";

/**
 * Message types from the notification updates WebSocket consumer.
 */
type NotificationMessageType =
  | "CONNECTED"
  | "NOTIFICATION_CREATED"
  | "NOTIFICATION_UPDATED"
  | "NOTIFICATION_DELETED"
  | "pong"
  | "heartbeat_ack";

/**
 * Actor (user who triggered the notification).
 */
interface NotificationActor {
  id: string;
  username: string;
}

/**
 * Structure of notification update messages received from the consumer.
 */
interface NotificationUpdateMessage {
  type: NotificationMessageType;
  user_id?: string;
  session_id?: string;
  notificationId?: string;
  notificationType?: NotificationType;
  createdAt?: string;
  isRead?: boolean;
  modified?: string;
  data?: Record<string, any>;
  actor?: NotificationActor;
  messageId?: string;
  conversationId?: string;
}

/**
 * Notification update event (parsed and normalized).
 */
export interface NotificationUpdate {
  id: string;
  notificationType: NotificationType;
  createdAt: string;
  isRead: boolean;
  data: Record<string, any>;
  actor?: NotificationActor;
  messageId?: string;
  conversationId?: string;
}

/**
 * Connection state for the WebSocket.
 */
type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

/**
 * Hook options.
 */
interface UseNotificationWebSocketOptions {
  /** Callback when new notification is created */
  onNotificationCreated?: (notification: NotificationUpdate) => void;
  /** Callback when notification is updated (e.g., marked as read) */
  onNotificationUpdated?: (notificationId: string, isRead: boolean) => void;
  /** Callback when notification is deleted */
  onNotificationDeleted?: (notificationId: string) => void;
  /** Auto-reconnect on disconnect (default: true) */
  autoReconnect?: boolean;
  /** Reconnect delay in ms (default: 3000) */
  reconnectDelay?: number;
  /** Heartbeat interval in ms (default: 30000) */
  heartbeatInterval?: number;
  /** Enable the hook (default: true) */
  enabled?: boolean;
}

/**
 * Hook return value.
 */
interface UseNotificationWebSocketReturn {
  /** Current connection state */
  connectionState: ConnectionState;
  /** Session ID from the server */
  sessionId: string | null;
  /** Recently received notifications (last 50) */
  recentNotifications: NotificationUpdate[];
  /** Manually connect to WebSocket */
  connect: () => void;
  /** Manually disconnect from WebSocket */
  disconnect: () => void;
  /** Send a ping to check connection */
  sendPing: () => void;
  /** Clear recent notifications */
  clearRecent: () => void;
}

// ============================================================================
// Hook Implementation
// ============================================================================

/**
 * Hook for subscribing to notification updates via WebSocket.
 *
 * @param options - Configuration options
 * @returns WebSocket state and control functions
 */
export function useNotificationWebSocket(
  options: UseNotificationWebSocketOptions = {}
): UseNotificationWebSocketReturn {
  const {
    onNotificationCreated,
    onNotificationUpdated,
    onNotificationDeleted,
    autoReconnect = true,
    reconnectDelay = 3000,
    heartbeatInterval = 30000,
    enabled = true,
  } = options;

  const token = useReactiveVar(authToken);
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recentNotificationsRef = useRef<NotificationUpdate[]>([]);
  const failureCountRef = useRef<number>(0);

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recentNotifications, setRecentNotifications] = useState<
    NotificationUpdate[]
  >([]);

  // Clear heartbeat interval
  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  // Clear reconnect timeout
  const clearReconnect = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
  }, []);

  // Update recent notifications state
  const updateRecentNotifications = useCallback(() => {
    setRecentNotifications([...recentNotificationsRef.current]);
  }, []);

  // Add notification to recent list (keep last 50)
  const addToRecent = useCallback(
    (notification: NotificationUpdate) => {
      recentNotificationsRef.current = [
        notification,
        ...recentNotificationsRef.current,
      ].slice(0, 50);
      updateRecentNotifications();
    },
    [updateRecentNotifications]
  );

  // Clear recent notifications
  const clearRecent = useCallback(() => {
    recentNotificationsRef.current = [];
    updateRecentNotifications();
  }, [updateRecentNotifications]);

  // Handle incoming messages
  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const data: NotificationUpdateMessage = JSON.parse(event.data);

        switch (data.type) {
          case "CONNECTED":
            setSessionId(data.session_id || null);
            // Note: Failure count is reset in onopen, not here, to handle
            // cases where CONNECTED message may be delayed or missing
            break;

          case "NOTIFICATION_CREATED": {
            if (!data.notificationId || !data.notificationType) {
              console.warn(
                "[useNotificationWebSocket] Missing required fields in NOTIFICATION_CREATED"
              );
              break;
            }

            const notification: NotificationUpdate = {
              id: data.notificationId,
              notificationType: data.notificationType,
              createdAt: data.createdAt || new Date().toISOString(),
              isRead: data.isRead || false,
              data: data.data || {},
              actor: data.actor,
              messageId: data.messageId,
              conversationId: data.conversationId,
            };

            addToRecent(notification);
            onNotificationCreated?.(notification);
            break;
          }

          case "NOTIFICATION_UPDATED": {
            if (!data.notificationId) break;
            onNotificationUpdated?.(data.notificationId, data.isRead || false);
            break;
          }

          case "NOTIFICATION_DELETED": {
            if (!data.notificationId) break;
            onNotificationDeleted?.(data.notificationId);
            break;
          }

          case "pong":
          case "heartbeat_ack":
            // Connection is healthy
            break;

          default:
            console.debug(
              `[useNotificationWebSocket] Unknown message type: ${data.type}`
            );
        }
      } catch (e) {
        console.error("[useNotificationWebSocket] Failed to parse message:", e);
      }
    },
    [
      onNotificationCreated,
      onNotificationUpdated,
      onNotificationDeleted,
      addToRecent,
    ]
  );

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!enabled) {
      return;
    }

    // Don't attempt connection without auth token - will get 403
    if (!token) {
      console.debug(
        "[useNotificationWebSocket] Skipping connection - no auth token yet"
      );
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    clearReconnect();
    setConnectionState("connecting");

    const wsUrl = getNotificationUpdatesWebSocket(token);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionState("connected");
      // Reset failure count immediately on successful open as a fallback,
      // in case CONNECTED message is delayed or missing
      failureCountRef.current = 0;
      // Clear recent notifications buffer for clean state on new connection.
      // Note: For persistent notification storage across reconnections, use
      // Apollo cache (GET_NOTIFICATIONS query) - this buffer is only for
      // immediate UI updates during the current session.
      recentNotificationsRef.current = [];
      updateRecentNotifications();

      // Start heartbeat
      clearHeartbeat();
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, heartbeatInterval);
    };

    ws.onmessage = handleMessage;

    ws.onerror = (event) => {
      console.error("[useNotificationWebSocket] WebSocket error:", event);
      setConnectionState("error");
      failureCountRef.current += 1;
    };

    ws.onclose = (event) => {
      clearHeartbeat();
      setConnectionState("disconnected");
      setSessionId(null);

      // Auto-reconnect if enabled and not a normal closure
      // Use exponential backoff if we have repeated failures
      if (autoReconnect && event.code !== 1000) {
        const delay =
          reconnectDelay * Math.min(Math.pow(2, failureCountRef.current), 8);

        console.debug(
          `[useNotificationWebSocket] Reconnecting in ${delay}ms (failures: ${failureCountRef.current})`
        );

        reconnectRef.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };
  }, [
    enabled,
    token,
    autoReconnect,
    reconnectDelay,
    heartbeatInterval,
    handleMessage,
    clearHeartbeat,
    clearReconnect,
    updateRecentNotifications,
  ]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    clearHeartbeat();
    clearReconnect();

    if (wsRef.current) {
      wsRef.current.close(1000, "Client disconnect");
      wsRef.current = null;
    }

    setConnectionState("disconnected");
    setSessionId(null);
    recentNotificationsRef.current = [];
    updateRecentNotifications();
  }, [clearHeartbeat, clearReconnect, updateRecentNotifications]);

  // Send ping
  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ping" }));
    }
  }, []);

  // Connect when enabled changes to true
  // NOTE: connect/disconnect are intentionally excluded from deps to prevent
  // infinite reconnection loops. These functions have dependencies that change
  // frequently (e.g., handleMessage changes when callbacks change), but we only
  // want to connect/disconnect when `enabled` changes.
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reconnect when token changes (authentication change)
  // NOTE: connect/disconnect/enabled are intentionally excluded to prevent loops.
  // We reconnect when token changes regardless of current state because:
  // 1. Initial connection may fail (403) before auth completes
  // 2. Token refresh requires new connection with updated credentials
  useEffect(() => {
    if (enabled && token) {
      // Token is now available - connect or reconnect
      disconnect();
      connect();
    }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reconnect when page becomes visible after being hidden
  // This handles mobile devices where the app may be suspended when screen is locked
  useNetworkStatus({
    onResume: () => {
      if (!enabled) return;

      console.debug(
        "[useNotificationWebSocket] Page resumed, checking connection..."
      );

      // Check if WebSocket is still connected
      if (
        wsRef.current?.readyState !== WebSocket.OPEN &&
        wsRef.current?.readyState !== WebSocket.CONNECTING
      ) {
        console.debug(
          "[useNotificationWebSocket] WebSocket disconnected, reconnecting..."
        );
        try {
          connect();
        } catch (error) {
          console.error(
            "[useNotificationWebSocket] Reconnection failed:",
            error
          );
          setConnectionState("error");
        }
      } else if (wsRef.current?.readyState === WebSocket.OPEN) {
        // Send a ping to verify connection is still alive
        sendPing();
      }
    },
    onOnline: () => {
      if (!enabled) return;

      console.debug(
        "[useNotificationWebSocket] Network online, checking connection..."
      );

      // Reconnect if disconnected
      if (
        wsRef.current?.readyState !== WebSocket.OPEN &&
        wsRef.current?.readyState !== WebSocket.CONNECTING
      ) {
        try {
          connect();
        } catch (error) {
          console.error(
            "[useNotificationWebSocket] Reconnection after network recovery failed:",
            error
          );
          setConnectionState("error");
        }
      }
    },
    resumeThreshold: 1000, // 1 second hidden threshold
    enabled: enabled,
  });

  return {
    connectionState,
    sessionId,
    recentNotifications,
    connect,
    disconnect,
    sendPing,
    clearRecent,
  };
}

export default useNotificationWebSocket;
