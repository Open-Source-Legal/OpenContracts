/**
 * useChatSendHandlers
 *
 * Bundles the three user-facing actions that emit frames over the chat
 * WebSocket: typing-driven send, programmatic immediate send (for the
 * `initialMessage` prop), and approval-decision send. Extracted from
 * ChatTray so the composer doesn't own debounce locks and ok/error
 * branching.
 *
 * The hook accepts `updateMessageApprovalStatus` as an input (rather than
 * defining it here) because that mutator belongs in `useChatStreamHandlers`
 * — both the stream pipeline and the send pipeline write through it, and
 * locating it with its sibling stream mutators keeps the data-mutation
 * surface co-located.
 */

import React, { useCallback, useMemo } from "react";
import { ChatMessageProps } from "../../../widgets/chat/ChatMessage";
import { CHAT_SEND_LOCK_MS } from "../../../../assets/configurations/constants";
import type { PendingApproval } from "../../../chat/types";

export interface UseChatSendHandlersParams {
  /** WebSocket send function from useWebSocketAuth — returns true on success. */
  wsSend: (payload: string) => boolean;
  /** Whether the WebSocket is currently open and authenticated. */
  wsReady: boolean;
  /** User email used to label outgoing messages; falls back to "You". */
  userEmail: string | undefined;
  /** Current value of the chat input textarea. */
  newMessage: string;
  /** Current pending approval (read for sendApprovalDecision). */
  pendingApproval: PendingApproval | null;
  /**
   * Debounce lock shared with the composer. Mutated by the send handlers to
   * prevent duplicate sends within `CHAT_SEND_LOCK_MS` ms after a send.
   */
  sendingLockRef: React.MutableRefObject<boolean>;
  setChat: React.Dispatch<React.SetStateAction<ChatMessageProps[]>>;
  setNewMessage: React.Dispatch<React.SetStateAction<string>>;
  setWsError: React.Dispatch<React.SetStateAction<string | null>>;
  setShowApprovalModal: React.Dispatch<React.SetStateAction<boolean>>;
  setPendingApproval: React.Dispatch<
    React.SetStateAction<PendingApproval | null>
  >;
  /** Forwarded from useChatStreamHandlers for optimistic approval updates. */
  updateMessageApprovalStatus: (
    messageId: string,
    status: "approved" | "rejected"
  ) => void;
}

export interface UseChatSendHandlersReturn {
  /** Send the contents of `newMessage` over the WebSocket; clears input on success. */
  sendMessageOverSocket: () => void;
  /** Send approval/rejection for the current pending tool call. */
  sendApprovalDecision: (approved: boolean) => void;
  /** Send arbitrary text immediately, bypassing the `newMessage` state. */
  sendTextImmediately: (text: string) => void;
}

export function useChatSendHandlers({
  wsSend,
  wsReady,
  userEmail,
  newMessage,
  pendingApproval,
  sendingLockRef,
  setChat,
  setNewMessage,
  setWsError,
  setShowApprovalModal,
  setPendingApproval,
  updateMessageApprovalStatus,
}: UseChatSendHandlersParams): UseChatSendHandlersReturn {
  // Shared implementation for the two outbound text-send paths. Both
  // sendMessageOverSocket (input-driven) and sendTextImmediately (programmatic)
  // share: acquire lock → trim guard → wsSend → optimistic chat append →
  // release lock in finally. Keeping them in one place ensures fixes apply to
  // both. `onSuccess` is the only divergence: sendMessageOverSocket clears the
  // input via setNewMessage, sendTextImmediately is a no-op.
  const sendTextOverSocket = useCallback(
    (trimmed: string, onSuccess?: () => void): void => {
      if (!trimmed || !wsReady) return;
      if (sendingLockRef.current) return;

      sendingLockRef.current = true;

      try {
        const ok = wsSend(JSON.stringify({ query: trimmed }));
        if (!ok) {
          setWsError("Failed to send message. Please try again.");
          return;
        }
        setChat((prev) => [
          ...prev,
          {
            messageId: `user_${Date.now()}_${Math.random()
              .toString(36)
              .substring(2)}`,
            user: userEmail || "You",
            content: trimmed,
            timestamp: new Date().toLocaleString(),
            isAssistant: false,
            isComplete: false,
          },
        ]);
        onSuccess?.();
        setWsError(null);
      } catch (err) {
        console.error("Failed to send message:", err);
        setWsError("Failed to send message. Please try again.");
      } finally {
        setTimeout(() => {
          sendingLockRef.current = false;
        }, CHAT_SEND_LOCK_MS);
      }
    },
    [wsReady, userEmail, wsSend, sendingLockRef, setChat, setWsError]
  );

  // These three guards intentionally duplicate the checks inside
  // sendTextOverSocket: this is the user-facing entry point, so it emits
  // ``console.warn`` for observability when an interactive send is dropped.
  // sendTextOverSocket is the authoritative (silent) guard — both code paths
  // share the lock/empty/wsReady invariants, but only this caller surfaces
  // them to the dev console.
  const sendMessageOverSocket = useCallback((): void => {
    const trimmed = newMessage.trim();
    if (!trimmed) return;
    if (!wsReady) {
      console.warn("WebSocket not ready yet");
      return;
    }
    if (sendingLockRef.current) {
      console.warn("Message is already being sent, ignoring duplicate send.");
      return;
    }
    sendTextOverSocket(trimmed, () => setNewMessage(""));
  }, [newMessage, wsReady, sendingLockRef, sendTextOverSocket, setNewMessage]);

  const sendApprovalDecision = useCallback(
    (approved: boolean): void => {
      if (!pendingApproval || !wsReady) {
        console.warn("Cannot send approval decision - missing requirements");
        return;
      }

      try {
        const messageData = {
          approval_decision: approved,
          llm_message_id: pendingApproval.messageId,
        };

        const ok = wsSend(JSON.stringify(messageData));
        if (!ok) {
          setWsError("Failed to send approval decision. Please try again.");
          setShowApprovalModal(true);
          return;
        }

        setShowApprovalModal(false);

        updateMessageApprovalStatus(
          pendingApproval.messageId,
          approved ? "approved" : "rejected"
        );

        setPendingApproval(null);
        setWsError(null);
      } catch (err) {
        console.error("Failed to send approval decision:", err);
        setWsError("Failed to send approval decision. Please try again.");
        setShowApprovalModal(true);
      }
    },
    [
      pendingApproval,
      wsReady,
      wsSend,
      updateMessageApprovalStatus,
      setWsError,
      setShowApprovalModal,
      setPendingApproval,
    ]
  );

  const sendTextImmediately = useCallback(
    (text: string): void => {
      sendTextOverSocket(text.trim());
    },
    [sendTextOverSocket]
  );

  // Memoize the bundle so callers can safely include it (or one of its
  // members) in a ``useCallback`` / ``useMemo`` dependency array without
  // forcing a fresh closure on every render. Matches the contract of the
  // sibling ``useChatStreamHandlers`` hook.
  return useMemo(
    () => ({
      sendMessageOverSocket,
      sendApprovalDecision,
      sendTextImmediately,
    }),
    [sendMessageOverSocket, sendApprovalDecision, sendTextImmediately]
  );
}
