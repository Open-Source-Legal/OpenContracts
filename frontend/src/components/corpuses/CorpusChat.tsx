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
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLazyQuery, useQuery, useReactiveVar } from "@apollo/client";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, ArrowLeft, Send, Home } from "lucide-react";
import { Button, Loader } from "semantic-ui-react";
import { CONVERSATION_TYPE } from "../../assets/configurations/constants";

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

import { authToken, userObj } from "../../graphql/cache";
import { IconButton } from "../knowledge_base/document/FilterContainers";
import {
  useChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
  ChatMessageSource,
} from "../annotator/context/ChatSourceAtom";
import {
  ChatMessage,
  ChatMessageProps,
  TimelineEntry,
} from "../widgets/chat/ChatMessage";
import { getCorpusQueryWebSocket } from "../chat/get_websockets";
import type {
  WebSocketSources,
  MessageData,
  ContextStatus,
  CompactionNotice,
} from "../chat/types";

import {
  ChatContainer,
  ConversationIndicator,
  ChatNavigationHeader,
  BackButton,
  NavigationTitle,
  MessagesArea,
  MessageWrapper,
  LatestMessageIndicator,
  ProcessingIndicator,
  ChatInputWrapper,
  EnhancedChatInputContainer,
  EnhancedChatInput,
  EnhancedSendButton,
  InputRow,
} from "./corpus_chat/styles";
import { ApprovalModal, PendingApproval } from "./corpus_chat/ApprovalModal";
import { CorpusConversationListView } from "./corpus_chat/ConversationListView";

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
  onClose?: () => void;
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
  onClose,
  onViewModeChange,
  onSourceNavigate,
}) => {
  // Chat state
  const [isNewChat, setIsNewChat] = useState(forceNewChat);
  const [newMessage, setNewMessage] = useState("");
  const [chat, setChat] = useState<ChatMessageProps[]>([]);
  const [wsReady, setWsReady] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);

  // Track whether the assistant is currently generating a response
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

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
  const auth_token = useReactiveVar(authToken);

  // WebSocket reference
  const socketRef = useRef<WebSocket | null>(null);
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
   * (Re)Establish the WebSocket connection if a conversation is selected (or if isNewChat),
   * otherwise close any existing socket.
   *
   * Note: We allow connections without auth_token to support anonymous users on public corpuses.
   * The backend will reject anonymous connections to non-public corpuses with code 4003.
   */
  useEffect(() => {
    if (!selectedConversationId && !isNewChat) {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setWsReady(false);
      return;
    }

    const wsUrl = getCorpusQueryWebSocket(
      corpusId,
      auth_token,
      isNewChat ? undefined : selectedConversationId
    );
    const newSocket = new WebSocket(wsUrl);

    newSocket.onopen = () => {
      setWsReady(true);
      setWsError(null);
      console.log(
        "WebSocket connected for corpus conversation:",
        selectedConversationId
      );
    };

    newSocket.onerror = (event) => {
      setWsReady(false);
      setWsError("Error connecting to the corpus WebSocket.");
      console.error("WebSocket error:", event);
    };

    newSocket.onmessage = (event) => {
      try {
        const messageData: MessageData = JSON.parse(event.data);
        if (!messageData) return;
        const { type: msgType, content, data } = messageData;

        switch (msgType) {
          case "ASYNC_START":
            setIsProcessing(true);
            appendStreamingTokenToChat(content, data?.message_id);
            break;
          case "ASYNC_CONTENT":
            appendStreamingTokenToChat(content, data?.message_id);
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
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
              });
              setShowApprovalModal(true);

              // Mark the message as awaiting approval
              updateMessageApprovalStatus(data.message_id, "awaiting");
            }
            break;
          case "ASYNC_APPROVAL_RESULT":
            // Informational – the backend echoes the decision back.
            if (
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
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
              pendingApproval &&
              data?.message_id === pendingApproval.messageId
            ) {
              setPendingApproval(null);
            }
            break;
          case "ASYNC_ERROR":
            setWsError(data?.error || "Agent error");
            finalizeStreamingResponse(
              data?.error || "Error",
              [],
              data?.message_id
            );
            setIsProcessing(false);
            break;
          case "SYNC_CONTENT": {
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

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [auth_token, corpusId, selectedConversationId, isNewChat]);

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

  // Modify the effect that sends the initial query
  useEffect(() => {
    // Do not send if the provided initialQuery is empty or whitespace
    if (
      initialQuery &&
      initialQuery.trim().length > 0 &&
      wsReady &&
      isNewChat
    ) {
      const timer = setTimeout(() => {
        if (socketRef.current && wsReady) {
          // Simply send the initial query over websocket (without adding it to chat)
          socketRef.current.send(JSON.stringify({ query: initialQuery }));
          setNewMessage("");
          setWsError(null);
        }
      }, 500);

      return () => clearTimeout(timer);
    }
  }, [initialQuery, wsReady, isNewChat]);

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
    setIsNewChat(true);
    setSelectedConversationId(undefined);
    setShowLoad(false);
    setChat([]);
    setServerMessages([]);
  }, [setShowLoad]);

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
    if (!trimmed || !socketRef.current || isProcessing) return;
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
      setChat((prev) => [
        ...prev,
        {
          user: user_obj?.email || "You",
          content: trimmed,
          timestamp: new Date().toLocaleString(),
          isAssistant: false,
        },
      ]);
      socketRef.current.send(JSON.stringify({ query: trimmed }));
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
  }, [newMessage, user_obj?.email, wsReady, isProcessing]);

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
      if (!pendingApproval || !socketRef.current || !wsReady) {
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

        socketRef.current.send(JSON.stringify(messageData));

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
    [pendingApproval, wsReady]
  );

  // If the GraphQL query fails entirely:
  if (error) {
    return (
      <ErrorContainer initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <AlertCircle size={24} />
        Failed to load corpus conversations
      </ErrorContainer>
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
                if (onClose) {
                  onClose();
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

                {/* Show processing indicator as a message in the chat */}
                {isProcessing && (
                  <MessageWrapper
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.3 }}
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      padding: "1rem 0",
                    }}
                  >
                    <ProcessingIndicator
                      initial={{ scale: 0.95 }}
                      animate={{ scale: 1 }}
                      transition={{
                        duration: 2,
                        repeat: Infinity,
                        repeatType: "reverse",
                        ease: "easeInOut",
                      }}
                    >
                      <div className="pulse-dot" />
                      <Loader active inline size="small" inverted />
                      <span>AI Assistant is thinking...</span>
                      <div
                        className="pulse-dot"
                        style={{ animationDelay: "0.5s" }}
                      />
                    </ProcessingIndicator>
                  </MessageWrapper>
                )}
              </MessagesArea>

              {/* Compaction banner (visible while compaction is underway) */}
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
                    padding: "0.25rem 1.5rem",
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
                  <InputRow>
                    <EnhancedChatInput
                      value={newMessage}
                      onChange={(e: {
                        target: { value: SetStateAction<string> };
                      }) => setNewMessage(e.target.value)}
                      placeholder={
                        wsReady
                          ? isProcessing
                            ? "Assistant is thinking..."
                            : "Type your corpus query..."
                          : "Waiting for connection..."
                      }
                      disabled={!wsReady || isProcessing}
                      onKeyPress={(e: { key: string }) => {
                        if (e.key === "Enter") {
                          sendMessageOverSocket();
                        }
                      }}
                    />
                    <EnhancedSendButton
                      disabled={!wsReady || !newMessage.trim() || isProcessing}
                      onClick={sendMessageOverSocket}
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      animate={wsReady ? { y: [0, -2, 0] } : {}}
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
