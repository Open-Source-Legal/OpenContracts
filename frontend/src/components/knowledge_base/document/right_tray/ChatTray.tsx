/**
 * ChatTray Component - Vertical Alignment For Sidebar
 *
 * This component now connects to our websocket backend IF the user is logged in
 * and we have a valid auth token in the Apollo reactive vars.
 * It will:
 *   1) Load existing conversation data from GraphQL (GET_CONVERSATIONS).
 *   2) If authenticated, open a WebSocket to stream new messages with partial updates
 *      (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH) or synchronous messages (SYNC_CONTENT).
 *   3) Display those messages in real time, appending them to the chat.
 *   4) Allow sending user queries through the socket.
 */

import {
  ChatContainer,
  ConversationIndicator,
  ErrorContainer,
} from "../ChatContainers";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, ArrowLeft, Send } from "lucide-react";
import { Button } from "semantic-ui-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChatMessage,
  ChatMessageProps,
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
import { authToken, userObj } from "../../../../graphql/cache";
import { getWebSocketUrl } from "../utils";
import {
  ChatInputContainer,
  ChatInput,
  SendButton,
  ErrorMessage,
  ConnectionStatus,
  ChatInputWrapper,
  CharacterCount,
} from "../ChatContainers";
import {
  useChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
} from "../../../annotator/context/ChatSourceAtom";
import { TimelineEntry } from "../../../widgets/chat/ChatMessage";
import { useUISettings } from "../../../annotator/hooks/useUISettings";
import useWindowDimensions from "../../../hooks/WindowDimensionHook";
import { useLocation, useNavigate } from "react-router-dom";
import { updateAnnotationSelectionParams } from "../../../../utils/navigationUtils";
import { toGlobalId } from "../../../../utils/idValidation";
import type {
  WebSocketSources,
  MessageData,
  ContextStatus,
  CompactionNotice,
} from "../../../chat/types";
import { ApprovalOverlay, ReopenApprovalButton } from "./ApprovalOverlay";
import type { PendingApproval } from "./ApprovalOverlay";
import { DocumentConversationListView } from "./ConversationListView";

export type { WebSocketSources, MessageData } from "../../../chat/types";

/**
 * ChatTray props definition.
 */
interface ChatTrayProps {
  documentId: string;
  showLoad: boolean;
  setShowLoad: React.Dispatch<React.SetStateAction<boolean>>;
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
  showLoad,
  setShowLoad,
  onMessageSelect,
  corpusId,
  initialMessage,
  readOnly = false,
}) => {
  // Routing hooks for URL-driven annotation selection
  const location = useLocation();
  const navigate = useNavigate();

  // User / Auth state – must be declared before any state that depends on it
  const user_obj = useReactiveVar(userObj);
  // Note: auth_token is kept for WebSocket URL construction which requires the token
  // for authentication. GraphQL queries use userObj for skip conditions.
  const auth_token = useReactiveVar(authToken);

  // Chat state
  // Start with new chat if readOnly OR if user is anonymous
  const [isNewChat, setIsNewChat] = useState<boolean>(readOnly || !user_obj);
  const [newMessage, setNewMessage] = useState("");
  const [chat, setChat] = useState<ChatMessageProps[]>([]);
  const [wsReady, setWsReady] = useState(false);
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

  // (user_obj, auth_token declared above)

  // WebSocket reference
  const socketRef = useRef<WebSocket | null>(null);
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
  const [
    fetchChatMessages,
    {
      data: msgData,
      fetchMore: fetchMoreMessages,
      loading: loadingMessages,
      error: messagesError,
    },
  ] = useLazyQuery<GetChatMessagesOutputs, GetChatMessagesInputs>(
    GET_CHAT_MESSAGES
  );

  const { chatTrayState, setChatTrayState } = useUISettings();

  // Ref to manage auto-scrolling behaviour
  const autoScrollRef = useRef(true);

  /**
   * Update the approval status of a message in both serverMessages and chat arrays
   */
  const updateMessageApprovalStatus = useCallback(
    (messageId: string, status: "approved" | "rejected") => {
      // Clear pendingApproval if this is the message being updated
      setPendingApproval((current) => {
        if (current?.messageId === messageId) {
          return null;
        }
        return current;
      });

      // Update serverMessages
      setServerMessages((prev) =>
        prev.map((msg) => {
          if (msg.messageId === messageId) {
            return { ...msg, approvalStatus: status, isComplete: true };
          }
          return msg;
        })
      );

      // Update chat messages
      setChat((prev) =>
        prev.map((msg) => {
          if (msg.messageId === messageId) {
            return { ...msg, approvalStatus: status, isComplete: true };
          }
          return msg;
        })
      );
    },
    []
  );

  // Flag so we only run initial scroll restore once
  const initialRestoreDone = useRef(false);

  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  // State for auto-resizing textarea
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const MAX_MESSAGE_LENGTH = 4000;

  // Auto-resize function
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = "auto";

    // Set new height based on content
    const newHeight = Math.min(textarea.scrollHeight, 200); // Max 200px
    textarea.style.height = `${newHeight}px`;
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
    adjustTextareaHeight();
  }, [adjustTextareaHeight]);

  /**
   * On server data load, we map messages to local ChatMessageProps and
   * also store any 'sources' in the chatSourcesAtom (so pins and selection work).
   */
  useEffect(() => {
    if (!msgData?.chatMessages) {
      return;
    }
    const messages = msgData.chatMessages;

    // First, register them in our chatSourcesAtom if they have sources
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
          srvMsg.createdAt,
          srvMsgData.timeline
        );
      }
    });

    console.log("messages", messages);

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

  // Add ref for messages container
  const messagesContainerRef = useRef<HTMLDivElement>(null);

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

  function appendStreamingTokenToChat(
    token: string,
    overrideMessageId?: string
  ): string {
    // Return the messageId
    if (!token) return "";

    let messageId = "";
    setChat((prev) => {
      const lastMessage = prev[prev.length - 1];

      // If we were already streaming the assistant's last message, just append:
      if (lastMessage && lastMessage.isAssistant) {
        messageId = lastMessage.messageId || ""; // Capture existing ID
        console.log("append to existing messageId", messageId);
        const updatedLast = {
          ...lastMessage,
          content: lastMessage.content + token,
          isComplete: false,
        };
        return [...prev.slice(0, -1), updatedLast];
      } else {
        // Otherwise, create a fresh assistant message with a brand-new messageId
        messageId =
          overrideMessageId ||
          `msg_${Date.now()}_${Math.random().toString(36).substr(2)}`;
        console.log("append to new messageId", messageId);
        return [
          ...prev,
          {
            messageId, // Use the same ID we'll return
            user: "Assistant",
            content: token,
            timestamp: new Date().toLocaleString(),
            isAssistant: true,
            hasTimeline: false,
            timeline: [],
            isComplete: false,
          },
        ];
      }
    });

    // Auto-scroll to bottom only if user hasn't scrolled up
    const container = messagesContainerRef.current;
    if (container) {
      const isScrolledUp =
        container.scrollTop <
        container.scrollHeight - container.clientHeight - 100;
      if (!isScrolledUp) {
        setTimeout(
          () =>
            container.scrollTo({
              top: container.scrollHeight,
              behavior: "smooth",
            }),
          0
        );
      }
    }

    return messageId;
  }

  /**
   * Append an *agent thought* (or tool call/result) to the timeline of the
   * streaming assistant message so the user can watch reasoning unfold.
   */
  const appendThoughtToMessage = (
    thoughtText: string,
    data: MessageData["data"] | undefined
  ): void => {
    const messageId = data?.message_id;
    if (!messageId || !thoughtText) return;

    // Determine timeline entry type
    let entryType: TimelineEntry["type"] = "thought";
    if (data?.compaction) {
      entryType = "compaction";
      setCompactionNotice({
        tokensBefore: data.compaction.tokens_before,
        tokensAfter: data.compaction.tokens_after,
        contextWindow: data.compaction.context_window,
      });
    } else if (data?.tool_name && data?.args) entryType = "tool_call";
    else if (data?.tool_name && !data?.args) entryType = "tool_result";

    const newEntry: TimelineEntry = {
      type: entryType,
      text: thoughtText,
      tool: data?.tool_name,
      args: data?.args,
      result: data?.tool_result,
    };

    // Update chat UI timeline
    setChat((prev) => {
      const idx = prev.findIndex((m) => m.messageId === messageId);
      if (idx === -1) {
        // No message yet (thought arrived very early) – create skeleton.
        return [
          ...prev,
          {
            messageId,
            user: "Assistant",
            content: "", // will be filled later
            timestamp: new Date().toLocaleString(),
            isAssistant: true,
            hasTimeline: true,
            timeline: [newEntry],
            isComplete: false,
          },
        ];
      }

      const msg = prev[idx];
      const timeline = msg.timeline ? [...msg.timeline, newEntry] : [newEntry];
      const updated = {
        ...msg,
        hasTimeline: true,
        timeline,
        isComplete: false,
      } as ChatMessageProps;

      return [...prev.slice(0, idx), updated, ...prev.slice(idx + 1)];
    });
  };

  /**
   * Finalize a partially-streamed response by replacing the last chat entry
   * with the final content (and calling `handleCompleteMessage` to store sources).
   * @param content - the fully streamed final response
   * @param sourcesData - optional array of WebSocketSources describing pinned info
   * @param overrideId - optional message ID to use
   * @param timelineData - optional timeline entries
   */
  const finalizeStreamingResponse = (
    content: string,
    sourcesData?: WebSocketSources[],
    overrideId?: string,
    timelineData?: TimelineEntry[]
  ): void => {
    console.log("finalizeStreamingResponse", {
      content,
      sourcesData,
      overrideId,
    });

    let lastMsgId: string | undefined;
    setChat((prev) => {
      if (!prev.length) return prev;
      // Determine which message to update: prefer overrideId match, else last assistant
      let updateIdx = prev.findIndex((m) => m.messageId === overrideId);
      if (updateIdx === -1) {
        // Fallback: last assistant message
        const lastIdxRev = [...prev].reverse().findIndex((m) => m.isAssistant);
        if (lastIdxRev === -1) return prev;
        updateIdx = prev.length - 1 - lastIdxRev;
      }

      const updatedMessages = [...prev];
      const assistantMsg = updatedMessages[updateIdx];
      console.log("XOXO - Found assistant message to update:", {
        messageId: assistantMsg.messageId,
        oldContent: assistantMsg.content.substring(0, 50) + "...",
      });

      lastMsgId = assistantMsg.messageId;

      updatedMessages[updateIdx] = {
        ...assistantMsg,
        content,
        isComplete: true,
      };
      console.log("Updated message with final content:", {
        messageId: lastMsgId,
      });

      // Now store the final content + sources in ChatSourceAtom with the same ID
      handleCompleteMessage(
        content,
        sourcesData,
        lastMsgId,
        undefined,
        timelineData
      );

      return updatedMessages;
    });
  };

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

  /**
   * Whenever the selected conversation changes, (re)establish the WebSocket connection.
   */
  useEffect(() => {
    // If no conversation is selected and not in new chat mode, close any socket and exit.
    if (!selectedConversationId && !isNewChat) {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setWsReady(false);
      return;
    }

    // Build WebSocket URL, including conversation ID
    const wsUrl = getWebSocketUrl(
      documentId,
      auth_token || undefined,
      selectedConversationId,
      corpusId
    );
    const newSocket = new WebSocket(wsUrl);

    newSocket.onopen = () => {
      setWsReady(true);
      setWsError(null);
      console.log(
        "WebSocket connected for conversation:",
        selectedConversationId
      );
    };

    newSocket.onerror = (event) => {
      setWsReady(false);
      setWsError("Error connecting to the websocket.");
      console.error("WebSocket error:", event);
    };

    newSocket.onmessage = (event) => {
      try {
        const messageData: MessageData = JSON.parse(event.data);
        if (!messageData) return;
        const { type: msgType, content, data } = messageData;

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

        // Check if any message includes approval status update
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
            // Clear pending approval if agent resumes after approval decision
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
              // Update the approval status of the message
              updateMessageApprovalStatus(
                pendingApproval.messageId,
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

              // Update the message to show awaiting status
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
            // Clear pending approval when streaming finishes (covers both approval and rejection cases)
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
              // Update status based on the final content or metadata
              if (data?.approval_decision) {
                updateMessageApprovalStatus(
                  pendingApproval.messageId,
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
            // SYNC_CONTENT is for standalone messages that don't stream.
            // Add it directly to the chat state.
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
    };

    newSocket.onclose = (event) => {
      setWsReady(false);
      console.warn("WebSocket closed:", event);
    };

    socketRef.current = newSocket;

    // Cleanup on unmount or conversation change
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [auth_token, documentId, selectedConversationId, isNewChat, corpusId]);

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
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
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

  /**
   * Send typed message over the WebSocket to the assistant, and add it locally.
   */
  const sendMessageOverSocket = useCallback((): void => {
    const trimmed = newMessage.trim();
    if (!trimmed || !socketRef.current) return;
    if (!wsReady) {
      console.warn("WebSocket not ready yet");
      return;
    }

    // Check if a message is already being sent
    if (sendingLockRef.current) {
      console.warn("Message is already being sent, ignoring duplicate send.");
      return;
    }

    // Lock sending to prevent duplicate sends
    sendingLockRef.current = true;

    try {
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
      socketRef.current.send(JSON.stringify({ query: trimmed }));
      setNewMessage("");
      setWsError(null);
    } catch (err) {
      console.error("Failed to send message:", err);
      setWsError("Failed to send message. Please try again.");
    } finally {
      // Release the lock after a debounce interval (e.g., 300ms)
      setTimeout(() => {
        sendingLockRef.current = false;
      }, 300);
    }
  }, [newMessage, user_obj?.email, wsReady]);

  /**
   * Send approval decision back to the WebSocket.
   */
  const sendApprovalDecision = useCallback(
    (approved: boolean): void => {
      if (!pendingApproval || !socketRef.current || !wsReady) {
        console.warn("Cannot send approval decision - missing requirements");
        return;
      }

      try {
        const messageData = {
          approval_decision: approved,
          llm_message_id: pendingApproval.messageId,
        };

        socketRef.current.send(JSON.stringify(messageData));

        // Hide the modal immediately after sending the decision (optimistic UI)
        setShowApprovalModal(false);

        // Update the message status immediately (optimistic update)
        updateMessageApprovalStatus(
          pendingApproval.messageId,
          approved ? "approved" : "rejected"
        );

        // Clear pendingApproval immediately since we've processed the decision
        setPendingApproval(null);
        setWsError(null);
      } catch (err) {
        console.error("Failed to send approval decision:", err);
        setWsError("Failed to send approval decision. Please try again.");
        // Re-show modal on error so user can try again
        setShowApprovalModal(true);
      }
    },
    [pendingApproval, wsReady, updateMessageApprovalStatus]
  );

  // Render error if GraphQL query fails
  if (error) {
    return (
      <ErrorContainer initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <AlertCircle size={24} />
        Failed to load conversations
      </ErrorContainer>
    );
  }

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
    const messageId = overrideId ?? `msg_${Date.now()}`; // Only fallback if really needed
    console.log("XOXO - handleCompleteMessage messageId", messageId);
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
        } as typeof existingMsg;

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
            },
          ],
          selectedMessageId: overrideId ? prev.selectedMessageId : messageId,
        };
      }
    });
  };

  /**
   * Merge *additional* sources arriving via ASYNC_SOURCES into the existing
   * ChatSourceAtom + local chat message so the user can click pins while the
   * answer is still streaming.
   */
  const mergeSourcesIntoMessage = (
    sourcesData: WebSocketSources[] | undefined,
    overrideId?: string
  ): void => {
    if (!sourcesData?.length || !overrideId) return;

    // First convert incoming sources → ChatMessageSource objects.
    const mappedSources = mapWebSocketSourcesToChatMessageSources(
      sourcesData,
      overrideId
    );

    // Update ChatSourceAtom – merge or append sources for the message.
    setChatSourceState((prev) => {
      const idx = prev.messages.findIndex((m) => m.messageId === overrideId);
      if (idx === -1) {
        // Message not yet in atom – create skeleton entry so pins work.
        return {
          ...prev,
          messages: [
            ...prev.messages,
            {
              messageId: overrideId,
              content: "", // will be filled later by finalizeStreamingResponse
              timestamp: new Date().toISOString(),
              sources: mappedSources,
              isComplete: false,
            },
          ],
        };
      }

      // Merge with existing sources (avoid duplicates by annotation_id)
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
      const mergedMsg = { ...existing, sources: mergedSources };
      updatedMessages[idx] = mergedMsg;

      return { ...prev, messages: updatedMessages };
    });

    // Update transient chat UI so pin indicator appears immediately.
    setChat((prev) => {
      const idx = prev.findIndex((m) => m.messageId === overrideId);
      if (idx === -1) return prev;
      const msg = prev[idx];
      return [
        ...prev.slice(0, idx),
        { ...msg, hasSources: true },
        ...prev.slice(idx + 1),
      ];
    });
  };

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

  /**
   * Helper to send a text message immediately (bypassing newMessage state).
   */
  const sendTextImmediately = useCallback(
    (text: string): void => {
      const trimmed = text.trim();
      if (!trimmed || !socketRef.current || !wsReady) return;

      if (sendingLockRef.current) return;
      sendingLockRef.current = true;

      try {
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

        socketRef.current.send(JSON.stringify({ query: trimmed }));
        setWsError(null);
      } catch (err) {
        console.error("Failed to send initial message:", err);
        setWsError("Failed to send message. Please try again.");
      } finally {
        setTimeout(() => {
          sendingLockRef.current = false;
        }, 300);
      }
    },
    [wsReady, user_obj?.email]
  );

  // Once the socket is ready, flush the pending initial message (if any)
  useEffect(() => {
    if (wsReady && pendingInitialRef.current) {
      sendTextImmediately(pendingInitialRef.current);
      pendingInitialRef.current = undefined;
    }
  }, [wsReady, sendTextImmediately]);

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
                    size="small"
                    onClick={exitConversation}
                    style={{
                      background: "transparent",
                      padding: "0.5rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <ArrowLeft size={16} />
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
              </motion.div>

              {/* Compaction banner — visible during streaming when compaction fires */}
              {compactionNotice && (
                <div
                  data-testid="compaction-banner"
                  style={{
                    padding: "0.5rem 1rem",
                    borderTop: "1px solid #bfdbfe",
                    background:
                      "linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.8125rem",
                    color: "#1e40af",
                    flexShrink: 0,
                    animation: "compaction-pulse 2s ease-in-out infinite",
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#2563eb"
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
                    padding: "0.25rem 1rem",
                    borderTop: "1px solid rgba(0, 0, 0, 0.06)",
                    background: "rgba(255, 255, 255, 0.95)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.75rem",
                    color: "#64748b",
                    flexShrink: 0,
                  }}
                >
                  <div
                    data-testid="context-meter-track"
                    style={{
                      flex: 1,
                      height: 4,
                      borderRadius: 2,
                      background: "#e2e8f0",
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
                            ? "#ef4444"
                            : contextStatus.used_tokens /
                                contextStatus.context_window >
                              0.6
                            ? "#f59e0b"
                            : "#22c55e",
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
                        background: "#dbeafe",
                        color: "#2563eb",
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
                        size="small"
                        onClick={() => window.location.reload()}
                        style={{
                          marginLeft: "0.75rem",
                          background: "#dc3545",
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
                <ChatInputWrapper>
                  <ChatInput
                    data-testid="chat-input"
                    ref={textareaRef}
                    value={newMessage}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => {
                      const value = e.target.value;
                      const capped = value.slice(0, MAX_MESSAGE_LENGTH);
                      setNewMessage(capped);
                      // Use setTimeout to ensure DOM updates before measuring
                      setTimeout(adjustTextareaHeight, 0);
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
        <ApprovalOverlay
          pendingApproval={pendingApproval}
          showApprovalModal={showApprovalModal}
          setShowApprovalModal={setShowApprovalModal}
          sendApprovalDecision={sendApprovalDecision}
        />
      </AnimatePresence>
    </ChatContainer>
  );
};
