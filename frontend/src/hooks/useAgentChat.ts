/**
 * useAgentChat - Unified hook for agent chat WebSocket communication.
 *
 * This hook consolidates WebSocket logic from CorpusChat.tsx and ChatTray.tsx,
 * connecting to the unified backend consumer (ws/agent-chat/).
 *
 * Features:
 * - Automatic WebSocket connection management (via useWebSocketAuth)
 * - Streaming message support (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH)
 * - Thought/timeline tracking for agent reasoning
 * - Source pinning integration with ChatSourceAtom
 * - Approval flow for permission-required tools
 * - Conversation persistence
 * - In-band token refresh (no socket churn on auth rotation)
 * - Automatic reconnection on page visibility change (Issue #697)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { userObj } from "../graphql/cache";
import { useNetworkStatus } from "./useNetworkStatus";
import { getUnifiedAgentWebSocket } from "../components/chat/get_websockets";
import { useWebSocketAuth } from "./useWebSocketAuth";
import {
  useChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
} from "../components/annotator/context/ChatSourceAtom";
import { MultipageAnnotationJson } from "../components/types";

// ============================================================================
// Types
// ============================================================================

/**
 * Source data from WebSocket messages (annotations, labels, text).
 */
export interface WebSocketSources {
  page: number;
  json: { start: number; end: number } | MultipageAnnotationJson;
  annotation_id: number;
  label: string;
  label_id: number;
  rawText: string;
}

/**
 * Timeline entry for agent reasoning display.
 */
export interface TimelineEntry {
  type: "thought" | "tool_call" | "tool_result";
  text: string;
  tool?: string;
  args?: any;
}

/**
 * WebSocket message structure from the backend.
 */
export interface AgentMessageData {
  type:
    | "ASYNC_START"
    | "ASYNC_CONTENT"
    | "ASYNC_FINISH"
    | "SYNC_CONTENT"
    | "ASYNC_THOUGHT"
    | "ASYNC_SOURCES"
    | "ASYNC_APPROVAL_NEEDED"
    | "ASYNC_APPROVAL_RESULT"
    | "ASYNC_RESUME"
    | "ASYNC_ERROR";
  content: string;
  data?: {
    sources?: WebSocketSources[];
    timeline?: TimelineEntry[];
    message_id?: string;
    tool_name?: string;
    args?: any;
    error?: string;
    pending_tool_call?: {
      name: string;
      arguments: any;
      tool_call_id?: string;
    };
    approval_decision?: string;
    [key: string]: any;
  };
}

/**
 * Chat message for display in the UI.
 */
export interface ChatMessageProps {
  messageId?: string;
  user: string;
  content: string;
  timestamp: string;
  isAssistant: boolean;
  hasSources?: boolean;
  hasTimeline?: boolean;
  timeline?: TimelineEntry[];
  isComplete?: boolean;
  approvalStatus?: "approved" | "rejected" | "awaiting";
}

/**
 * Pending approval state for tool execution.
 */
export interface PendingApproval {
  messageId: string;
  toolCall: {
    name: string;
    arguments: any;
    tool_call_id?: string;
  };
}

/**
 * Context status metadata from the backend (token usage, compaction info).
 */
export interface ContextStatus {
  used_tokens: number;
  context_window: number;
  was_compacted: boolean;
  tokens_before_compaction: number;
}

/**
 * Context configuration for the agent chat.
 */
export interface AgentChatContext {
  /** Corpus ID for corpus-scoped conversations */
  corpusId?: string;
  /** Document ID for document-scoped conversations */
  documentId?: string;
  /** Explicit agent ID to use (overrides defaults) */
  agentId?: string;
  /** Conversation ID to resume */
  conversationId?: string;
}

/**
 * Options for the useAgentChat hook.
 */
export interface UseAgentChatOptions {
  /** Context for the conversation (corpus, document, agent) */
  context: AgentChatContext;
  /** Skip loading conversation history (anonymous mode) */
  readOnly?: boolean;
  /** Initial message to send when connection is ready */
  initialMessage?: string;
  /** Callback when a message with sources is selected */
  onMessageSelect?: (messageId: string) => void;
}

/**
 * Return value of the useAgentChat hook.
 */
export interface UseAgentChatReturn {
  // State
  messages: ChatMessageProps[];
  isConnected: boolean;
  isProcessing: boolean;
  error: string | null;
  pendingApproval: PendingApproval | null;
  showApprovalModal: boolean;
  contextStatus: ContextStatus | null;

  // Actions
  sendMessage: (content: string) => void;
  sendApprovalDecision: (approved: boolean) => void;
  setShowApprovalModal: (show: boolean) => void;
  clearError: () => void;

  // Selected source state (from ChatSourceAtom)
  selectedMessageId: string | null;
  setSelectedMessageId: (id: string | null) => void;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useAgentChat(options: UseAgentChatOptions): UseAgentChatReturn {
  const {
    context,
    readOnly = false,
    initialMessage,
    onMessageSelect,
  } = options;

  // User state
  const user_obj = useReactiveVar(userObj);

  const sendingLockRef = useRef<boolean>(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Message state
  const [messages, setMessages] = useState<ChatMessageProps[]>([]);

  // Approval state
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);

  // Mirror `pendingApproval` in a ref so the WebSocket handler can read
  // the latest value without including `pendingApproval` in its dep array.
  // Without this, every approval-state transition would reconnect the socket
  // mid-conversation (issue #1296), dropping streaming tokens.
  const pendingApprovalRef = useRef<PendingApproval | null>(pendingApproval);
  useEffect(() => {
    pendingApprovalRef.current = pendingApproval;
  }, [pendingApproval]);

  // Context status (token usage, compaction info)
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(
    null
  );

  // Chat source state for annotation pinning
  const {
    messages: sourcedMessages,
    selectedMessageId,
    setChatSourceState,
  } = useChatSourceState();

  // Initial message ref (to send once connected)
  const pendingInitialRef = useRef<string | undefined>(initialMessage);

  // ========================================================================
  // Message Handlers
  // ========================================================================

  /**
   * Append a streaming token to the last assistant message (or create new).
   */
  const appendStreamingToken = useCallback(
    (token: string, overrideMessageId?: string): string => {
      if (!token) return "";

      let messageId = "";
      setMessages((prev) => {
        const lastMessage = prev[prev.length - 1];

        if (lastMessage && lastMessage.isAssistant && !lastMessage.isComplete) {
          messageId = lastMessage.messageId || "";
          return [
            ...prev.slice(0, -1),
            {
              ...lastMessage,
              content: lastMessage.content + token,
            },
          ];
        } else {
          messageId =
            overrideMessageId ||
            `msg_${Date.now()}_${Math.random().toString(36).substr(2)}`;
          return [
            ...prev,
            {
              messageId,
              user: "Assistant",
              content: token,
              timestamp: new Date().toLocaleString(),
              isAssistant: true,
              isComplete: false,
            },
          ];
        }
      });

      return messageId;
    },
    []
  );

  /**
   * Append thought/tool call to message timeline.
   */
  const appendThought = useCallback(
    (thoughtText: string, data: AgentMessageData["data"]): void => {
      const messageId = data?.message_id;
      if (!messageId || !thoughtText) return;

      let entryType: TimelineEntry["type"] = "thought";
      if (data?.tool_name && data?.args) entryType = "tool_call";
      else if (data?.tool_name && !data?.args) entryType = "tool_result";

      const newEntry: TimelineEntry = {
        type: entryType,
        text: thoughtText,
        tool: data?.tool_name,
        args: data?.args,
      };

      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.messageId === messageId);
        if (idx === -1) {
          return [
            ...prev,
            {
              messageId,
              user: "Assistant",
              content: "",
              timestamp: new Date().toLocaleString(),
              isAssistant: true,
              hasTimeline: true,
              timeline: [newEntry],
              isComplete: false,
            },
          ];
        }

        const msg = prev[idx];
        const timeline = msg.timeline
          ? [...msg.timeline, newEntry]
          : [newEntry];
        return [
          ...prev.slice(0, idx),
          { ...msg, hasTimeline: true, timeline, isComplete: false },
          ...prev.slice(idx + 1),
        ];
      });
    },
    []
  );

  /**
   * Store sources in ChatSourceAtom for annotation pinning.
   */
  const handleCompleteMessage = useCallback(
    (
      content: string,
      sourcesData?: WebSocketSources[],
      overrideId?: string,
      overrideCreatedAt?: string,
      timelineData?: TimelineEntry[]
    ): void => {
      const messageId = overrideId ?? `msg_${Date.now()}`;
      const messageTimestamp = overrideCreatedAt
        ? new Date(overrideCreatedAt).toISOString()
        : new Date().toISOString();

      const mappedSources = mapWebSocketSourcesToChatMessageSources(
        sourcesData,
        messageId
      );

      setChatSourceState((prev) => {
        const existingIndex = prev.messages.findIndex(
          (m) => m.messageId === messageId
        );

        if (existingIndex !== -1) {
          const existingMsg = prev.messages[existingIndex];
          const updatedMsg = {
            ...existingMsg,
            content,
            timestamp: messageTimestamp,
            sources: mappedSources.length ? mappedSources : existingMsg.sources,
          };

          const updatedMessages = [...prev.messages];
          updatedMessages[existingIndex] = updatedMsg;
          return { ...prev, messages: updatedMessages };
        }

        return {
          ...prev,
          messages: [
            ...prev.messages,
            {
              messageId,
              content,
              timestamp: messageTimestamp,
              sources: mappedSources,
            },
          ],
          selectedMessageId: overrideId ? prev.selectedMessageId : messageId,
        };
      });
    },
    [setChatSourceState]
  );

  /**
   * Merge additional sources into existing message.
   */
  const mergeSourcesIntoMessage = useCallback(
    (
      sourcesData: WebSocketSources[] | undefined,
      overrideId?: string
    ): void => {
      if (!sourcesData?.length || !overrideId) return;

      const mappedSources = mapWebSocketSourcesToChatMessageSources(
        sourcesData,
        overrideId
      );

      setChatSourceState((prev) => {
        const idx = prev.messages.findIndex((m) => m.messageId === overrideId);
        if (idx === -1) {
          return {
            ...prev,
            messages: [
              ...prev.messages,
              {
                messageId: overrideId,
                content: "",
                timestamp: new Date().toISOString(),
                sources: mappedSources,
              },
            ],
          };
        }

        const existing = prev.messages[idx];
        const mergedSources = [
          ...existing.sources,
          ...mappedSources.filter(
            (ms) =>
              !existing.sources.some(
                (es) => es.annotation_id === ms.annotation_id
              )
          ),
        ];

        const updatedMessages = [...prev.messages];
        updatedMessages[idx] = { ...existing, sources: mergedSources };
        return { ...prev, messages: updatedMessages };
      });

      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.messageId === overrideId);
        if (idx === -1) return prev;
        return [
          ...prev.slice(0, idx),
          { ...prev[idx], hasSources: true },
          ...prev.slice(idx + 1),
        ];
      });
    },
    [setChatSourceState]
  );

  /**
   * Finalize a streaming response with final content.
   */
  const finalizeResponse = useCallback(
    (
      content: string,
      sourcesData?: WebSocketSources[],
      overrideId?: string,
      timelineData?: TimelineEntry[]
    ): void => {
      let lastMsgId: string | undefined;

      setMessages((prev) => {
        if (!prev.length) return prev;

        let updateIdx = prev.findIndex((m) => m.messageId === overrideId);
        if (updateIdx === -1) {
          const lastIdxRev = [...prev]
            .reverse()
            .findIndex((m) => m.isAssistant);
          if (lastIdxRev === -1) return prev;
          updateIdx = prev.length - 1 - lastIdxRev;
        }

        const updatedMessages = [...prev];
        const assistantMsg = updatedMessages[updateIdx];
        lastMsgId = assistantMsg.messageId;

        updatedMessages[updateIdx] = {
          ...assistantMsg,
          content,
          isComplete: true,
          hasSources: sourcesData
            ? sourcesData.length > 0
            : assistantMsg.hasSources,
          hasTimeline: timelineData
            ? timelineData.length > 0
            : assistantMsg.hasTimeline,
        };

        return updatedMessages;
      });

      if (lastMsgId) {
        handleCompleteMessage(
          content,
          sourcesData,
          lastMsgId,
          undefined,
          timelineData
        );
      }
    },
    [handleCompleteMessage]
  );

  /**
   * Update message approval status.
   */
  const updateMessageApprovalStatus = useCallback(
    (messageId: string, status: "approved" | "rejected"): void => {
      setPendingApproval((current) => {
        if (current?.messageId === messageId) return null;
        return current;
      });

      setMessages((prev) =>
        prev.map((msg) =>
          msg.messageId === messageId
            ? { ...msg, approvalStatus: status, isComplete: true }
            : msg
        )
      );
    },
    []
  );

  // ========================================================================
  // WebSocket Management (via useWebSocketAuth)
  // ========================================================================

  const url = getUnifiedAgentWebSocket(context);
  const enabled = !!(context.corpusId || context.documentId || context.agentId);

  const handleAgentMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const messageData: AgentMessageData = JSON.parse(event.data);
        if (!messageData) return;

        const { type: msgType, content, data } = messageData;

        if (data?.approval_decision && data?.message_id) {
          updateMessageApprovalStatus(
            data.message_id,
            data.approval_decision as "approved" | "rejected"
          );
        }

        switch (msgType) {
          case "ASYNC_START":
            setIsProcessing(true);
            appendStreamingToken(content, data?.message_id);
            break;

          case "ASYNC_CONTENT": {
            appendStreamingToken(content, data?.message_id);
            const currentApproval = pendingApprovalRef.current;
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
          }

          case "ASYNC_THOUGHT":
            appendThought(content, data);
            break;

          case "ASYNC_SOURCES":
            mergeSourcesIntoMessage(data?.sources, data?.message_id);
            break;

          case "ASYNC_APPROVAL_NEEDED":
            // NOTE: No sub-tool unwrapping (_sub_tool_name) needed here.
            // This hook is used for document-level and generic chat contexts
            // that talk to agents directly — never via ask_document. Sub-tool
            // unwrapping for nested corpus→document approvals lives only in
            // CorpusChat.
            if (data?.pending_tool_call && data?.message_id) {
              setPendingApproval({
                messageId: data.message_id,
                toolCall: data.pending_tool_call,
              });
              setShowApprovalModal(true);

              setMessages((prev) =>
                prev.map((msg) =>
                  msg.messageId === data.message_id
                    ? { ...msg, approvalStatus: "awaiting" as const }
                    : msg
                )
              );
            }
            break;

          case "ASYNC_APPROVAL_RESULT": {
            // Informational – backend echoes the user's decision.
            const currentApproval = pendingApprovalRef.current;
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
          }

          case "ASYNC_RESUME":
            setIsProcessing(true);
            break;

          case "ASYNC_FINISH": {
            finalizeResponse(
              content,
              data?.sources,
              data?.message_id,
              data?.timeline
            );
            setIsProcessing(false);
            if (data?.context_status) {
              setContextStatus(data.context_status as ContextStatus);
            }
            const currentApproval = pendingApprovalRef.current;
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
          }

          case "ASYNC_ERROR":
            setError(data?.error || "Agent error");
            finalizeResponse(
              data?.error || "An error occurred.",
              [],
              data?.message_id
            );
            setIsProcessing(false);
            break;

          case "SYNC_CONTENT":
            setMessages((prev) => [
              ...prev,
              {
                messageId: data?.message_id || `asst_${Date.now()}`,
                user: "Assistant",
                content,
                timestamp: new Date().toLocaleString(),
                isAssistant: true,
                isComplete: true,
              },
            ]);
            handleCompleteMessage(
              content,
              data?.sources,
              data?.message_id,
              undefined,
              data?.timeline
            );
            break;

          default:
            console.warn("[useAgentChat] Unknown message type:", msgType);
        }
      } catch (err) {
        console.error("[useAgentChat] Failed to parse message:", err);
      }
    },
    [
      appendStreamingToken,
      appendThought,
      mergeSourcesIntoMessage,
      finalizeResponse,
      handleCompleteMessage,
      updateMessageApprovalStatus,
    ]
  );

  const { isConnected, send, reconnect } = useWebSocketAuth({
    url,
    enabled,
    onMessage: handleAgentMessage,
    onOpen: () => setError(null),
    onAuthInvalid: () =>
      setError("Authentication failed. Please log in again."),
  });

  // Send initial message once connected
  useEffect(() => {
    if (isConnected && pendingInitialRef.current) {
      const msg = pendingInitialRef.current;
      pendingInitialRef.current = undefined;

      // Use a slight delay to ensure socket is fully ready
      setTimeout(() => {
        const ok = send(JSON.stringify({ query: msg }));
        if (ok) {
          setMessages((prev) => [
            ...prev,
            {
              messageId: `user_${Date.now()}`,
              user: user_obj?.email || "You",
              content: msg,
              timestamp: new Date().toLocaleString(),
              isAssistant: false,
              isComplete: true,
            },
          ]);
        }
      }, 100);
    }
  }, [isConnected, user_obj?.email, send]);

  // Reconnect when page becomes visible after being hidden (Issue #697)
  const hasContext = !!(
    context.corpusId ||
    context.documentId ||
    context.agentId
  );

  useNetworkStatus({
    onResume: () => {
      if (hasContext && !isConnected) reconnect();
    },
    onOnline: () => {
      if (hasContext && !isConnected) reconnect();
    },
    resumeThreshold: 1000,
    enabled: hasContext,
  });

  // ========================================================================
  // Actions
  // ========================================================================

  const sendMessage = useCallback(
    (content: string): void => {
      const trimmed = content.trim();
      if (!trimmed || !isConnected || isProcessing) return;

      if (sendingLockRef.current) {
        console.warn("[useAgentChat] Message already being sent");
        return;
      }

      sendingLockRef.current = true;

      try {
        setMessages((prev) => [
          ...prev,
          {
            messageId: `user_${Date.now()}_${Math.random()
              .toString(36)
              .substr(2)}`,
            user: user_obj?.email || "You",
            content: trimmed,
            timestamp: new Date().toLocaleString(),
            isAssistant: false,
            isComplete: true,
          },
        ]);
        const ok = send(JSON.stringify({ query: trimmed }));
        if (!ok) {
          setError("Failed to send message. Please try again.");
          return;
        }
        setError(null);
      } catch (err) {
        console.error("[useAgentChat] Failed to send message:", err);
        setError("Failed to send message. Please try again.");
      } finally {
        setTimeout(() => {
          sendingLockRef.current = false;
        }, 300);
      }
    },
    [isConnected, isProcessing, user_obj?.email, send]
  );

  const sendApprovalDecisionFn = useCallback(
    (approved: boolean): void => {
      if (!pendingApproval || !isConnected) {
        console.warn("[useAgentChat] Cannot send approval decision");
        return;
      }

      try {
        const ok = send(
          JSON.stringify({
            approval_decision: approved,
            llm_message_id: pendingApproval.messageId,
          })
        );

        if (!ok) {
          setError("Failed to send approval decision. Please try again.");
          setShowApprovalModal(true);
          return;
        }

        setShowApprovalModal(false);
        updateMessageApprovalStatus(
          pendingApproval.messageId,
          approved ? "approved" : "rejected"
        );
        setPendingApproval(null);
        setError(null);
      } catch (err) {
        console.error("[useAgentChat] Failed to send approval decision:", err);
        setError("Failed to send approval decision. Please try again.");
        setShowApprovalModal(true);
      }
    },
    [pendingApproval, isConnected, updateMessageApprovalStatus, send]
  );

  const clearError = useCallback(() => setError(null), []);

  const setSelectedMessageIdFn = useCallback(
    (id: string | null) => {
      setChatSourceState((prev) => ({
        ...prev,
        selectedMessageId: id,
        selectedSourceIndex: null,
      }));
    },
    [setChatSourceState]
  );

  // ========================================================================
  // Return
  // ========================================================================

  return {
    messages,
    isConnected,
    isProcessing,
    error,
    pendingApproval,
    showApprovalModal,
    contextStatus,
    sendMessage,
    sendApprovalDecision: sendApprovalDecisionFn,
    setShowApprovalModal,
    clearError,
    selectedMessageId,
    setSelectedMessageId: setSelectedMessageIdFn,
  };
}

export default useAgentChat;
