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
import { formatDistanceToNow } from "date-fns";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  Plus,
  Search,
  Send,
  X,
  Home,
  CheckCircle,
} from "lucide-react";
import { Button, Loader } from "semantic-ui-react";
import styled from "styled-components";
import { color } from "../../theme/colors";
import { MessageCircle } from "lucide-react";
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
  ConversationGrid,
  ChatInputContainer,
  ChatInput,
  SendButton,
  ErrorMessage,
  ConnectionStatus,
  FilterContainer,
} from "../knowledge_base/document/ChatContainers";

import { authToken, userObj, showQueryViewState } from "../../graphql/cache";
import {
  DatePickerExpanded,
  ExpandingInput,
  IconButton,
} from "../knowledge_base/document/FilterContainers";
import {
  useChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
} from "../annotator/context/ChatSourceAtom";
import { MultipageAnnotationJson } from "../types";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import {
  ChatMessage,
  ChatMessageProps,
  TimelineEntry,
} from "../widgets/chat/ChatMessage";
import { getCorpusQueryWebSocket } from "../chat/get_websockets";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import useWindowDimensions from "../hooks/WindowDimensionHook";

/**
 * A helper interface representing the properties of data included in websocket messages,
 * specifically any source annotations or label metadata.
 */
interface WebSocketSources {
  page: number;
  json: { start: number; end: number } | MultipageAnnotationJson;
  annotation_id: number;
  label: string;
  label_id: number;
  rawText: string;
}

/**
 * An interface for the full websocket message structure.
 * Includes the type of content (async start, streaming content, final, etc.),
 * the actual text content, and optional annotation data.
 */
interface MessageData {
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
    pending_tool_call?: {
      name: string;
      arguments: any;
      tool_call_id?: string;
    };
    [key: string]: any;
  };
}

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
}

// Add these styled components near your other styled components
const ConversationHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;

  h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #1a202c;
    margin: 0;
  }

  .actions {
    display: flex;
    gap: 0.75rem;
  }

  @media (max-width: 768px) {
    padding: 1rem;

    h2 {
      font-size: 1.25rem;
    }

    .actions button {
      padding: 0.5rem 0.75rem !important;
      font-size: 0.85rem !important;
    }
  }
`;

const EnhancedConversationGrid = styled(ConversationGrid)`
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  width: 100%;
  overflow-y: auto;
  background: ${color.N2};
`;

const EnhancedConversationCard = styled(motion.div)`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: ${color.N1};
  border-bottom: 1px solid ${color.N4};
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: ${color.G1};
  }

  &:active {
    background: ${color.G2};
  }
`;

const ChatItemIcon = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, ${color.B2} 0%, ${color.B3} 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 20px;
    height: 20px;
    color: ${color.B7};
  }
`;

const ChatItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const ChatItemTitle = styled.div`
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${color.N10};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ChatItemMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.8125rem;
  color: ${color.N6};
`;

const MessageCountBadge = styled.div`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: 12px;
  background: ${color.B4};
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
`;

const EnhancedFilterContainer = styled(FilterContainer)`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  background: ${color.N1};
  border-bottom: 1px solid ${color.N4};
  margin: 0;
  border-radius: 0;
  position: sticky;
  top: 0;
  z-index: 10;
`;

const NewChatButton = styled(motion.button)`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  background: ${color.G6};
  color: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;

  &:hover {
    background: ${color.G7};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: 480px) {
    padding: 0.5rem;
    span {
      display: none;
    }
  }
`;

const ToolbarDivider = styled.div`
  width: 1px;
  height: 24px;
  background: ${color.N4};
  margin: 0 0.25rem;
  flex-shrink: 0;
`;

const EmptyStateContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
  flex: 1;
  background: ${color.N2};
`;

const EmptyStateIcon = styled.div`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, ${color.G1} 0%, ${color.G2} 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;

  svg {
    width: 36px;
    height: 36px;
    color: ${color.G6};
  }
`;

const EmptyStateTitle = styled.h3`
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
  color: ${color.N10};
  letter-spacing: -0.025em;
`;

const EmptyStateDescription = styled.p`
  color: ${color.N7};
  max-width: 360px;
  margin: 0 0 1.5rem;
  font-size: 0.9375rem;
  line-height: 1.5;
`;

const EmptyStateButton = styled(motion.button)`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  background: ${color.G6};
  color: white;
  font-size: 0.9375rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: ${color.G7};
    transform: translateY(-1px);
  }

  svg {
    width: 18px;
    height: 18px;
  }
`;

// Update the ChatContainer styled component
const ChatContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background: #f8fafc;
  position: relative;
  margin: 0;
  padding: 0;
  border-radius: 0;
  flex: 1;
  min-height: 0; /* Important for flex children */
  max-height: 100%; /* Never exceed parent's height */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    /* Removed position: fixed to prevent covering parent navigation and bottom nav */
    /* Container now works as a normal flex child */
    height: 100%; /* Fill parent container */
    max-height: 100%; /* Don't exceed parent's height */
  }
`;

const ConversationIndicator = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  position: relative;
  min-height: 0; /* Important for flex children to properly overflow */
  flex: 1;
  max-height: 100%; /* Never exceed parent's height */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    height: 100%; /* Fill parent container */
    max-height: 100%; /* Don't exceed parent's height */
  }
`;

// Add a styled component for the input wrapper
const ChatInputWrapper = styled.div`
  flex-shrink: 0;
  width: 100%;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.04);
  position: sticky;
  bottom: 0;
  z-index: 50; /* Ensure it's above other content */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: sticky;
    bottom: 0; /* Back to bottom - FAB is now compact and out of the way */
    /* Ensure it stays at bottom even when keyboard appears */
    transform: translateZ(0); /* Force GPU acceleration */
  }
`;

// Add new styled component for processing indicator
const ProcessingIndicator = styled(motion.div)`
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.5rem;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f2ff 100%);
  color: #4a90e2;
  border-radius: 24px;
  font-weight: 500;
  font-size: 0.9375rem;
  position: relative;
  overflow: hidden;
  border: 1px solid #d4e3f4;
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.15);

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(74, 144, 226, 0.15) 50%,
      transparent 100%
    );
    animation: shimmer 2s infinite;
  }

  @keyframes shimmer {
    0% {
      left: -100%;
    }
    100% {
      left: 100%;
    }
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    background: #4a90e2;
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
    box-shadow: 0 0 4px rgba(74, 144, 226, 0.4);
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(1);
      opacity: 0.8;
    }
    50% {
      transform: scale(1.5);
      opacity: 0.4;
    }
  }

  /* Loader color override */
  .ui.loader {
    &:after {
      border-color: #4a90e2 transparent transparent !important;
    }
  }
`;

// Enhance the ChatInputContainer for better mobile experience
const EnhancedChatInputContainer = styled(ChatInputContainer)<{
  $disabled?: boolean;
}>`
  padding: 1.25rem 1.5rem;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.04);
  flex-direction: column;
  align-items: stretch;

  /* When disabled (i.e. assistant is processing) */
  ${(props) =>
    props.$disabled &&
    `
      opacity: 0.6;        /* Visually indicate inactive state */
    `}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
    gap: 0.75rem;
  }
`;

// Enhance the chat messages area for mobile
const MessagesArea = styled.div<{ $isProcessing?: boolean }>`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 1.5rem;
  background: linear-gradient(to bottom, #f8fafc 0%, #ffffff 100%);
  min-height: 0;
  max-height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  transition: background 0.3s ease;

  ${(props) =>
    props.$isProcessing &&
    `
    background: linear-gradient(to bottom, #f0f7ff 0%, #f8fbff 100%);
    animation: subtleGlow 2s ease-in-out infinite;
    
    @keyframes subtleGlow {
      0%, 100% {
        background: linear-gradient(to bottom, #f0f7ff 0%, #f8fbff 100%);
      }
      50% {
        background: linear-gradient(to bottom, #e6f2ff 0%, #f0f7ff 100%);
      }
    }
  `}

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;

    &:hover {
      background: #94a3b8;
    }
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

// Input row wrapper to keep input and send button together
const InputRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.875rem;
  width: 100%;
`;

// Enhance the chat input for better mobile experience
const EnhancedChatInput = styled(ChatInput)`
  background: #f8fafc;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.875rem 1.25rem;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  flex: 1;
  min-height: 48px;

  &:focus {
    background: white;
    border-color: #4299e1;
    box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.875rem;
    padding: 0.75rem 1rem;
    min-height: 44px;
  }
`;

// Enhanced send button that matches input height
const EnhancedSendButton = styled(SendButton)`
  width: 48px;
  height: 48px;
  align-self: center; /* Override the flex-end from base component */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 44px;
    height: 44px;
  }
`;

// Add a new styled component for latest message indicator
const LatestMessageIndicator = styled(motion.div)`
  position: absolute;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(to bottom, #4299e1, #3182ce);
  border-radius: 0 4px 4px 0;
`;

// Add a pulsing dot for new messages
const NewMessageDot = styled(motion.div)`
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 12px;
  height: 12px;
  background: #ef4444;
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.2);

  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: #ef4444;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.5);
      opacity: 0.3;
    }
    100% {
      transform: scale(1);
      opacity: 1;
    }
  }
`;

// Add message wrapper for better styling
const MessageWrapper = styled(motion.div)<{ isLatest?: boolean }>`
  position: relative;
  margin-bottom: 1.5rem;

  ${(props) =>
    props.isLatest &&
    `
    & > * {
      box-shadow: 0 4px 12px rgba(66, 153, 225, 0.15);
      border: 1px solid rgba(66, 153, 225, 0.2);
    }
  `}
`;

// Mobile navigation header styled components
const ChatNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 100; /* High z-index to ensure it's always visible */
  flex-shrink: 0; /* Prevent compression */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: -webkit-sticky; /* For Safari */
    position: sticky;
    padding: 0.75rem 1rem;
  }
`;

const BackButton = styled(motion.button)`
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    background: #e2e8f0;
  }
`;

const NavigationTitle = styled.span`
  flex: 1;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1a202c;
`;

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
}) => {
  // Window dimensions for responsive layout
  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

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

  // For dynamic display of filters
  const [showSearch, setShowSearch] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLDivElement>(null);

  // Approval gate state (mirrors ChatTray)
  const [pendingApproval, setPendingApproval] = useState<{
    messageId: string;
    toolCall: {
      name: string;
      arguments: any;
      tool_call_id?: string;
    };
  } | null>(null);
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

  // Hide search or date picker if user clicks outside
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
                    subArgs && typeof subArgs === "object" ? subArgs : {};
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
    if (data?.tool_name && data?.args) entryType = "tool_call";
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
            <motion.div
              key="conversation-menu"
              style={{
                width: "100%",
                height: "100%",
                maxHeight: "100%",
                display: "flex",
                flexDirection: "column",
                overflowY: "auto",
                flex: 1,
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
            >
              <EnhancedFilterContainer>
                <NewChatButton
                  onClick={startNewChat}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Plus size={16} />
                  <span>New Chat</span>
                </NewChatButton>

                <ToolbarDivider />

                <AnimatePresence>
                  {showSearch && (
                    <ExpandingInput
                      initial={{ width: 0, opacity: 0 }}
                      animate={{ width: "auto", opacity: 1 }}
                      exit={{ width: 0, opacity: 0 }}
                      ref={searchInputRef}
                    >
                      <input
                        className="expanded"
                        placeholder="Search chats..."
                        value={titleFilter}
                        onChange={(e) => setTitleFilter(e.target.value)}
                        autoFocus
                      />
                    </ExpandingInput>
                  )}
                </AnimatePresence>

                <IconButton
                  onClick={() => setShowSearch(!showSearch)}
                  $isActive={!!titleFilter}
                  whileTap={{ scale: 0.95 }}
                  title="Search"
                >
                  <Search />
                </IconButton>

                <IconButton
                  onClick={() => setShowDatePicker(!showDatePicker)}
                  $isActive={!!(createdAtGte || createdAtLte)}
                  whileTap={{ scale: 0.95 }}
                  title="Filter by date"
                >
                  <Calendar />
                </IconButton>

                <AnimatePresence>
                  {showDatePicker && (
                    <DatePickerExpanded
                      ref={datePickerRef}
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                    >
                      <input
                        type="date"
                        value={createdAtGte}
                        onChange={(e) => setCreatedAtGte(e.target.value)}
                        placeholder="Start Date"
                      />
                      <input
                        type="date"
                        value={createdAtLte}
                        onChange={(e) => setCreatedAtLte(e.target.value)}
                        placeholder="End Date"
                      />
                    </DatePickerExpanded>
                  )}
                </AnimatePresence>

                {(titleFilter || createdAtGte || createdAtLte) && (
                  <IconButton
                    onClick={() => {
                      setTitleFilter("");
                      setCreatedAtGte("");
                      setCreatedAtLte("");
                      setShowSearch(false);
                      setShowDatePicker(false);
                    }}
                    whileTap={{ scale: 0.95 }}
                  >
                    <X />
                  </IconButton>
                )}
              </EnhancedFilterContainer>

              {conversations.length > 0 ? (
                <EnhancedConversationGrid id="conversation-grid">
                  {conversations.map((conv, index) => {
                    if (!conv) return null;
                    const messageCount = conv.chatMessages?.totalCount || 0;
                    return (
                      <EnhancedConversationCard
                        key={conv.id}
                        onClick={() => loadConversation(conv.id)}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{
                          duration: 0.2,
                          delay: index * 0.03,
                        }}
                      >
                        <ChatItemIcon>
                          <MessageCircle />
                        </ChatItemIcon>
                        <ChatItemContent>
                          <ChatItemTitle>
                            {conv.title || "Untitled Chat"}
                          </ChatItemTitle>
                          <ChatItemMeta>
                            <span>
                              {formatDistanceToNow(new Date(conv.createdAt))}{" "}
                              ago
                            </span>
                            {conv.creator?.email && (
                              <>
                                <span>·</span>
                                <span>{conv.creator.email}</span>
                              </>
                            )}
                          </ChatItemMeta>
                        </ChatItemContent>
                        {messageCount > 0 && (
                          <MessageCountBadge>{messageCount}</MessageCountBadge>
                        )}
                      </EnhancedConversationCard>
                    );
                  })}
                  <FetchMoreOnVisible
                    fetchNextPage={handleFetchMoreConversations}
                  />
                </EnhancedConversationGrid>
              ) : (
                <EmptyStateContainer>
                  <EmptyStateIcon>
                    <MessageCircle />
                  </EmptyStateIcon>
                  <EmptyStateTitle>No chats yet</EmptyStateTitle>
                  <EmptyStateDescription>
                    Start a conversation with the AI to ask questions about this
                    corpus.
                  </EmptyStateDescription>
                  <EmptyStateButton
                    onClick={startNewChat}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Plus size={18} />
                    Start New Chat
                  </EmptyStateButton>
                </EmptyStateContainer>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </ConversationIndicator>

      {/* Approval Overlay */}
      <AnimatePresence>
        {(() => {
          if (!pendingApproval || !showApprovalModal) return null;
          return (
            <motion.div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: "rgba(0, 0, 0, 0.5)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
                padding: "1rem",
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <motion.div
                style={{
                  backgroundColor: "white",
                  borderRadius: "12px",
                  padding: "2rem",
                  maxWidth: "500px",
                  width: "100%",
                  boxShadow:
                    "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
                }}
                initial={{ scale: 0.9, y: 20 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.9, y: 20 }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    marginBottom: "1.5rem",
                  }}
                >
                  <AlertCircle size={24} style={{ color: "#f59e0b" }} />
                  <h3
                    style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}
                  >
                    Tool Approval Required
                  </h3>
                  <button
                    style={{
                      marginLeft: "auto",
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                    }}
                    onClick={() => setShowApprovalModal(false)}
                  >
                    <X size={20} />
                  </button>
                </div>

                <div style={{ marginBottom: "1.5rem" }}>
                  <p style={{ margin: "0 0 1rem 0", color: "#374151" }}>
                    The assistant wants to execute the following tool:
                  </p>
                  <div
                    style={{
                      backgroundColor: "#f3f4f6",
                      padding: "1rem",
                      borderRadius: "8px",
                      fontFamily: "monospace",
                      fontSize: "0.875rem",
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                      Tool: {pendingApproval.toolCall.name}
                    </div>
                    {Object.keys(pendingApproval.toolCall.arguments).length >
                      0 && (
                      <div>
                        <div
                          style={{ fontWeight: 600, marginBottom: "0.25rem" }}
                        >
                          Arguments:
                        </div>
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                          {JSON.stringify(
                            pendingApproval.toolCall.arguments,
                            null,
                            2
                          )}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: "1rem",
                    justifyContent: "flex-end",
                  }}
                >
                  <Button
                    size="medium"
                    onClick={() => sendApprovalDecision(false)}
                    style={{
                      backgroundColor: "#dc2626",
                      color: "white",
                      border: "none",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <X size={16} />
                    Reject
                  </Button>
                  <Button
                    size="medium"
                    onClick={() => sendApprovalDecision(true)}
                    style={{
                      backgroundColor: "#059669",
                      color: "white",
                      border: "none",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <CheckCircle size={16} />
                    Approve
                  </Button>
                </div>
              </motion.div>
            </motion.div>
          );
        })()}
      </AnimatePresence>
    </ChatContainer>
  );
};
