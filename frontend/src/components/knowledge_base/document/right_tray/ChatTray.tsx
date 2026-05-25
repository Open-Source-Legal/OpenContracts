/**
 * ChatTray Component - Vertical Alignment For Sidebar
 *
 * Thin composer that wires the chat WebSocket + ChatSourceAtom state to the
 * three sibling hooks (`useChatStreamHandlers`, `useChatAgentMessageHandler`,
 * `useChatSendHandlers`) and renders the chat UI.
 *
 * Behavior:
 *   1) Load existing conversation data from GraphQL (GET_CONVERSATIONS).
 *   2) If authenticated, open a WebSocket to stream new messages with partial
 *      updates (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH) or synchronous
 *      messages (SYNC_CONTENT).
 *   3) Display those messages in real time, appending them to the chat.
 *   4) Allow sending user queries through the socket.
 */

import {
  ChatContainer,
  ConversationIndicator,
  ErrorContainer,
} from "../ChatContainers";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowLeft,
  AtSign,
  MessageCircle,
  Send,
} from "lucide-react";
import { Button } from "@os-legal/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatMessage,
  ChatMessageProps,
  StreamingThoughtTicker,
} from "../../../widgets/chat/ChatMessage";
import { useLazyQuery, useQuery, useReactiveVar } from "@apollo/client";
import {
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
  GET_CHAT_MESSAGES,
  GetChatMessagesOutputs,
  GetChatMessagesInputs,
} from "../../../../graphql/queries";
import { userObj } from "../../../../graphql/cache";
import { getWebSocketUrl } from "../utils";
import { useWebSocketAuth } from "../../../../hooks/useWebSocketAuth";
import {
  ChatInputContainer,
  ChatInput,
  SendButton,
  ErrorMessage,
  ConnectionStatus,
  ChatInputWrapper,
  CharacterCount,
  ChatEmptyState,
  ChatEmptyStateIcon,
  ChatEmptyStateTitle,
  ChatEmptyStateDescription,
  ChatEmptyStateHint,
} from "../ChatContainers";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { useChatSourceState } from "../../../annotator/context/ChatSourceAtom";
import { TimelineEntry } from "../../../widgets/chat/ChatMessage";
import {
  buildTimelineEntryFromAsyncThought,
  deriveTimelineEntryType,
} from "../../../widgets/chat/timelineEntryFactory";
import { useUISettings } from "../../../annotator/hooks/useUISettings";
import { useLocation, useNavigate } from "react-router-dom";
import { updateAnnotationSelectionParams } from "../../../../utils/navigationUtils";
import { toGlobalId } from "../../../../utils/idValidation";
import type {
  WebSocketSources,
  MessageData,
  ContextStatus,
  CompactionNotice,
} from "../../../chat/types";
import { ApprovalDialog } from "../../../chat/ApprovalDialog";
import { ReopenApprovalButton } from "./ApprovalOverlay";
import type { PendingApproval } from "../../../chat/types";
import { DocumentConversationListView } from "./ConversationListView";
import { adjustTextareaHeight } from "./chatUtils";
import { useChatStreamHandlers } from "./useChatStreamHandlers";
import { useChatAgentMessageHandler } from "./useChatAgentMessageHandler";
import { useChatSendHandlers } from "./useChatSendHandlers";
import { useChatMentionPicker } from "../../../../hooks/useChatMentionPicker";

export type { WebSocketSources, MessageData } from "../../../chat/types";

/**
 * ChatTray props definition.
 */
interface ChatTrayProps {
  documentId: string;
  onMessageSelect?: () => void;
  corpusId?: string;
  /**
   * Optional initial message to send immediately once the WebSocket is ready.
   * Used when the user submits a chat query via the floating input.
   */
  initialMessage?: string;
  /**
   * When true, hides conversation history and starts a fresh conversation each time.
   */
  readOnly?: boolean;
  /**
   * When true, ChatTray initializes in new-chat mode instead of showing the
   * conversation list — used on mobile so submitting from the ask bar launches
   * a fresh conversation directly with the typed message.
   */
  autoStartNewChat?: boolean;
}

/**
 * ChatTray component provides:
 * 1) Initial user selection of either creating a new conversation or loading an existing one,
 * with infinite scrolling for loading conversations in pages.
 * 2) Upon conversation selection, it establishes a websocket connection and renders the chat UI
 *    (including message list, chat input, connection status, or error messages).
 *
 * It merges older chat input and websocket communication code with newer UI logic
 * for listing or creating conversations, including streaming partial responses.
 */
export const ChatTray: React.FC<ChatTrayProps> = ({
  documentId,
  onMessageSelect,
  corpusId,
  initialMessage,
  readOnly = false,
  autoStartNewChat = false,
}) => {
  // Routing hooks for URL-driven annotation selection
  const location = useLocation();
  const navigate = useNavigate();

  // User / Auth state – must be declared before any state that depends on it
  const user_obj = useReactiveVar(userObj);

  // Chat state
  // Start with new chat if readOnly OR if user is anonymous OR if the caller
  // asked us to skip the conversation list (e.g. mobile ask bar submit).
  const [isNewChat, setIsNewChat] = useState<boolean>(
    readOnly || !user_obj || autoStartNewChat
  );
  const [newMessage, setNewMessage] = useState("");
  const [chat, setChat] = useState<ChatMessageProps[]>([]);
  const [wsError, setWsError] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | undefined
  >();

  // Context status (token usage, compaction info)
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(
    null
  );
  const [compactionNotice, setCompactionNotice] =
    useState<CompactionNotice | null>(null);

  // Approval state
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);

  // Controls visibility of the approval modal (can be dismissed & reopened)
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);

  const {
    messages: sourcedMessages,
    selectedMessageId,
    setChatSourceState,
  } = useChatSourceState();

  // For messages from server (via the new GET_CHAT_MESSAGES query)
  const [serverMessages, setServerMessages] = useState<ChatMessageProps[]>([]);

  // Mirror pendingApproval in a ref so the WebSocket onmessage closure (which
  // is captured once at effect-mount time inside useWebSocketAuth) can read
  // the latest value without retriggering the connection effect.
  const pendingApprovalRef = useRef<PendingApproval | null>(null);
  useEffect(() => {
    pendingApprovalRef.current = pendingApproval;
  }, [pendingApproval]);

  const sendingLockRef = useRef<boolean>(false);

  // State for the search filter
  const [titleFilter, setTitleFilter] = useState<string>("");
  const [debouncedTitle, setDebouncedTitle] = useState<string>("");
  const [createdAtGte, setCreatedAtGte] = useState<string>("");
  const [createdAtLte, setCreatedAtLte] = useState<string>("");

  // For dynamic display of filters
  const [showSearch, setShowSearch] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const searchInputRef = useRef<HTMLElement>(null);
  const datePickerRef = useRef<HTMLElement>(null);

  const { data, loading, error, fetchMore, refetch } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables: {
      documentId,
      title_Contains: debouncedTitle || undefined,
      createdAt_Gte: createdAtGte || undefined,
      createdAt_Lte: createdAtLte || undefined,
    },
    fetchPolicy: "network-only",
    skip: !user_obj, // Skip loading conversations for anonymous users
  });

  // Lazy query for loading messages of a specific conversation
  const [fetchChatMessages, { data: msgData }] = useLazyQuery<
    GetChatMessagesOutputs,
    GetChatMessagesInputs
  >(GET_CHAT_MESSAGES);

  const { chatTrayState, setChatTrayState } = useUISettings();

  // showLoad lives on chatTrayStateAtom (lifted out of DocumentKnowledgeBase
  // to break the cross-component setState chain that triggered React's
  // "Cannot update a component while rendering a different component"
  // warning when ChatTray's mount effect called the parent setter prop).
  // The local `setShowLoad` shape preserves the previous call sites.
  const setShowLoad = useCallback(
    (value: boolean) => {
      setChatTrayState((prev) => ({ ...prev, showLoad: value }));
    },
    [setChatTrayState]
  );

  // Ref to manage auto-scrolling behaviour
  const autoScrollRef = useRef(true);

  // Flag so we only run initial scroll restore once
  const initialRestoreDone = useRef(false);

  // State for auto-resizing textarea
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const MAX_MESSAGE_LENGTH = 4000;

  // Ref to the scrollable messages container — declared early so the stream
  // handlers hook can attach inline auto-scroll on token append.
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  /* --------------------------------------------------------------------- */
  /* Stream / agent / send handler hooks                                   */
  /* --------------------------------------------------------------------- */

  const streamHandlers = useChatStreamHandlers({
    setChat,
    setServerMessages,
    setChatSourceState,
    setCompactionNotice,
    setPendingApproval,
    messagesContainerRef,
  });
  const { updateMessageApprovalStatus, handleCompleteMessage } = streamHandlers;

  // Auto-resize callback — wraps the pure DOM helper from chatUtils.
  const adjustTextareaHeightCb = useCallback(() => {
    adjustTextareaHeight(textareaRef.current);
  }, []);

  // Reset textarea height when message is cleared
  useEffect(() => {
    if (!newMessage) {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.style.height = "44px"; // Reset to initial height
      }
    }
  }, [newMessage]);

  // Initial textarea setup
  useEffect(() => {
    adjustTextareaHeightCb();
  }, [adjustTextareaHeightCb]);

  // Rich-mention agent delegation (docs/architecture/rich_mentions.md):
  // detect `@<fragment>` in the textarea, query agents visible in this
  // document/corpus scope, and splice a markdown-link mention on select.
  // The backend's `search_agents_for_mention` resolver already enforces
  // scope (global + the provided corpus only when corpusId is passed), so
  // we just forward corpusId here. Shared with CorpusChat via the
  // useChatMentionPicker hook.
  const {
    handleValueChange: handleMentionValueChange,
    popoverNode: mentionPopover,
  } = useChatMentionPicker({
    textareaRef,
    corpusId,
    onValueChange: setNewMessage,
  });

  /**
   * On server data load, we map messages to local ChatMessageProps and
   * also store any 'sources' in the chatSourcesAtom (so pins and selection work).
   */
  useEffect(() => {
    if (!msgData?.chatMessages) {
      return;
    }
    const messages = msgData.chatMessages;

    // First, register them in our chatSourcesAtom if they have sources.
    // `srvMsgData.timeline` is intentionally not forwarded — ChatSourceAtom
    // does not persist timelines, and the live chat array carries them via
    // the mapped `timeline` field on the assistant message below.
    messages.forEach((srvMsg) => {
      const srvMsgData = srvMsg.data as
        | {
            sources?: WebSocketSources[];
            timeline?: TimelineEntry[];
            message_id?: string;
          }
        | undefined;
      if (srvMsgData?.sources?.length) {
        handleCompleteMessage(
          srvMsg.content,
          srvMsgData.sources,
          srvMsg.id,
          srvMsg.createdAt
        );
      }
    });

    // Then, map them for immediate display - NOW INCLUDING hasSources and hasTimeline FLAGS
    const mapped = messages.map((msg) => {
      // Type assertion for data field to include timeline and approval status
      const msgData = msg.data as
        | {
            sources?: WebSocketSources[];
            timeline?: TimelineEntry[];
            message_id?: string;
            approval_decision?: string;
            state?: string;
            pending_tool_call?: {
              name: string;
              arguments: any;
              tool_call_id?: string;
            };
            // Single source of truth: ``PendingApproval.requestingAgent``
            // (see ``components/chat/types.ts``). Keeps this persisted-message
            // cast in lock-step with the live WebSocket frame shape so a
            // future field addition on the canonical type flows through here.
            requesting_agent?: PendingApproval["requestingAgent"];
          }
        | undefined;

      // Determine lifecycle + approval status from *persisted* state field first
      const lifecycleState =
        ((msg as any).state as string | undefined) || msgData?.state;

      let approvalStatus: "approved" | "rejected" | "awaiting" | undefined;
      if (msgData?.approval_decision === "approved") {
        approvalStatus = "approved";
      } else if (msgData?.approval_decision === "rejected") {
        approvalStatus = "rejected";
      } else if (lifecycleState === "awaiting_approval") {
        approvalStatus = "awaiting";
      }

      const isCompleteFlag =
        lifecycleState !== "in_progress" &&
        lifecycleState !== "awaiting_approval";

      const mappedMsg = {
        messageId: msg.id,
        user: msg.msgType === "HUMAN" ? "You" : "Assistant",
        content: msg.content,
        timestamp: new Date(msg.createdAt).toLocaleString(),
        isAssistant: msg.msgType !== "HUMAN",
        hasSources: !!msgData?.sources?.length,
        hasTimeline: !!msgData?.timeline?.length,
        timeline: msgData?.timeline || [],
        approvalStatus,
        isComplete: isCompleteFlag,
        // Rich-mention agent delegation: hand backend-resolved mention
        // metadata + agent attribution down to ChatMessage so its
        // MarkdownMessageRenderer can render styled chips with tooltips.
        mentionedResources: msg.mentionedResources ?? [],
        agentConfiguration: msg.agentConfiguration ?? null,
      } as any;

      // If this message is awaiting approval and we haven't already set
      // pendingApproval, prime the overlay so users can act immediately.
      // Only set it if the message is truly still awaiting (not already processed)
      if (
        approvalStatus === "awaiting" &&
        msgData?.pending_tool_call &&
        !pendingApproval &&
        !msgData?.approval_decision // Don't show modal if already has a decision
      ) {
        setPendingApproval({
          messageId: msg.id.toString(),
          toolCall: msgData.pending_tool_call,
          requestingAgent: msgData.requesting_agent ?? null,
        });
        setShowApprovalModal(true);
      }

      return mappedMsg;
    });
    setServerMessages(mapped);
  }, [msgData]);

  // Add this effect to handle clicks outside the expanded elements
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        searchInputRef.current &&
        !searchInputRef.current.contains(event.target as Node)
      ) {
        setShowSearch(false);
      }
      if (
        datePickerRef.current &&
        !datePickerRef.current.contains(event.target as Node)
      ) {
        setShowDatePicker(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /**
   * Memoized list of conversation nodes from the GraphQL response.
   */
  const conversations = useMemo(() => {
    return data?.conversations?.edges?.map((edge) => edge?.node) || [];
  }, [data]);

  /**
   * Combine serverMessages + local chat for final display
   */
  const combinedMessages = useMemo(() => {
    const messages = [...serverMessages, ...chat];

    // Remove duplicates by messageId, preferring the most recent version
    const messageMap = new Map<string, ChatMessageProps>();
    const messagesWithoutId: ChatMessageProps[] = [];

    messages.forEach((msg) => {
      if (msg.messageId) {
        messageMap.set(msg.messageId, msg);
      } else {
        // Keep messages without IDs (shouldn't happen with our fix, but just in case)
        messagesWithoutId.push(msg);
      }
    });

    // If there's a pending approval, ensure the message shows awaiting status
    if (pendingApproval) {
      const existingMessage = messageMap.get(pendingApproval.messageId);
      if (existingMessage) {
        // Update existing message to show awaiting status if not already set
        if (
          !existingMessage.approvalStatus ||
          existingMessage.approvalStatus === "awaiting"
        ) {
          messageMap.set(pendingApproval.messageId, {
            ...existingMessage,
            approvalStatus: "awaiting",
          });
        }
      } else {
        // Create a placeholder message with the same ID
        const approvalMessage = {
          messageId: pendingApproval.messageId,
          user: "Assistant",
          content: `Tool execution paused: ${pendingApproval.toolCall.name}`,
          timestamp: new Date().toLocaleString(),
          isAssistant: true,
          hasTimeline: false,
          timeline: [],
          approvalStatus: "awaiting" as const,
          isComplete: false,
        };
        messageMap.set(pendingApproval.messageId, approvalMessage);
      }
    }

    // Combine all messages and sort by timestamp to maintain chronological order
    const allMessages = [
      ...messagesWithoutId,
      ...Array.from(messageMap.values()),
    ];
    return allMessages.sort((a, b) => {
      const timeA = new Date(a.timestamp).getTime();
      const timeB = new Date(b.timestamp).getTime();
      return timeA - timeB;
    });
  }, [serverMessages, chat, pendingApproval]);

  // Check if assistant is currently responding (streaming)
  const isAssistantResponding = useMemo(() => {
    const lastMessage = combinedMessages[combinedMessages.length - 1];
    return lastMessage?.isAssistant && !lastMessage?.isComplete;
  }, [combinedMessages]);

  // Add scroll helper function
  const scrollToBottom = useCallback(() => {
    if (messagesContainerRef.current) {
      const container = messagesContainerRef.current;
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, []);

  // Scroll when messages change
  useEffect(() => {
    if (autoScrollRef.current) {
      scrollToBottom();
    }
  }, [combinedMessages, scrollToBottom]);

  // Restore persisted conversation + scroll
  useEffect(() => {
    if (chatTrayState.conversationId) {
      // open the cached conversation and immediately refresh first page
      loadConversation(chatTrayState.conversationId);
      setShowLoad(false);
      // explicit refresh to ensure new messages are fetched even if cached
      fetchChatMessages({
        variables: {
          conversationId: chatTrayState.conversationId,
          limit: 10,
        },
        fetchPolicy: "network-only",
      });
    } else if (chatTrayState.isNewChat) {
      startNewChat();
    }
  }, []);

  // Once messages arrive, restore the scroll offset exactly once
  useEffect(() => {
    if (
      !initialRestoreDone.current &&
      chatTrayState.conversationId &&
      selectedConversationId === chatTrayState.conversationId &&
      combinedMessages.length > 0 &&
      messagesContainerRef.current
    ) {
      const container = messagesContainerRef.current;
      container.scrollTo({ top: chatTrayState.scrollOffset });
      // update auto scroll flag based on restored position
      const dist =
        container.scrollHeight -
        chatTrayState.scrollOffset -
        container.clientHeight;
      autoScrollRef.current = dist < 100;
      initialRestoreDone.current = true;
    }
  }, [
    combinedMessages,
    chatTrayState.conversationId,
    chatTrayState.scrollOffset,
    selectedConversationId,
  ]);

  // Keep chatTrayState atom in sync with current conversation mode
  useEffect(() => {
    setChatTrayState((prev) => ({
      ...prev,
      conversationId: selectedConversationId ?? null,
      isNewChat,
    }));
  }, [selectedConversationId, isNewChat, setChatTrayState]);

  // Track scroll to update offset live
  const handlePersistedScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const offset = container.scrollTop;
    setChatTrayState((prev) => ({ ...prev, scrollOffset: offset }));

    // Disable auto-scroll if the user is more than 100 px from bottom
    const distanceFromBottom =
      container.scrollHeight - offset - container.clientHeight;
    autoScrollRef.current = distanceFromBottom < 100;
  }, [setChatTrayState]);

  /**
   * Debounce the title filter input.
   *
   * This effect updates `debouncedTitle` 500ms after the user stops typing,
   * which in turn triggers the GET_CONVERSATIONS query to refetch with the new filter.
   *
   * It is crucial that this hook is defined at the top level, not conditionally.
   */
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedTitle(titleFilter);
    }, 500); // Adjust delay as needed

    return () => clearTimeout(timer);
  }, [titleFilter]);

  // WebSocket dispatcher hook — depends on streamHandlers above. Returns the
  // stable `onMessage` callback consumed by useWebSocketAuth.
  const handleAgentMessage = useChatAgentMessageHandler({
    pendingApprovalRef,
    setPendingApproval,
    setShowApprovalModal,
    setWsError,
    setChat,
    setServerMessages,
    setContextStatus,
    setCompactionNotice,
    streamHandlers,
  });

  const wsUrl = getWebSocketUrl(documentId, selectedConversationId, corpusId);
  const wsEnabled = !!(selectedConversationId || isNewChat);
  const { isConnected: wsReady, send: wsSend } = useWebSocketAuth({
    url: wsUrl,
    enabled: wsEnabled,
    onMessage: handleAgentMessage,
    onOpen: () => setWsError(null),
    onAuthInvalid: () =>
      setWsError("Authentication failed. Please log in again."),
  });

  // Warm-up ticker visibility: shown only during the gap between the user
  // sending and the first assistant message arriving. Once an in-flight
  // assistant message exists, its inline StreamingThoughtTicker takes over.
  const showWarmupTicker = useMemo(() => {
    const last = combinedMessages[combinedMessages.length - 1];
    return !!last && !last.isAssistant && wsReady;
  }, [combinedMessages, wsReady]);

  /**
   * Load existing conversation by ID, clearing local state, then showing chat UI.
   * @param conversationId The ID of the chosen conversation
   */
  const loadConversation = (conversationId: string): void => {
    setSelectedConversationId(conversationId);
    setIsNewChat(false);
    setShowLoad(false);
    // Clear both local chat state and server messages
    setChat([]);
    setServerMessages([]);
    setPendingApproval(null);

    // Fetch messages with proper variables
    fetchChatMessages({
      variables: {
        conversationId,
        limit: 10,
      },
      // Add fetchPolicy to ensure we always get fresh data
      fetchPolicy: "network-only",
    });
  };

  /**
   * Exit the current conversation and reset chat state.
   */
  const exitConversation = (): void => {
    setIsNewChat(false);
    setShowLoad(false);
    setNewMessage("");
    setChat([]);
    setServerMessages([]);
    setSelectedConversationId(undefined);
    setPendingApproval(null);
    setShowApprovalModal(false);
    // Clearing selectedConversationId + isNewChat makes wsEnabled false,
    // and useWebSocketAuth tears the socket down on its next effect run.
    refetch();
  };

  /**
   * Start a new chat (unselect existing conversation).
   */
  const startNewChat = (): void => {
    setIsNewChat(true);
    setSelectedConversationId(undefined);
    setShowLoad(false);
    setChat([]);
    setServerMessages([]);
    setPendingApproval(null);
    // Potentially you'll create a new conversation server-side
  };

  /**
   * Handle infinite scroll triggers for loading more conversation summary cards.
   * Loads next page if available.
   */
  const handleFetchMoreConversations = useCallback(() => {
    if (
      !loading &&
      data?.conversations?.pageInfo?.hasNextPage &&
      typeof fetchMore === "function"
    ) {
      fetchMore({
        variables: {
          documentId,
          limit: 5,
          cursor: data.conversations.pageInfo.endCursor,
        },
      }).catch((err: any) => {
        console.error("Failed to fetch more conversations:", err);
      });
    }
  }, [loading, data, fetchMore, documentId]);

  // Send handlers hook — depends on streamHandlers (for the shared approval
  // mutator) plus the WebSocket connection from useWebSocketAuth above.
  const { sendMessageOverSocket, sendApprovalDecision, sendTextImmediately } =
    useChatSendHandlers({
      wsSend,
      wsReady,
      userEmail: user_obj?.email,
      newMessage,
      pendingApproval,
      sendingLockRef,
      setChat,
      setNewMessage,
      setWsError,
      setShowApprovalModal,
      setPendingApproval,
      updateMessageApprovalStatus,
    });

  /* ----------------------------------------------------------- */
  /* Handle initialMessage (from FloatingDocumentInput)          */
  /* ----------------------------------------------------------- */

  // Store the latest initialMessage in a ref so we can clear it after use
  const pendingInitialRef = useRef<string | undefined>();

  useEffect(() => {
    if (initialMessage && initialMessage.trim()) {
      pendingInitialRef.current = initialMessage.trim();

      // If user hasn't opened/select a conversation yet, auto-start a new one
      if (!selectedConversationId && !isNewChat) {
        startNewChat();
      }
    }
  }, [initialMessage]);

  // Once the socket is ready, flush the pending initial message (if any)
  useEffect(() => {
    if (wsReady && pendingInitialRef.current) {
      sendTextImmediately(pendingInitialRef.current);
      pendingInitialRef.current = undefined;
    }
  }, [wsReady, sendTextImmediately]);

  // Render error if GraphQL query fails
  if (error) {
    return (
      <ErrorContainer initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <AlertCircle size={24} />
        Failed to load conversations
      </ErrorContainer>
    );
  }

  /**
   * Main UI return
   */
  return (
    <ChatContainer id="chat-container">
      <ConversationIndicator id="conversation-indicator">
        <AnimatePresence>
          {isNewChat || selectedConversationId || readOnly || !user_obj ? (
            <motion.div
              style={{
                display: "flex",
                flexDirection: "column",
                // Fill parent container - parent already constrains height
                height: "100%",
                width: "100%",
                position: "relative",
                // Prevent the container from overflowing
                overflow: "hidden",
              }}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              {/* Fixed Header */}
              <motion.div
                style={{
                  padding: "0.5rem 1rem",
                  borderBottom: "1px solid rgba(0,0,0,0.1)",
                  background: "rgba(255, 255, 255, 0.95)",
                  zIndex: 2,
                  flexShrink: 0, // Prevent header from shrinking
                }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                {!readOnly && user_obj && (
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<ArrowLeft size={16} />}
                    onClick={exitConversation}
                    style={{
                      background: "transparent",
                      padding: "0.5rem",
                    }}
                  >
                    Back to Conversations
                  </Button>
                )}
                <ReopenApprovalButton
                  pendingApproval={pendingApproval}
                  showApprovalModal={showApprovalModal}
                  setShowApprovalModal={setShowApprovalModal}
                  combinedMessages={combinedMessages}
                  setPendingApproval={setPendingApproval}
                />
              </motion.div>

              {/* Scrollable Messages Container */}
              <motion.div
                style={{
                  flex: "1 1 0", // Changed from "1 1 auto" to "1 1 0" to prevent overflow
                  overflowY: "auto",
                  overflowX: "hidden",
                  minHeight: 0, // Critical for flex children with overflow
                  padding: "1rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                  paddingBottom: "1rem", // Reduced from 6rem
                }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                id="messages-container"
                ref={messagesContainerRef}
                onScroll={handlePersistedScroll}
              >
                {combinedMessages.length === 0 &&
                  !showWarmupTicker &&
                  !isAssistantResponding && (
                    <ChatEmptyState data-testid="chat-empty-state">
                      <ChatEmptyStateIcon>
                        <MessageCircle />
                      </ChatEmptyStateIcon>
                      <ChatEmptyStateTitle>
                        Ask me about this document
                      </ChatEmptyStateTitle>
                      <ChatEmptyStateDescription>
                        I can read it, find sections, and answer questions.
                      </ChatEmptyStateDescription>
                      <ChatEmptyStateHint>
                        <AtSign size={14} />
                        Try @-mentioning a specific agent for deeper analysis.
                      </ChatEmptyStateHint>
                    </ChatEmptyState>
                  )}
                {combinedMessages.map((msg, idx) => {
                  // Find if this message has sources in our sourced messages state
                  const sourcedMessage = sourcedMessages.find(
                    (m) => m.messageId === msg.messageId
                  );

                  // Map sources to include onClick handlers and text content
                  const sources =
                    sourcedMessage?.sources.map((source, index) => ({
                      text: source.rawText || `Source ${index + 1}`,
                      onClick: () => {
                        // Update the chatSourcesAtom with the selected source
                        setChatSourceState((prev) => ({
                          ...prev,
                          selectedMessageId: sourcedMessage.messageId,
                          selectedSourceIndex: index,
                        }));
                        // Update URL with annotation selection (single source of truth)
                        if (source.annotation_id) {
                          // "AnnotationType" matches the Graphene class
                          // name in config/graphql/annotation_types.py.
                          const globalId = toGlobalId(
                            "AnnotationType",
                            source.annotation_id
                          );
                          updateAnnotationSelectionParams(location, navigate, {
                            annotationIds: [globalId],
                          });
                        }
                      },
                    })) || [];

                  return (
                    <ChatMessage
                      key={msg.messageId || idx}
                      {...msg}
                      hasSources={!!sourcedMessage?.sources.length}
                      hasTimeline={msg.hasTimeline}
                      sources={sources}
                      timeline={msg.timeline}
                      approvalStatus={msg.approvalStatus}
                      isSelected={
                        sourcedMessage?.messageId === selectedMessageId
                      }
                      onSelect={() => {
                        if (sourcedMessage) {
                          const isDeselecting =
                            selectedMessageId === sourcedMessage.messageId;
                          setChatSourceState((prev) => ({
                            ...prev,
                            selectedMessageId: isDeselecting
                              ? null // deselect if already selected
                              : sourcedMessage.messageId,
                            selectedSourceIndex: null, // Reset source selection when message selection changes
                          }));
                          // Update URL annotation selection: clear on deselect
                          if (isDeselecting) {
                            updateAnnotationSelectionParams(
                              location,
                              navigate,
                              { annotationIds: [] }
                            );
                          }
                          // Call the onMessageSelect callback when a message with sources is selected
                          if (sourcedMessage.sources.length > 0) {
                            onMessageSelect?.();
                          }
                        }
                      }}
                    />
                  );
                })}
                {/* Pre-message warm-up ticker. When the user has just sent a
                    message and the assistant's reply hasn't been created yet
                    (the brief window between ASYNC_START's empty payload and
                    the first ASYNC_CONTENT/ASYNC_THOUGHT), there's no in-flight
                    assistant message to host the per-message ticker — so we
                    render a standalone one here. Replaces the old standalone
                    "AI Assistant is thinking..." pill.
                    AnimatePresence is required for the exit animation to fire. */}
                <AnimatePresence>
                  {showWarmupTicker && (
                    <motion.div
                      key="warmup-ticker"
                      data-testid="streaming-warmup-ticker-wrapper"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.2 }}
                      style={{ paddingLeft: "1rem", paddingTop: "0.5rem" }}
                    >
                      <StreamingThoughtTicker timeline={[]} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>

              {/* Compaction banner — visible during streaming when compaction fires */}
              {compactionNotice && (
                <div
                  data-testid="compaction-banner"
                  style={{
                    padding: "0.5rem 1rem",
                    borderTop: `1px solid ${OS_LEGAL_COLORS.blueBorder}`,
                    background: `linear-gradient(135deg, ${OS_LEGAL_COLORS.blueSurface} 0%, ${OS_LEGAL_COLORS.blueBorder} 100%)`,
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
                    padding: "0.375rem 1rem 0.625rem",
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
              {/* Fixed Footer with Input */}
              <ChatInputContainer
                $isTyping={isNewChat}
                style={{
                  zIndex: 3,
                  background: "rgba(255, 255, 255, 0.95)",
                  backdropFilter: "blur(10px)",
                  borderTop: "1px solid rgba(0, 0, 0, 0.1)",
                  flexShrink: 0, // Prevent input from being compressed
                }}
              >
                {wsError ? (
                  <ErrorMessage data-testid="ws-error-message">
                    <motion.div
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ type: "spring", damping: 20 }}
                    >
                      {wsError}
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => window.location.reload()}
                        style={{
                          marginLeft: "0.75rem",
                          background: OS_LEGAL_COLORS.danger,
                          color: "white",
                          border: "none",
                          boxShadow: "0 2px 4px rgba(220,53,69,0.2)",
                        }}
                      >
                        Reconnect
                      </Button>
                    </motion.div>
                  </ErrorMessage>
                ) : (
                  <ConnectionStatus
                    connected={wsReady}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    data-testid="connection-status"
                    data-connected={wsReady}
                  />
                )}
                {mentionPopover}
                <ChatInputWrapper>
                  <ChatInput
                    data-testid="chat-input"
                    ref={textareaRef}
                    value={newMessage}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                      const value = e.target.value;
                      const capped = value.slice(0, MAX_MESSAGE_LENGTH);
                      setNewMessage(capped);
                      const caret = e.target.selectionStart ?? capped.length;
                      handleMentionValueChange(capped, caret);
                      // Use setTimeout to ensure DOM updates before measuring
                      setTimeout(adjustTextareaHeightCb, 0);
                    }}
                    placeholder={
                      !wsReady
                        ? "Waiting for connection..."
                        : isAssistantResponding
                        ? "Assistant is responding..."
                        : "Type your message..."
                    }
                    disabled={!wsReady || isAssistantResponding}
                    onKeyDown={(
                      e: React.KeyboardEvent<HTMLTextAreaElement>
                    ) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (newMessage.trim()) {
                          sendMessageOverSocket();
                        }
                      }
                    }}
                    rows={1}
                  />
                  {newMessage.length > MAX_MESSAGE_LENGTH * 0.9 && (
                    <CharacterCount
                      $nearLimit={newMessage.length >= MAX_MESSAGE_LENGTH}
                    >
                      {newMessage.length}/{MAX_MESSAGE_LENGTH}
                    </CharacterCount>
                  )}
                </ChatInputWrapper>
                <SendButton
                  $hasText={!!newMessage.trim()}
                  disabled={
                    !wsReady || !newMessage.trim() || isAssistantResponding
                  }
                  onClick={sendMessageOverSocket}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  animate={
                    wsReady && newMessage.trim() && !isAssistantResponding
                      ? { y: [0, -2, 0] }
                      : {}
                  }
                  transition={{ duration: 0.2 }}
                >
                  <Send size={18} />
                </SendButton>
              </ChatInputContainer>
            </motion.div>
          ) : (
            <DocumentConversationListView
              conversations={conversations}
              showSearch={showSearch}
              setShowSearch={setShowSearch}
              showDatePicker={showDatePicker}
              setShowDatePicker={setShowDatePicker}
              titleFilter={titleFilter}
              setTitleFilter={setTitleFilter}
              createdAtGte={createdAtGte}
              setCreatedAtGte={setCreatedAtGte}
              createdAtLte={createdAtLte}
              setCreatedAtLte={setCreatedAtLte}
              searchInputRef={searchInputRef}
              datePickerRef={datePickerRef}
              loadConversation={loadConversation}
              handleFetchMoreConversations={handleFetchMoreConversations}
              startNewChat={startNewChat}
            />
          )}
        </AnimatePresence>
      </ConversationIndicator>

      {/* Approval Overlay */}
      <AnimatePresence>
        {showApprovalModal && pendingApproval && (
          <ApprovalDialog
            pendingApproval={pendingApproval}
            onHide={() => setShowApprovalModal(false)}
            onDecision={sendApprovalDecision}
          />
        )}
      </AnimatePresence>
    </ChatContainer>
  );
};
