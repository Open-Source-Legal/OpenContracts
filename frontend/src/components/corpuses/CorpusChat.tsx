/**
 * CorpusChat Component - Similar to ChatTray, but for corpuses.
 *
 * This component connects to our WebSocket backend for both authenticated
 * and anonymous users. Anonymous users can chat on public corpuses.
 * It will:
 *   1) Load existing corpus-specific conversation data from a GraphQL query (GET_CORPUS_CONVERSATIONS).
 *   2) Open a WebSocket to stream new messages with partial updates
 *      (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH) or synchronous messages (SYNC_CONTENT).
 *   3) Display those messages in real time, appending them to the chat.
 *   4) Allow sending user queries through the socket.
 *
 * Note: The backend handles authentication - anonymous users are allowed on public corpuses,
 * but will receive a 4003 close code if attempting to access non-public corpuses.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLazyQuery, useQuery, useReactiveVar } from "@apollo/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowLeft,
  AtSign,
  Home,
  MessageCircle,
  Send,
} from "lucide-react";
import { Button } from "@os-legal/ui";
import {
  CONVERSATION_TYPE,
  WS_ERROR_CONTEXT_EXHAUSTED,
} from "../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

import {
  GET_CORPUS_CONVERSATIONS,
  GetCorpusConversationsInputs,
  GetCorpusConversationsOutputs,
  GET_CHAT_MESSAGES,
  GetChatMessagesInputs,
  GetChatMessagesOutputs,
} from "../../graphql/queries";

import {
  ErrorContainer,
  ErrorMessage,
  ConnectionStatus,
} from "../knowledge_base/document/ChatContainers";

import { userObj } from "../../graphql/cache";
import { IconButton } from "../knowledge_base/document/FilterContainers";
import {
  useChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
  ChatMessageSource,
} from "../annotator/context/ChatSourceAtom";
import {
  ChatMessage,
  ChatMessageProps,
  StreamingThoughtTicker,
  TimelineEntry,
} from "../widgets/chat/ChatMessage";
import {
  buildTimelineEntryFromAsyncThought,
  deriveTimelineEntryType,
} from "../widgets/chat/timelineEntryFactory";
import { getUnifiedAgentWebSocket } from "../chat/get_websockets";
import { useWebSocketAuth } from "../../hooks/useWebSocketAuth";
import type {
  WebSocketSources,
  MessageData,
  ContextStatus,
  CompactionNotice,
} from "../chat/types";

import {
  ChatContainer,
  ContextExhaustedBanner,
  ContextExhaustedButton,
  ConversationIndicator,
  ChatNavigationHeader,
  BackButton,
  NavigationTitle,
  MessagesArea,
  MessageWrapper,
  LatestMessageIndicator,
  ChatInputWrapper,
  EnhancedChatInputContainer,
  EnhancedChatInput,
  EnhancedSendButton,
  InputRow,
} from "./corpus_chat/styles";
import { ApprovalModal, PendingApproval } from "./corpus_chat/ApprovalModal";
import { CorpusConversationListView } from "./corpus_chat/ConversationListView";
import { useChatMentionPicker } from "../../hooks/useChatMentionPicker";
import {
  ChatEmptyState,
  ChatEmptyStateIcon,
  ChatEmptyStateTitle,
  ChatEmptyStateDescription,
  ChatEmptyStateHint,
} from "../knowledge_base/document/ChatContainers";

/**
 * CorpusChat props definition.
 */
interface CorpusChatProps {
  corpusId: string;
  showLoad: boolean;
  setShowLoad: (show: boolean) => void;
  onMessageSelect: (messageId: string) => void;
  initialQuery?: string;
  forceNewChat?: boolean;
  /**
   * Navigate back to the corpus home / search view.
   * Also wired to the conversation list's "Back" button on mobile.
   */
  onNavigateHome?: () => void;
  /**
   * Callback fired when the component transitions between list view and conversation view.
   * Parent components can use this to adjust their navigation headers.
   */
  onViewModeChange?: (isInConversation: boolean) => void;
  /**
   * Callback fired when a source citation is clicked and should navigate to the
   * source document with the text block highlighted. Receives the source's
   * ChatMessageSource so the parent can build a deep link URL.
   *
   * When provided, ALL sources with a `document_id` will route through this
   * callback instead of selecting locally. Only pass this prop in contexts
   * where no document is currently displayed (e.g. corpus-level chat), so
   * that every source is effectively a cross-document navigation.
   */
  onSourceNavigate?: (source: ChatMessageSource) => void;
  /**
   * When true, the conversation-list view's filter-bar Back button is hidden.
   * Use this when the parent already renders an outer navigation header with
   * its own Back affordance — keeping both creates a duplicate-back UX bug.
   */
  hideListBackButton?: boolean;
}

/**
 * CorpusChat component provides:
 * 1) Initial user selection of either creating a new conversation or loading an existing one,
 *    with infinite scrolling for loading conversations in pages.
 * 2) Upon conversation selection, it establishes a websocket connection (using the corpus route)
 *    and renders the chat UI (including message list, chat input, connection status, or errors).
 *
 * It merges the older chat input and websocket logic with a new UI for listing or creating
 * corpus-based conversations, including streaming partial responses.
 */
export const CorpusChat: React.FC<CorpusChatProps> = ({
  corpusId,
  showLoad,
  setShowLoad,
  onMessageSelect,
  initialQuery,
  forceNewChat = false,
  onNavigateHome,
  onViewModeChange,
  onSourceNavigate,
  hideListBackButton = false,
}) => {
  // Chat state
  const [isNewChat, setIsNewChat] = useState(forceNewChat);
  const [newMessage, setNewMessage] = useState("");
  const [chat, setChat] = useState<ChatMessageProps[]>([]);
  const [wsError, setWsError] = useState<string | null>(null);

  // Track whether the assistant is currently generating a response
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  // Track whether the anonymous session context has been exhausted
  const [contextExhausted, setContextExhausted] = useState(false);

  const [selectedConversationId, setSelectedConversationId] = useState<
    string | undefined
  >();

  // For messages from server (via the new GET_CORPUS_CHAT_MESSAGES query)
  const [serverMessages, setServerMessages] = useState<ChatMessageProps[]>([]);

  // handle pinned sources via chatSourcesAtom
  const {
    messages: sourcedMessages,
    selectedMessageId,
    setChatSourceState,
  } = useChatSourceState();

  // GraphQL & user state
  const user_obj = useReactiveVar(userObj);

  const sendingLockRef = useRef<boolean>(false);

  // State for the search filter
  const [titleFilter, setTitleFilter] = useState<string>("");
  const [debouncedTitle, setDebouncedTitle] = useState<string>("");
  const [createdAtGte, setCreatedAtGte] = useState<string>("");
  const [createdAtLte, setCreatedAtLte] = useState<string>("");

  // Context status (token usage, compaction info)
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(
    null
  );
  const [compactionNotice, setCompactionNotice] =
    useState<CompactionNotice | null>(null);

  // Approval gate state (mirrors ChatTray)
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);

  // Mirror pendingApproval in a ref so the WebSocket message handler can read
  // the latest value without including pendingApproval in its dep array
  // (avoiding stale closures in the once-installed onmessage listener).
  const pendingApprovalRef = useRef<PendingApproval | null>(null);
  useEffect(() => {
    pendingApprovalRef.current = pendingApproval;
  }, [pendingApproval]);

  /**
   * Update approval status on a message in both chat and serverMessages arrays.
   * Mirrors the updateMessageApprovalStatus helper in ChatTray / useAgentChat.
   */
  const updateMessageApprovalStatus = useCallback(
    (
      messageId: string,
      status: "awaiting" | "approved" | "rejected",
      opts?: { isComplete?: boolean }
    ): void => {
      const patch: Partial<ChatMessageProps> = { approvalStatus: status };
      if (opts?.isComplete) patch.isComplete = true;

      const mapper = (msg: ChatMessageProps) =>
        msg.messageId === messageId ? { ...msg, ...patch } : msg;
      setChat((prev) => prev.map(mapper));
      setServerMessages((prev) => prev.map(mapper));
    },
    [setChat, setServerMessages]
  );

  // Query for listing CORPUS conversations
  const {
    data,
    loading,
    error,
    fetchMore,
    refetch: refetchConversations,
  } = useQuery<GetCorpusConversationsOutputs, GetCorpusConversationsInputs>(
    GET_CORPUS_CONVERSATIONS,
    {
      variables: {
        corpusId,
        title_Contains: debouncedTitle || undefined,
        createdAt_Gte: createdAtGte || undefined,
        createdAt_Lte: createdAtLte || undefined,
        conversationType: CONVERSATION_TYPE.CHAT,
      },
      fetchPolicy: "network-only",
    }
  );

  // Lazy query for loading messages of a specific conversation
  const [
    fetchChatMessages,
    { data: msgData, loading: loadingMessages, fetchMore: fetchMoreMessages },
  ] = useLazyQuery<GetChatMessagesOutputs, GetChatMessagesInputs>(
    GET_CHAT_MESSAGES
  );

  // messages container ref for scrolling
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Textarea ref + auto-resize so the input starts at one row and grows up to
  // its CSS max-height as the user types, then becomes scrollable. Mirrors the
  // pattern used in ChatTray so document-chat and corpus-chat behave the same.
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const adjustInputHeight = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  useEffect(() => {
    if (!newMessage) {
      const el = inputRef.current;
      if (el) {
        // Reset to the CSS-defined initial height when the input is cleared.
        el.style.height = "";
      }
    }
  }, [newMessage]);

  // Rich-mention agent delegation (docs/architecture/rich_mentions.md):
  // detect `@<fragment>` in the textarea, query agents scoped to this
  // corpus (backend resolver returns global + corpus agents only), then
  // splice a markdown-link mention on select. Shared with ChatTray via
  // the useChatMentionPicker hook.
  const {
    handleValueChange: handleMentionValueChange,
    popoverNode: mentionPopover,
  } = useChatMentionPicker({
    textareaRef: inputRef,
    corpusId,
    onValueChange: setNewMessage,
  });

  /**
   * On server data load, map messages to local ChatMessageProps and store any 'sources' in chatSourcesAtom.
   */
  useEffect(() => {
    if (!msgData?.chatMessages) return;
    const messages = msgData.chatMessages;

    messages.forEach((srvMsg) => {
      const d = (srvMsg as any).data || {};
      const sArr = d.sources as WebSocketSources[] | undefined;
      const tArr = d.timeline as TimelineEntry[] | undefined;
      if (sArr?.length) {
        handleCompleteMessage(
          srvMsg.content,
          sArr,
          srvMsg.id,
          srvMsg.createdAt,
          tArr
        );
      }
    });

    const mapped = messages.map((msg) => {
      const dataField = (msg as any).data || {};
      const sArr = dataField.sources as WebSocketSources[] | undefined;
      const tArr = dataField.timeline as TimelineEntry[] | undefined;
      return {
        messageId: msg.id,
        user: msg.msgType === "HUMAN" ? "You" : "Assistant",
        content: msg.content,
        timestamp: new Date(msg.createdAt).toLocaleString(),
        isAssistant: msg.msgType !== "HUMAN",
        hasSources: !!sArr?.length,
        hasTimeline: !!tArr?.length,
        timeline: tArr || [],
        isComplete: true,
        // Rich-mention agent delegation: forward backend-resolved mention
        // metadata + agent attribution to ChatMessage's MarkdownMessageRenderer.
        mentionedResources: msg.mentionedResources ?? [],
        agentConfiguration: msg.agentConfiguration ?? null,
      } as ChatMessageProps;
    });
    setServerMessages(mapped);
  }, [msgData]);

  // Debounce the title filter input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedTitle(titleFilter);
    }, 500);
    return () => clearTimeout(timer);
  }, [titleFilter]);

  // Combine serverMessages + local chat for final display
  const combinedMessages = [...serverMessages, ...chat];

  // Warm-up ticker visibility: shown only during the gap between the user
  // sending and the first assistant message arriving. Once an in-flight
  // assistant message exists, its inline StreamingThoughtTicker takes over.
  const lastCombinedMessage = combinedMessages[combinedMessages.length - 1];
  const inFlightAssistantPresent =
    !!lastCombinedMessage &&
    !!lastCombinedMessage.isAssistant &&
    lastCombinedMessage.isComplete !== true;
  const showWarmupTicker = isProcessing && !inFlightAssistantPresent;

  // Scroll to bottom helper
  const scrollToBottom = useCallback(() => {
    if (messagesContainerRef.current) {
      const container = messagesContainerRef.current;
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [combinedMessages, scrollToBottom]);

  /**
   * Handle incoming WebSocket messages. Wrapped in useCallback so the
   * useWebSocketAuth onmessage closure stays stable; reads transient
   * approval state via pendingApprovalRef to avoid stale closures.
   *
   * Note: We allow connections without auth_token to support anonymous users on public corpuses.
   * The backend will reject anonymous connections to non-public corpuses with code 4003.
   */
  const handleAgentMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const messageData: MessageData = JSON.parse(event.data);
        if (!messageData) return;
        const { type: msgType, content, data } = messageData;
        const currentApproval = pendingApprovalRef.current;

        switch (msgType) {
          case "ASYNC_START":
            setIsProcessing(true);
            appendStreamingTokenToChat(content, data?.message_id);
            break;
          case "ASYNC_CONTENT":
            appendStreamingTokenToChat(content, data?.message_id);
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
            }
            break;
          case "ASYNC_THOUGHT":
            appendThoughtToMessage(content, data);
            break;
          case "ASYNC_SOURCES":
            mergeSourcesIntoMessage(data?.sources, data?.message_id);
            break;
          case "ASYNC_APPROVAL_NEEDED":
            if (data?.pending_tool_call && data?.message_id) {
              // For sub-agent approvals (ask_document), show the inner
              // tool name/args so the user understands what is being approved.
              const toolCall = { ...data.pending_tool_call };
              if (toolCall.name === "ask_document") {
                const subName = toolCall.arguments?._sub_tool_name;
                if (typeof subName === "string" && subName.length > 0) {
                  toolCall.name = subName;
                  const subArgs = toolCall.arguments?._sub_tool_arguments;
                  toolCall.arguments =
                    subArgs && typeof subArgs === "object"
                      ? (subArgs as Record<string, unknown>)
                      : {};
                }
              }
              setPendingApproval({
                messageId: data.message_id,
                toolCall,
                // Rich-mention agent delegation (Task 14): when the approval
                // originates from a sub-agent invocation, surface its
                // identity in the modal alongside the tool name.
                requestingAgent: data.requesting_agent ?? null,
              });
              setShowApprovalModal(true);

              // Mark the message as awaiting approval
              updateMessageApprovalStatus(data.message_id, "awaiting");
            }
            break;
          case "ASYNC_APPROVAL_RESULT":
            // Informational – the backend echoes the decision back.
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              setShowApprovalModal(false);
              if (data?.decision) {
                updateMessageApprovalStatus(
                  data.message_id,
                  data.decision as "approved" | "rejected",
                  { isComplete: true }
                );
              }
            }
            break;
          case "ASYNC_RESUME":
            // Agent is resuming after approval – keep processing indicator.
            setIsProcessing(true);
            break;
          case "ASYNC_FINISH":
            // Sub-agent persistence failure flag: backend sets
            // ``persistence_failed: true`` on ASYNC_FINISH when the pinned
            // sub-agent ``ChatMessage`` couldn't be written to the DB
            // (rich-mention agent delegation). Surface as a console
            // warning so developers see it; the bubble still renders for
            // this session but will be gone after reload. Follow-up:
            // promote to a non-blocking toast (tracked in PR description).
            if (
              (data as { persistence_failed?: boolean } | undefined)
                ?.persistence_failed
            ) {
              console.warn(
                "[CorpusChat] Sub-agent reply rendered in-memory only — " +
                  "persistence failed; the bubble will be missing after reload.",
                { message_id: data?.message_id }
              );
            }
            finalizeStreamingResponse(
              content,
              data?.sources,
              data?.message_id,
              data?.timeline
            );
            setIsProcessing(false);
            setCompactionNotice(null);
            if (data?.context_status) {
              setContextStatus(data.context_status as ContextStatus);
            }
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
            }
            break;
          case "ASYNC_ERROR":
            if (data?.error_type === WS_ERROR_CONTEXT_EXHAUSTED) {
              setContextExhausted(true);
              setIsProcessing(false);
              break;
            }
            setWsError(data?.error || "Agent error");
            finalizeStreamingResponse(
              data?.error || "Error",
              [],
              data?.message_id
            );
            setIsProcessing(false);
            break;
          case "SYNC_CONTENT": {
            // SYNC_CONTENT is a standalone (non-streaming) assistant reply — unlike the
            // ASYNC path, it must be appended to `chat` directly or it will never render.
            // No setIsProcessing(false) is needed: ASYNC_START is the only setter for
            // isProcessing(true), and SYNC_CONTENT arrives without a preceding ASYNC_START.
            //
            // Capture the message id ONCE so the visible chat entry and the
            // ChatSourceAtom record agree even if the server omits message_id
            // (otherwise each `crypto.randomUUID()` call produces a different
            // value, leaving citations unable to find their parent message).
            const messageId = data?.message_id ?? crypto.randomUUID();
            setChat((prev) => [
              ...prev,
              {
                messageId,
                user: "Assistant",
                content,
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
            handleCompleteMessage(
              content,
              sourcesToPass,
              messageId,
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
    [updateMessageApprovalStatus]
  );

  const wsUrl = getUnifiedAgentWebSocket({
    corpusId,
    conversationId: isNewChat ? undefined : selectedConversationId,
  });
  const wsEnabled = !!(selectedConversationId || isNewChat);

  const {
    isConnected: wsReady,
    send: wsSend,
    reconnect: wsReconnect,
  } = useWebSocketAuth({
    url: wsUrl,
    enabled: wsEnabled,
    onMessage: handleAgentMessage,
    onOpen: () => {
      setWsError(null);
      setContextExhausted(false);
    },
    onAuthInvalid: () =>
      setWsError("Authentication failed. Please log in again."),
  });

  // Track if this is the initial mount - skip forceNewChat effect on mount
  // since isNewChat is already initialized from forceNewChat prop
  const isInitialMountRef = useRef(true);

  // Force new chat mode when forceNewChat prop changes (but not on initial mount)
  useEffect(() => {
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false;
      return;
    }
    if (forceNewChat) {
      startNewChat();
    }
  }, [forceNewChat]);

  // Send the initial query once the WebSocket is ready
  useEffect(() => {
    if (
      initialQuery &&
      initialQuery.trim().length > 0 &&
      wsReady &&
      isNewChat
    ) {
      const timer = setTimeout(() => {
        const trimmed = initialQuery.trim();
        const ok = wsSend(JSON.stringify({ query: trimmed }));
        if (ok) {
          setChat((prev) => [
            ...prev,
            {
              messageId: `user_${Date.now()}_${Math.random()
                .toString(36)
                .substr(2)}`,
              user: user_obj?.email || "You",
              content: trimmed,
              timestamp: new Date().toLocaleString(),
              isAssistant: false,
              isComplete: false,
            },
          ]);
          setNewMessage("");
          setWsError(null);
        }
      }, 500);

      return () => clearTimeout(timer);
    }
  }, [initialQuery, wsReady, isNewChat, user_obj?.email, wsSend]);

  /**
   * Loads existing conversation by ID, clearing local state, then showing chat UI.
   * @param conversationId The ID of the chosen conversation
   */
  const loadConversation = (conversationId: string): void => {
    setSelectedConversationId(conversationId);
    setIsNewChat(false);
    setShowLoad(false);
    setChat([]);
    setServerMessages([]);
    setContextExhausted(false);

    fetchChatMessages({
      variables: {
        conversationId,
        limit: 10,
      },
      fetchPolicy: "network-only",
    });
  };

  /**
   * Start a brand-new chat (unselect existing conversation).
   */
  const startNewChat = useCallback((): void => {
    setContextExhausted(false);
    setContextStatus(null);
    setCompactionNotice(null);
    setIsNewChat(true);
    setSelectedConversationId(undefined);
    setShowLoad(false);
    setChat([]);
    setServerMessages([]);
    // Force WebSocket reconnection even when deps haven't changed
    // (e.g. anonymous user where isNewChat is already true).
    wsReconnect();
  }, [setShowLoad, wsReconnect]);

  /**
   * Infinite scroll trigger for more conversation summary cards.
   */
  const handleFetchMoreConversations = useCallback(() => {
    if (
      !loading &&
      data?.conversations?.pageInfo?.hasNextPage &&
      typeof fetchMore === "function"
    ) {
      fetchMore({
        variables: {
          corpusId,
          limit: 5,
          cursor: data.conversations.pageInfo.endCursor,
        },
      }).catch((err: any) => {
        console.error("Failed to fetch more corpus conversations:", err);
      });
    }
  }, [loading, data, fetchMore, corpusId]);

  /**
   * Send the typed message over the WebSocket to the assistant, and add it locally.
   */
  const sendMessageOverSocket = useCallback((): void => {
    const trimmed = newMessage.trim();
    if (!trimmed || isProcessing) return;
    if (!wsReady) {
      console.warn("WebSocket not ready yet");
      return;
    }

    if (sendingLockRef.current) {
      console.warn("Message is already being sent, ignoring duplicate send.");
      return;
    }

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
          user: user_obj?.email || "You",
          content: trimmed,
          timestamp: new Date().toLocaleString(),
          isAssistant: false,
        },
      ]);
      setNewMessage("");
      setWsError(null);
    } catch (err) {
      console.error("Failed to send message:", err);
      setWsError("Failed to send message. Please try again.");
    } finally {
      setTimeout(() => {
        sendingLockRef.current = false;
      }, 300);
    }
  }, [newMessage, user_obj?.email, wsReady, isProcessing, wsSend]);

  // Conversion of GQL data to a local list
  const conversations = useMemo(() => {
    return data?.conversations?.edges?.map((edge) => edge?.node) || [];
  }, [data]);

  function appendStreamingTokenToChat(
    token: string,
    overrideMessageId?: string
  ): string {
    if (!token) return "";
    let messageId = "";

    setChat((prev) => {
      const lastMessage = prev[prev.length - 1];

      // If we were streaming the assistant's last message, just append
      if (lastMessage && lastMessage.isAssistant) {
        messageId = lastMessage.messageId || "";
        const updatedLast = {
          ...lastMessage,
          content: lastMessage.content + token,
        };
        return [...prev.slice(0, -1), updatedLast];
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
          },
        ];
      }
    });
    return messageId;
  }

  /**
   * Finalize a partially-streamed response by replacing the last chat entry
   * with the final content (and calling handleCompleteMessage to store sources).
   */
  const finalizeStreamingResponse = (
    content: string,
    sourcesData?: WebSocketSources[],
    overrideId?: string,
    timelineData?: TimelineEntry[]
  ) => {
    // First, update the local chat list **without** triggering any other state updates.
    let lastMsgId: string | undefined;
    setChat((prev) => {
      if (!prev.length) return prev;
      const lastIndex = [...prev].reverse().findIndex((msg) => msg.isAssistant);
      if (lastIndex === -1) return prev;

      const forwardIndex = prev.length - 1 - lastIndex;
      const updatedMessages = [...prev];
      const assistantMsg = updatedMessages[forwardIndex];
      lastMsgId = assistantMsg.messageId;

      updatedMessages[forwardIndex] = {
        ...assistantMsg,
        content,
        isComplete: true,
        hasSources:
          assistantMsg.hasSources ??
          (sourcesData ? sourcesData.length > 0 : false),
        hasTimeline:
          assistantMsg.hasTimeline ??
          (timelineData ? timelineData.length > 0 : false),
        timeline: timelineData || assistantMsg.timeline || [],
      };

      return updatedMessages;
    });

    // 🔑 Now that the chat list state is updated, handle sources & timeline in a **separate** state update
    // to avoid React's "setState inside render" warning.
    if (lastMsgId) {
      handleCompleteMessage(
        content,
        sourcesData,
        lastMsgId,
        overrideId,
        timelineData
      );
    }
  };

  /**
   * Store final content + sources in ChatSourceAtom using a consistent messageId
   */
  const handleCompleteMessage = (
    content: string,
    sourcesData?: Array<WebSocketSources>,
    overrideId?: string,
    overrideCreatedAt?: string,
    timelineData?: TimelineEntry[]
  ): void => {
    if (!overrideId) {
      console.warn(
        "handleCompleteMessage called without an overrideId - sources may not display correctly"
      );
    }
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
          timeline: timelineData || existingMsg.timeline,
        };
        const updatedMessages = [...prev.messages];
        updatedMessages[existingIndex] = updatedMsg;
        return {
          ...prev,
          messages: updatedMessages,
        };
      } else {
        return {
          ...prev,
          messages: [
            ...prev.messages,
            {
              messageId,
              content,
              timestamp: messageTimestamp,
              sources: mappedSources,
              timeline: timelineData || [],
            },
          ],
          selectedMessageId: overrideId ? prev.selectedMessageId : messageId,
        };
      }
    });
  };

  /**
   * Append agent thought/tool call details to message timeline while streaming.
   */
  const appendThoughtToMessage = (
    thoughtText: string,
    data: MessageData["data"] | undefined
  ): void => {
    const messageId = data?.message_id;
    if (!messageId || !thoughtText) return;

    const entryType = deriveTimelineEntryType(data);
    if (entryType === "compaction" && data?.compaction) {
      // Same dual-side-effect as ChatTray: timeline row + standalone
      // compaction-notice banner.
      setCompactionNotice({
        tokensBefore: data.compaction.tokens_before,
        tokensAfter: data.compaction.tokens_after,
        contextWindow: data.compaction.context_window,
      });
    }
    const newEntry = buildTimelineEntryFromAsyncThought(
      thoughtText,
      data,
      entryType
    );

    setChat((prev) => {
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
          } as any,
        ];
      }

      const msg = prev[idx] as any;
      const timeline = msg.timeline ? [...msg.timeline, newEntry] : [newEntry];
      const updated = { ...msg, hasTimeline: true, timeline };
      return [...prev.slice(0, idx), updated, ...prev.slice(idx + 1)];
    });
  };

  /**
   * Merge additional sources into existing message while streaming.
   */
  const mergeSourcesIntoMessage = (
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
              isComplete: false,
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

    setChat((prev) => {
      const idx = prev.findIndex((m) => m.messageId === overrideId);
      if (idx === -1) return prev;
      const msg = prev[idx] as any;
      return [
        ...prev.slice(0, idx),
        { ...msg, hasSources: true },
        ...prev.slice(idx + 1),
      ];
    });
  };

  /**
   * Determine current "view" to simplify back button logic
   */
  const isConversation = isNewChat || !!selectedConversationId;

  // Notify parent when view mode changes (conversation vs list)
  useEffect(() => {
    onViewModeChange?.(isConversation);
  }, [isConversation, onViewModeChange]);

  /**
   * Send approval decision back to the WebSocket.
   */
  const sendApprovalDecision = useCallback(
    (approved: boolean): void => {
      if (!pendingApproval || !wsReady) {
        console.warn("Cannot send approval decision - missing requirements");
        return;
      }

      try {
        const messageData = {
          approval_decision: approved,
          llm_message_id: parseInt(pendingApproval.messageId),
        };

        console.log(
          `[CorpusChat] Sending approval decision: ${
            approved ? "APPROVED" : "REJECTED"
          } for message ${pendingApproval.messageId}`
        );

        const ok = wsSend(JSON.stringify(messageData));
        if (!ok) {
          setWsError("Failed to send approval decision. Please try again.");
          setShowApprovalModal(true);
          return;
        }

        // Hide the modal immediately after sending the decision (optimistic UI)
        setShowApprovalModal(false);

        // Clear after decision will be handled when continuation arrives
        setWsError(null);
      } catch (err) {
        console.error("Failed to send approval decision:", err);
        setWsError("Failed to send approval decision. Please try again.");
        // Re-show modal on error so user can try again
        setShowApprovalModal(true);
      }
    },
    [pendingApproval, wsReady, wsSend]
  );

  // If the GraphQL query fails entirely:
  if (error) {
    return (
      <ChatContainer id="corpus-chat-container">
        {onNavigateHome && (
          <ChatNavigationHeader>
            <BackButton
              aria-label="Return to dashboard"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onNavigateHome();
              }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              style={{ cursor: "pointer" }}
            >
              <ArrowLeft size={20} />
            </BackButton>
            <NavigationTitle>Chat unavailable</NavigationTitle>
            <IconButton
              onClick={(e: React.MouseEvent) => {
                e.preventDefault();
                e.stopPropagation();
                onNavigateHome();
              }}
              title="Return to Dashboard"
              whileTap={{ scale: 0.95 }}
              style={{ cursor: "pointer" }}
            >
              <Home size={20} />
            </IconButton>
          </ChatNavigationHeader>
        )}
        <ErrorContainer initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <AlertCircle size={24} />
          Failed to load corpus conversations
        </ErrorContainer>
      </ChatContainer>
    );
  }

  return (
    <ChatContainer id="corpus-chat-container">
      <ConversationIndicator id="conversation-indicator">
        {/* Navigation header for conversation view
            Shows on both mobile and desktop when viewing a conversation */}
        {isConversation && (
          <ChatNavigationHeader>
            <BackButton
              aria-label="Back to conversation list"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                // Back button in conversation view always goes to the chat list
                // (The Home button is for going directly to corpus home)
                setSelectedConversationId(undefined);
                setIsNewChat(false);
                setChat([]);
                setServerMessages([]);
              }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              style={{ cursor: "pointer" }}
            >
              <ArrowLeft size={20} />
            </BackButton>
            <NavigationTitle>
              {selectedConversationId ? "Conversation" : "New Chat"}
            </NavigationTitle>
            <IconButton
              onClick={(e: React.MouseEvent) => {
                e.preventDefault();
                e.stopPropagation();
                console.log("Home button clicked");
                if (onNavigateHome) {
                  onNavigateHome();
                }
              }}
              title="Return to Dashboard"
              whileTap={{ scale: 0.95 }}
              style={{ cursor: "pointer" }}
            >
              <Home size={20} />
            </IconButton>
          </ChatNavigationHeader>
        )}

        <AnimatePresence>
          {isConversation ? (
            // CONVERSATION VIEW
            <motion.div
              id="corpus-chat-conversation-view"
              key="conversation"
              style={{
                display: "flex",
                flexDirection: "column",
                width: "100%",
                position: "relative",
                overflow: "hidden",
                minHeight: 0,
                flex: 1,
                height: "100%",
                maxHeight: "100%",
              }}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              {/* Scrollable Messages */}
              <MessagesArea
                className="chat-messages-area"
                ref={messagesContainerRef}
                $isProcessing={isProcessing}
              >
                {combinedMessages.length === 0 &&
                  !showWarmupTicker &&
                  !isProcessing && (
                    <ChatEmptyState data-testid="chat-empty-state">
                      <ChatEmptyStateIcon>
                        <MessageCircle />
                      </ChatEmptyStateIcon>
                      <ChatEmptyStateTitle>
                        Ask me about this corpus
                      </ChatEmptyStateTitle>
                      <ChatEmptyStateDescription>
                        I can search across all documents and answer questions.
                      </ChatEmptyStateDescription>
                      <ChatEmptyStateHint>
                        <AtSign size={14} />
                        Try @-mentioning a specific agent for deeper analysis.
                      </ChatEmptyStateHint>
                    </ChatEmptyState>
                  )}
                {combinedMessages.map((msg, idx) => {
                  const sourcedMessage = sourcedMessages.find(
                    (m) => m.messageId === msg.messageId
                  );

                  const sources =
                    sourcedMessage?.sources.map((source, index) => ({
                      text: source.rawText || `Source ${index + 1}`,
                      onClick: () => {
                        // Cross-document source: navigate away instead of
                        // selecting locally (avoids a flash of local selection
                        // state before the navigation replaces the view).
                        // onMessageSelect is intentionally skipped — navigation
                        // replaces the entire view, so local selection state
                        // and message callbacks are irrelevant.
                        if (source.document_id && onSourceNavigate) {
                          onSourceNavigate(source);
                          return;
                        }
                        if (!source.document_id) {
                          console.warn(
                            "[CorpusChat] Source has no document_id; cannot deep-link. The backend should populate it for corpus-chat sources via SourceNode.metadata.document_id."
                          );
                        } else if (!onSourceNavigate) {
                          console.warn(
                            "[CorpusChat] onSourceNavigate not provided by parent; cross-document deep-link disabled in this mount path."
                          );
                        }

                        // Same-document source: select locally
                        setChatSourceState((prev) => ({
                          ...prev,
                          selectedMessageId: sourcedMessage.messageId,
                          selectedSourceIndex: index,
                        }));
                        if (sourcedMessage.sources.length > 0) {
                          onMessageSelect?.(sourcedMessage.messageId);
                        }
                      },
                    })) || [];

                  const isLatestMessage = idx === combinedMessages.length - 1;

                  return (
                    <MessageWrapper
                      key={msg.messageId || idx}
                      isLatest={isLatestMessage && msg.isAssistant}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3, delay: idx * 0.05 }}
                    >
                      {isLatestMessage && msg.isAssistant && (
                        <LatestMessageIndicator
                          initial={{ scaleY: 0 }}
                          animate={{ scaleY: 1 }}
                          transition={{ duration: 0.3 }}
                        />
                      )}
                      <ChatMessage
                        {...msg}
                        hasSources={!!sourcedMessage?.sources.length}
                        hasTimeline={msg.hasTimeline}
                        timeline={msg.timeline}
                        sources={sources}
                        isSelected={
                          sourcedMessage?.messageId === selectedMessageId
                        }
                        onSelect={() => {
                          if (sourcedMessage) {
                            setChatSourceState((prev) => ({
                              ...prev,
                              selectedMessageId:
                                prev.selectedMessageId ===
                                sourcedMessage.messageId
                                  ? null
                                  : sourcedMessage.messageId,
                              selectedSourceIndex: null,
                            }));
                            if (sourcedMessage.sources.length > 0) {
                              onMessageSelect?.(sourcedMessage.messageId);
                            }
                          }
                        }}
                      />
                    </MessageWrapper>
                  );
                })}

                {/* In-flight signal lives inline on the streaming assistant
                    message via StreamingThoughtTicker — the old standalone
                    "AI Assistant is thinking..." pill was removed in favor of
                    the per-message animated ticker icon + breathing dot.

                    The pre-message warm-up beat (after the user sends, before
                    the assistant's message exists in `chat`) is bridged by a
                    standalone ticker so the user always has a visible cue. */}
                {showWarmupTicker && (
                  <MessageWrapper
                    data-testid="streaming-warmup-ticker-wrapper"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2 }}
                    style={{ paddingLeft: "1rem" }}
                  >
                    <StreamingThoughtTicker timeline={[]} />
                  </MessageWrapper>
                )}
              </MessagesArea>

              {/* Compaction banner (visible while compaction is underway) */}
              {compactionNotice && (
                <div
                  data-testid="compaction-banner"
                  style={{
                    padding: "0.5rem 1rem",
                    borderTop: `1px solid ${OS_LEGAL_COLORS.blueBorder}`,
                    background: `linear-gradient(135deg, ${OS_LEGAL_COLORS.blueSurface} 0%, #dbeafe 100%)`,
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.8125rem",
                    color: OS_LEGAL_COLORS.blueDark,
                    flexShrink: 0,
                    animation: "compaction-pulse 2s ease-in-out infinite",
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke={OS_LEGAL_COLORS.primaryBlueHover}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="4 14 10 14 10 20" />
                    <polyline points="20 10 14 10 14 4" />
                    <line x1="14" y1="10" x2="21" y2="3" />
                    <line x1="3" y1="21" x2="10" y2="14" />
                  </svg>
                  <span style={{ fontWeight: 600 }}>Compacting context</span>
                  <span style={{ opacity: 0.75 }}>
                    {compactionNotice.tokensBefore.toLocaleString()} →{" "}
                    {compactionNotice.tokensAfter.toLocaleString()} tokens
                  </span>
                  <style>{`
                    @keyframes compaction-pulse {
                      0%, 100% { opacity: 1; }
                      50% { opacity: 0.7; }
                    }
                  `}</style>
                </div>
              )}
              {/* Context usage meter */}
              {contextStatus && contextStatus.context_window > 0 && (
                <div
                  data-testid="context-meter"
                  style={{
                    padding: "0.375rem 1.5rem 0.625rem",
                    borderTop: "1px solid rgba(0, 0, 0, 0.06)",
                    background: "rgba(255, 255, 255, 0.95)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.75rem",
                    color: OS_LEGAL_COLORS.textSecondary,
                    flexShrink: 0,
                  }}
                >
                  <div
                    data-testid="context-meter-track"
                    style={{
                      flex: 1,
                      height: 4,
                      borderRadius: 2,
                      background: OS_LEGAL_COLORS.border,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      data-testid="context-meter-fill"
                      style={{
                        height: "100%",
                        borderRadius: 2,
                        width: `${Math.min(
                          100,
                          (contextStatus.used_tokens /
                            contextStatus.context_window) *
                            100
                        )}%`,
                        background:
                          contextStatus.used_tokens /
                            contextStatus.context_window >
                          0.85
                            ? OS_LEGAL_COLORS.danger
                            : contextStatus.used_tokens /
                                contextStatus.context_window >
                              0.6
                            ? OS_LEGAL_COLORS.folderIcon
                            : OS_LEGAL_COLORS.green,
                        transition: "width 0.3s ease, background 0.3s ease",
                      }}
                    />
                  </div>
                  <span
                    data-testid="context-meter-percentage"
                    title={`~${contextStatus.used_tokens.toLocaleString()} / ${contextStatus.context_window.toLocaleString()} tokens used`}
                  >
                    {Math.round(
                      (contextStatus.used_tokens /
                        contextStatus.context_window) *
                        100
                    )}
                    %
                  </span>
                  {contextStatus.was_compacted && (
                    <span
                      data-testid="context-meter-compacted"
                      style={{
                        background: OS_LEGAL_COLORS.blueBorder,
                        color: OS_LEGAL_COLORS.primaryBlueHover,
                        padding: "0.125rem 0.375rem",
                        borderRadius: 4,
                        fontSize: "0.6875rem",
                        fontWeight: 500,
                      }}
                    >
                      Compacted
                    </span>
                  )}
                </div>
              )}
              {/* Context exhausted banner */}
              {contextExhausted && (
                <ContextExhaustedBanner>
                  <span>This conversation has reached its context limit.</span>
                  <ContextExhaustedButton onClick={startNewChat}>
                    Start New Chat
                  </ContextExhaustedButton>
                </ContextExhaustedBanner>
              )}
              {/* Input */}
              <ChatInputWrapper>
                <EnhancedChatInputContainer
                  $isTyping={isNewChat}
                  $disabled={isProcessing}
                >
                  <AnimatePresence>
                    {wsError ? (
                      <ErrorMessage key="error">
                        <motion.div
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.9 }}
                          transition={{ type: "spring", damping: 20 }}
                        >
                          {wsError}
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => window.location.reload()}
                            style={{
                              marginLeft: "0.75rem",
                            }}
                          >
                            Reconnect
                          </Button>
                        </motion.div>
                      </ErrorMessage>
                    ) : (
                      !wsReady && (
                        <ConnectionStatus
                          key="status"
                          connected={wsReady}
                          initial={{ opacity: 0, y: -10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -10 }}
                          transition={{ duration: 0.3 }}
                        />
                      )
                    )}
                  </AnimatePresence>
                  {mentionPopover}
                  <InputRow>
                    <EnhancedChatInput
                      ref={inputRef}
                      rows={1}
                      value={newMessage}
                      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                        const value = e.target.value;
                        setNewMessage(value);
                        const caret = e.target.selectionStart ?? value.length;
                        handleMentionValueChange(value, caret);
                        // Defer measurement until after React commits the new
                        // value so scrollHeight reflects the typed content.
                        setTimeout(adjustInputHeight, 0);
                      }}
                      placeholder={
                        wsReady
                          ? isProcessing
                            ? "Assistant is thinking..."
                            : "Type your corpus query..."
                          : "Waiting for connection..."
                      }
                      disabled={!wsReady || isProcessing || contextExhausted}
                      onKeyDown={(
                        e: React.KeyboardEvent<HTMLTextAreaElement>
                      ) => {
                        // Shift+Enter inserts a newline; bare Enter sends the
                        // message — matches ChatTray and the user's expectation
                        // for a multi-line auto-growing input.
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          sendMessageOverSocket();
                        }
                      }}
                    />
                    <EnhancedSendButton
                      $hasText={!!newMessage.trim()}
                      disabled={
                        !wsReady ||
                        !newMessage.trim() ||
                        isProcessing ||
                        contextExhausted
                      }
                      onClick={sendMessageOverSocket}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      animate={
                        wsReady &&
                        !!newMessage.trim() &&
                        !isProcessing &&
                        !contextExhausted
                          ? { y: [0, -2, 0] }
                          : {}
                      }
                      transition={{ duration: 0.2 }}
                    >
                      <Send size={20} />
                    </EnhancedSendButton>
                  </InputRow>
                </EnhancedChatInputContainer>
              </ChatInputWrapper>
            </motion.div>
          ) : (
            // CONVERSATION MENU VIEW
            <CorpusConversationListView
              conversations={conversations}
              onLoadConversation={loadConversation}
              onStartNewChat={startNewChat}
              onFetchMore={handleFetchMoreConversations}
              titleFilter={titleFilter}
              onTitleFilterChange={setTitleFilter}
              createdAtGte={createdAtGte}
              onCreatedAtGteChange={setCreatedAtGte}
              createdAtLte={createdAtLte}
              onCreatedAtLteChange={setCreatedAtLte}
              onBack={hideListBackButton ? undefined : onNavigateHome}
            />
          )}
        </AnimatePresence>
      </ConversationIndicator>

      {/* Approval Overlay */}
      <ApprovalModal
        pendingApproval={pendingApproval}
        show={showApprovalModal}
        onHide={() => setShowApprovalModal(false)}
        onDecision={sendApprovalDecision}
      />
    </ChatContainer>
  );
};
