/**
 * useChatAgentMessageHandler
 *
 * Wraps the WebSocket message dispatcher that routes incoming agent frames to
 * the appropriate stream handlers. Extracted from ChatTray's
 * `handleAgentMessage` (188-line switch over 10+ message types).
 *
 * The returned callback is the `onMessage` handler for `useWebSocketAuth`.
 * It is intentionally bound only to the `updateMessageApprovalStatus`
 * reference from the stream handlers — all other handler references are
 * stable useCallback returns, and approval state is read through
 * `pendingApprovalRef.current` (not the React state value), so the
 * WebSocket callback stays stable across renders.
 */

import React, { useCallback } from "react";
import { ChatMessageProps } from "../../../widgets/chat/ChatMessage";
import type {
  CompactionNotice,
  ContextStatus,
  MessageData,
} from "../../../chat/types";
import type { PendingApproval } from "./ApprovalOverlay";
import type { UseChatStreamHandlersReturn } from "./useChatStreamHandlers";

export interface UseChatAgentMessageHandlerParams {
  /**
   * Ref mirroring the latest `pendingApproval` state. Read inside the
   * dispatcher closure so the callback stays stable while still reacting
   * to the most recent approval value.
   */
  pendingApprovalRef: React.RefObject<PendingApproval | null>;
  setPendingApproval: React.Dispatch<
    React.SetStateAction<PendingApproval | null>
  >;
  setShowApprovalModal: React.Dispatch<React.SetStateAction<boolean>>;
  setWsError: React.Dispatch<React.SetStateAction<string | null>>;
  setChat: React.Dispatch<React.SetStateAction<ChatMessageProps[]>>;
  setServerMessages: React.Dispatch<React.SetStateAction<ChatMessageProps[]>>;
  setContextStatus: React.Dispatch<React.SetStateAction<ContextStatus | null>>;
  setCompactionNotice: React.Dispatch<
    React.SetStateAction<CompactionNotice | null>
  >;
  streamHandlers: UseChatStreamHandlersReturn;
}

export function useChatAgentMessageHandler({
  pendingApprovalRef,
  setPendingApproval,
  setShowApprovalModal,
  setWsError,
  setChat,
  setServerMessages,
  setContextStatus,
  setCompactionNotice,
  streamHandlers,
}: UseChatAgentMessageHandlerParams): (event: MessageEvent) => void {
  const {
    updateMessageApprovalStatus,
    appendStreamingTokenToChat,
    appendThoughtToMessage,
    mergeSourcesIntoMessage,
    finalizeStreamingResponse,
    handleCompleteMessage,
  } = streamHandlers;

  return useCallback(
    (event: MessageEvent) => {
      try {
        const messageData: MessageData = JSON.parse(event.data);
        if (!messageData) return;
        const { type: msgType, content, data } = messageData;
        const currentApproval = pendingApprovalRef.current;

        console.log("[ChatTray WebSocket] Received message:", {
          type: msgType,
          hasContent: !!content,
          hasSources: !!data?.sources,
          sourceCount: data?.sources?.length,
          hasTimeline: !!data?.timeline,
          timelineCount: data?.timeline?.length,
          message_id: data?.message_id,
          approval_decision: data?.approval_decision,
          has_pending_tool_call: !!data?.pending_tool_call,
        });

        if (data?.approval_decision && data?.message_id) {
          updateMessageApprovalStatus(
            data.message_id,
            data.approval_decision as "approved" | "rejected"
          );
        }

        switch (msgType) {
          case "ASYNC_START":
            appendStreamingTokenToChat(content, data?.message_id);
            break;
          case "ASYNC_CONTENT":
            appendStreamingTokenToChat(content, data?.message_id);
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              updateMessageApprovalStatus(
                currentApproval.messageId,
                "approved"
              );
            }
            break;
          case "ASYNC_THOUGHT":
            appendThoughtToMessage(content, data);
            break;
          case "ASYNC_SOURCES":
            mergeSourcesIntoMessage(data?.sources, data?.message_id);
            break;
          case "ASYNC_APPROVAL_NEEDED":
            // NOTE: No sub-tool unwrapping (_sub_tool_name) needed here.
            // ChatTray handles document-level chat which talks to a document
            // agent directly — it never goes through ask_document, so nested
            // sub-agent approvals don't occur. Sub-tool unwrapping is only
            // relevant in CorpusChat.
            if (data?.pending_tool_call && data?.message_id) {
              setPendingApproval({
                messageId: data.message_id,
                toolCall: data.pending_tool_call,
              });
              setShowApprovalModal(true);

              setChat((prev) =>
                prev.map((msg) =>
                  msg.messageId === data.message_id
                    ? { ...msg, approvalStatus: "awaiting" as const }
                    : msg
                )
              );
              setServerMessages((prev) =>
                prev.map((msg) =>
                  msg.messageId === data.message_id
                    ? { ...msg, approvalStatus: "awaiting" as const }
                    : msg
                )
              );
            }
            break;
          case "ASYNC_APPROVAL_RESULT":
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              setShowApprovalModal(false);
              if (data?.decision) {
                updateMessageApprovalStatus(
                  currentApproval.messageId,
                  data.decision as "approved" | "rejected"
                );
              }
            }
            break;
          case "ASYNC_RESUME":
            // Agent is resuming after approval.  Unlike CorpusChat (which has
            // an explicit isProcessing state), ChatTray derives its processing
            // indicator from message state (isAssistantResponding), so no
            // additional state update is needed here.
            break;
          case "ASYNC_FINISH":
            finalizeStreamingResponse(
              content,
              data?.sources,
              data?.message_id,
              data?.timeline
            );
            setCompactionNotice(null);
            if (data?.context_status) {
              setContextStatus(data.context_status as ContextStatus);
            }
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              if (data?.approval_decision) {
                updateMessageApprovalStatus(
                  currentApproval.messageId,
                  data.approval_decision as "approved" | "rejected"
                );
              }
            }
            break;
          case "ASYNC_ERROR":
            // Set error state for the banner, but ALSO finalize the response
            // with the error content so it appears as a chat message.
            setWsError(data?.error || "Agent error");
            finalizeStreamingResponse(
              data?.error || "An unknown error occurred.",
              [],
              data?.message_id
            );
            break;
          case "SYNC_CONTENT": {
            setChat((prev) => [
              ...prev,
              {
                messageId: data?.message_id || `asst_${Date.now()}`,
                user: "Assistant",
                content: content,
                timestamp: new Date().toLocaleString(),
                isAssistant: true,
                isComplete: true,
              },
            ]);

            const sourcesToPass =
              data?.sources && Array.isArray(data.sources)
                ? data.sources
                : undefined;
            const timelineToPass =
              data?.timeline && Array.isArray(data.timeline)
                ? data.timeline
                : undefined;
            console.log(
              "[ChatTray WebSocket] SYNC_CONTENT sources:",
              sourcesToPass,
              "timeline:",
              timelineToPass
            );
            handleCompleteMessage(
              content,
              sourcesToPass,
              data?.message_id,
              undefined,
              timelineToPass
            );
            break;
          }
          default:
            console.warn("Unknown message type:", msgType);
            break;
        }
      } catch (err) {
        console.error("Failed to parse WS message:", err);
      }
    },
    [
      pendingApprovalRef,
      setPendingApproval,
      setShowApprovalModal,
      setWsError,
      setChat,
      setServerMessages,
      setContextStatus,
      setCompactionNotice,
      updateMessageApprovalStatus,
      appendStreamingTokenToChat,
      appendThoughtToMessage,
      mergeSourcesIntoMessage,
      finalizeStreamingResponse,
      handleCompleteMessage,
    ]
  );
}
