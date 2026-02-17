/**
 * useAgentChat - Unified hook for agent chat WebSocket communication.
 *
 * This hook consolidates WebSocket logic from CorpusChat.tsx and ChatTray.tsx,
 * connecting to the unified backend consumer (ws/agent-chat/).
 *
 * Features:
 * - Automatic WebSocket connection management
 * - Streaming message support (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH)
 * - Thought/timeline tracking for agent reasoning
 * - Source pinning integration with ChatSourceAtom
 * - Approval flow for permission-required tools
 * - Conversation persistence
 * - Automatic reconnection on page visibility change (Issue #697)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { authToken, userObj } from "../graphql/cache";
import { useNetworkStatus } from "./useNetworkStatus";
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
// WebSocket URL Builder
// ============================================================================

/**
 * Get environment variable from Vite or CRA style.
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

/**
 * Resolve WebSocket base URL from env vars or window.location.
 */
function resolveWsBaseUrl(): string {
  const envUrl =
    getEnvVar("VITE_WS_URL", "REACT_APP_WS_URL") ||
    getEnvVar("VITE_API_URL", "REACT_APP_API_URL");

  if (envUrl) return envUrl.replace(/\/+$/, "");

  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${
    window.location.host
  }`;
}

/**
 * Build WebSocket URL for the unified agent consumer.
 */
export function getUnifiedAgentWebSocketUrl(
  context: AgentChatContext,
  token?: string
): string {
  const wsBaseUrl = resolveWsBaseUrl();
  const normalizedBaseUrl = wsBaseUrl
    .replace(/\/+$/, "")
    .replace(/^http/, "ws")
    .replace(/^https/, "wss");

  let url = `${normalizedBaseUrl}/ws/agent-chat/`;
  const params: string[] = [];

  if (context.corpusId) {
    params.push(`corpus_id=${encodeURIComponent(context.corpusId)}`);
  }
  if (context.documentId) {
    params.push(`document_id=${encodeURIComponent(context.documentId)}`);
  }
  if (context.agentId) {
    params.push(`agent_id=${encodeURIComponent(context.agentId)}`);
  }
  if (context.conversationId) {
    params.push(
      `conversation_id=${encodeURIComponent(context.conversationId)}`
    );
  }
  if (token) {
    params.push(`token=${encodeURIComponent(token)}`);
  }

  if (params.length > 0) {
    url += `?${params.join("&")}`;
  }

  return url;
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

  // Auth state
  const auth_token = useReactiveVar(authToken);
  const user_obj = useReactiveVar(userObj);

  // WebSocket state
  const socketRef = useRef<WebSocket | null>(null);
  const sendingLockRef = useRef<boolean>(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reconnect trigger - increment to force reconnection (Issue #697)
  const [reconnectTrigger, setReconnectTrigger] = useState(0);
  // Guard to prevent duplicate reconnection attempts
  const isReconnectingRef = useRef<boolean>(false);

  // Message state
  const [messages, setMessages] = useState<ChatMessageProps[]>([]);

  // Approval state
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);

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
  // WebSocket Management
  // ========================================================================

  useEffect(() => {
    // Need at least one context identifier
    if (!context.corpusId && !context.documentId && !context.agentId) {
      return;
    }

    // Set reconnecting flag to prevent duplicate attempts
    isReconnectingRef.current = true;

    const wsUrl = getUnifiedAgentWebSocketUrl(context, auth_token || undefined);
    const newSocket = new WebSocket(wsUrl);

    newSocket.onopen = () => {
      isReconnectingRef.current = false;
      setIsConnected(true);
      setError(null);
      console.debug("[useAgentChat] WebSocket connected:", wsUrl);
    };

    newSocket.onerror = (event) => {
      isReconnectingRef.current = false;
      setIsConnected(false);
      setError("Error connecting to the chat server.");
      console.error("[useAgentChat] WebSocket error:", event);
    };

    newSocket.onmessage = (event) => {
      try {
        const messageData: AgentMessageData = JSON.parse(event.data);
        if (!messageData) return;

        const { type: msgType, content, data } = messageData;

        // Handle approval status updates
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

          case "ASYNC_CONTENT":
            appendStreamingToken(content, data?.message_id);
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
              updateMessageApprovalStatus(
                pendingApproval.messageId,
                "approved"
              );
            }
            break;

          case "ASYNC_THOUGHT":
            appendThought(content, data);
            break;

          case "ASYNC_SOURCES":
            mergeSourcesIntoMessage(data?.sources, data?.message_id);
            break;

          case "ASYNC_APPROVAL_NEEDED":
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

          case "ASYNC_APPROVAL_RESULT":
            // Informational – backend echoes the user's decision.
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
              setShowApprovalModal(false);
              if (data?.decision) {
                updateMessageApprovalStatus(
                  pendingApproval.messageId,
                  data.decision as "approved" | "rejected"
                );
              }
            }
            break;

          case "ASYNC_RESUME":
            // Agent is resuming after approval – keep processing indicator.
            setIsProcessing(true);
            break;

          case "ASYNC_FINISH":
            finalizeResponse(
              content,
              data?.sources,
              data?.message_id,
              data?.timeline
            );
            setIsProcessing(false);
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
              if (data?.approval_decision) {
                updateMessageApprovalStatus(
                  pendingApproval.messageId,
                  data.approval_decision as "approved" | "rejected"
                );
              }
            }
            break;

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
    };

    newSocket.onclose = (event) => {
      isReconnectingRef.current = false;
      setIsConnected(false);
      console.debug("[useAgentChat] WebSocket closed:", event);
    };

    socketRef.current = newSocket;

    return () => {
      isReconnectingRef.current = false;
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [
    context.corpusId,
    context.documentId,
    context.agentId,
    context.conversationId,
    auth_token,
    reconnectTrigger, // Added for Issue #697 - triggers reconnection when incremented
    appendStreamingToken,
    appendThought,
    mergeSourcesIntoMessage,
    finalizeResponse,
    handleCompleteMessage,
    updateMessageApprovalStatus,
    pendingApproval,
  ]);

  // Send initial message once connected
  useEffect(() => {
    if (isConnected && pendingInitialRef.current) {
      const msg = pendingInitialRef.current;
      pendingInitialRef.current = undefined;

      // Use a slight delay to ensure socket is fully ready
      setTimeout(() => {
        if (
          socketRef.current &&
          socketRef.current.readyState === WebSocket.OPEN
        ) {
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
          socketRef.current.send(JSON.stringify({ query: msg }));
        }
      }, 100);
    }
  }, [isConnected, user_obj?.email]);

  // Reconnect when page becomes visible after being hidden (Issue #697)
  // This handles mobile devices where the app may be suspended when screen is locked
  const hasContext = !!(
    context.corpusId ||
    context.documentId ||
    context.agentId
  );

  useNetworkStatus({
    onResume: () => {
      console.debug("[useAgentChat] Page resumed, checking connection...");

      // Check if WebSocket is still connected and not already reconnecting
      if (
        hasContext &&
        !isReconnectingRef.current &&
        socketRef.current?.readyState !== WebSocket.OPEN &&
        socketRef.current?.readyState !== WebSocket.CONNECTING
      ) {
        console.debug(
          "[useAgentChat] WebSocket disconnected, triggering reconnection..."
        );
        // Trigger reconnection by incrementing the reconnectTrigger
        // This will cause the WebSocket useEffect to re-run and establish a new connection
        setReconnectTrigger((prev) => prev + 1);
      }
    },
    onOnline: () => {
      console.debug("[useAgentChat] Network online, checking connection...");

      // Reconnect if WebSocket is disconnected and not already reconnecting
      if (
        hasContext &&
        !isReconnectingRef.current &&
        socketRef.current?.readyState !== WebSocket.OPEN &&
        socketRef.current?.readyState !== WebSocket.CONNECTING
      ) {
        console.debug(
          "[useAgentChat] Triggering reconnection after network recovery..."
        );
        setReconnectTrigger((prev) => prev + 1);
      }
    },
    resumeThreshold: 1000, // 1 second hidden threshold
    enabled: hasContext,
  });

  // ========================================================================
  // Actions
  // ========================================================================

  const sendMessage = useCallback(
    (content: string): void => {
      const trimmed = content.trim();
      if (!trimmed || !socketRef.current || !isConnected || isProcessing)
        return;

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
        socketRef.current.send(JSON.stringify({ query: trimmed }));
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
    [isConnected, isProcessing, user_obj?.email]
  );

  const sendApprovalDecisionFn = useCallback(
    (approved: boolean): void => {
      if (!pendingApproval || !socketRef.current || !isConnected) {
        console.warn("[useAgentChat] Cannot send approval decision");
        return;
      }

      try {
        socketRef.current.send(
          JSON.stringify({
            approval_decision: approved,
            llm_message_id: pendingApproval.messageId,
          })
        );

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
    [pendingApproval, isConnected, updateMessageApprovalStatus]
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
    sendMessage,
    sendApprovalDecision: sendApprovalDecisionFn,
    setShowApprovalModal,
    clearError,
    selectedMessageId,
    setSelectedMessageId: setSelectedMessageIdFn,
  };
}

export default useAgentChat;
