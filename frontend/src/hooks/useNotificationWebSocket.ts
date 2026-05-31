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
 * - Automatic WebSocket connection management (via useWebSocketAuth)
 * - Real-time notification delivery (no polling latency)
 * - In-band token refresh (no socket churn on auth rotation)
 * - Heartbeat/ping-pong for connection health
 * - Automatic reconnection on page visibility change
 *
 * Issue #637: Migrate badge notifications from polling to WebSocket
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getNotificationUpdatesWebSocket } from "../components/chat/get_websockets";
import { useNetworkStatus } from "./useNetworkStatus";
import { useWebSocketAuth } from "./useWebSocketAuth";

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
  | "EXPORT_COMPLETE"
  // Deep-research job lifecycle. An incremental RESEARCH_REPORT_PROGRESS event
  // is planned for v2 but is intentionally absent here: the backend does not
  // emit it yet and there is no handler, so adding it to the union now would
  // mask the gap rather than catch it. Add the member when the handler is wired.
  | "RESEARCH_REPORT_COMPLETE"
  | "RESEARCH_REPORT_FAILED"
  | "RESEARCH_REPORT_CANCELLED";

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
export interface UseNotificationWebSocketOptions {
  /** Callback when new notification is created */
  onNotificationCreated?: (notification: NotificationUpdate) => void;
  /** Callback when notification is updated (e.g., marked as read) */
  onNotificationUpdated?: (notificationId: string, isRead: boolean) => void;
  /** Callback when notification is deleted */
  onNotificationDeleted?: (notificationId: string) => void;
  /** Heartbeat interval in ms (default: 30000) */
  heartbeatInterval?: number;
  /** Enable the hook (default: true) */
  enabled?: boolean;
}

/**
 * Hook return value.
 */
export interface UseNotificationWebSocketReturn {
  /** Current connection state */
  connectionState: ConnectionState;
  /** Session ID from the server */
  sessionId: string | null;
  /** Recently received notifications (last 50) */
  recentNotifications: NotificationUpdate[];
  /** Force a reconnect (e.g. on page resume). */
  reconnect: () => void;
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
    heartbeatInterval = 30000,
    enabled = true,
  } = options;

  const url = getNotificationUpdatesWebSocket();
  const recentNotificationsRef = useRef<NotificationUpdate[]>([]);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recentNotifications, setRecentNotifications] = useState<
    NotificationUpdate[]
  >([]);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected");

  const updateRecent = useCallback(() => {
    setRecentNotifications([...recentNotificationsRef.current]);
  }, []);

  const addToRecent = useCallback(
    (n: NotificationUpdate) => {
      recentNotificationsRef.current = [
        n,
        ...recentNotificationsRef.current,
      ].slice(0, 50);
      updateRecent();
    },
    [updateRecent]
  );

  const clearRecent = useCallback(() => {
    recentNotificationsRef.current = [];
    updateRecent();
  }, [updateRecent]);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const data: NotificationUpdateMessage = JSON.parse(event.data);

        switch (data.type) {
          case "CONNECTED":
            setSessionId(data.session_id || null);
            break;

          case "NOTIFICATION_CREATED": {
            if (!data.notificationId || !data.notificationType) break;
            const n: NotificationUpdate = {
              id: data.notificationId,
              notificationType: data.notificationType,
              createdAt: data.createdAt || new Date().toISOString(),
              isRead: data.isRead || false,
              data: data.data || {},
              actor: data.actor,
              messageId: data.messageId,
              conversationId: data.conversationId,
            };
            addToRecent(n);
            onNotificationCreated?.(n);
            break;
          }

          case "NOTIFICATION_UPDATED":
            if (data.notificationId)
              onNotificationUpdated?.(
                data.notificationId,
                data.isRead || false
              );
            break;

          case "NOTIFICATION_DELETED":
            if (data.notificationId)
              onNotificationDeleted?.(data.notificationId);
            break;

          case "pong":
          case "heartbeat_ack":
            break;
        }
      } catch (e) {
        console.error("[useNotificationWebSocket] Failed to parse:", e);
      }
    },
    [
      addToRecent,
      onNotificationCreated,
      onNotificationUpdated,
      onNotificationDeleted,
    ]
  );

  const sendRef = useRef<((data: string) => boolean) | null>(null);

  const { isConnected, isAuthenticated, send, reconnect } = useWebSocketAuth({
    url,
    enabled,
    // Notifications are inherently per-user; the server rejects
    // anonymous connections. Without this gate the hook would open a
    // token-less socket on app mount, the consumer would close 4001,
    // and reconnects would be suppressed for the rest of the session.
    requireAuth: true,
    onMessage: handleMessage,
    onOpen: () => {
      setConnectionState("connected");
      recentNotificationsRef.current = [];
      updateRecent();
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      heartbeatRef.current = setInterval(() => {
        sendRef.current?.(JSON.stringify({ type: "ping" }));
      }, heartbeatInterval);
    },
    onClose: () => {
      setConnectionState("disconnected");
      setSessionId(null);
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    },
  });

  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  useEffect(() => {
    if (!isConnected) setConnectionState("disconnected");
    else setConnectionState(isAuthenticated ? "connected" : "connecting");
  }, [isConnected, isAuthenticated]);

  useNetworkStatus({
    onResume: () => {
      if (enabled && !isConnected) reconnect();
    },
    onOnline: () => {
      if (enabled && !isConnected) reconnect();
    },
    resumeThreshold: 1000,
    enabled,
  });

  const sendPing = useCallback(() => {
    send(JSON.stringify({ type: "ping" }));
  }, [send]);

  return {
    connectionState,
    sessionId,
    recentNotifications,
    reconnect,
    sendPing,
    clearRecent,
  };
}

export default useNotificationWebSocket;
