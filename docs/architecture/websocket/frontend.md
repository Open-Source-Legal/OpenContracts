# Frontend WebSocket Implementation

**Last Updated:** 2026-01-09

## Overview

The frontend WebSocket implementation consists of React components and hooks that handle real-time interactions:

| Component/Hook | Purpose | Location |
|----------------|---------|----------|
| **ChatTray** | Document-specific conversations (in right sidebar) | `frontend/src/components/knowledge_base/document/right_tray/ChatTray.tsx` |
| **CorpusChat** | Corpus-wide conversations (full-screen interface) | `frontend/src/components/corpuses/CorpusChat.tsx` |
| **Thread Components** | Discussion thread UI components | `frontend/src/components/threads/` |

All components share similar patterns for WebSocket communication, state management, and UI rendering.

## Architecture

### Core Technologies

- **React Hooks**: State management and lifecycle handling
- **WebSocket API**: Native browser WebSocket implementation
- **Framer Motion**: Animations and transitions
- **Jotai**: Global state management for chat sources
- **Apollo Client**: GraphQL integration for conversation history

### Common State Pattern

Both components manage multiple layers of state:

```typescript
// WebSocket connection state
const [wsReady, setWsReady] = useState(false);
const [wsError, setWsError] = useState<string | null>(null);

// Chat message state
const [chat, setChat] = useState<ChatMessageProps[]>([]);
const [serverMessages, setServerMessages] = useState<ChatMessageProps[]>([]);

// UI state
const [isNewChat, setIsNewChat] = useState(false);
const [selectedConversationId, setSelectedConversationId] = useState<string>();

// Processing state
const [isProcessing, setIsProcessing] = useState(false);

// Approval workflow state
const [pendingApproval, setPendingApproval] = useState<ApprovalState | null>(null);
const [showApprovalModal, setShowApprovalModal] = useState(false);
```

## ChatTray Component

**Location:** `frontend/src/components/knowledge_base/document/right_tray/ChatTray.tsx`

### Key Features

1. **Sidebar Integration**: Appears in document viewer right panel
2. **Conversation History**: Lists previous conversations with filtering
3. **Source Pinning**: Integrates with document annotation system
4. **Approval Workflow**: Handles tool execution approvals
5. **Mobile Responsive**: Adapts layout for mobile screens

### WebSocket Connection Management

```typescript
useEffect(() => {
  // Connection depends on auth, document, conversation, and chat mode
  if (!selectedConversationId && !isNewChat) {
    // Close socket when no active conversation
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    setWsReady(false);
    return;
  }

  // Build WebSocket URL with context
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
  };

  newSocket.onmessage = (event) => {
    const messageData: MessageData = JSON.parse(event.data);
    // Message processing logic...
  };

  // Cleanup on dependencies change
  return () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  };
}, [auth_token, documentId, selectedConversationId, isNewChat]);
```

### Message Processing Pipeline

The `onmessage` handler routes events to specialized functions:

```typescript
switch (msgType) {
  case "ASYNC_START":
    appendStreamingTokenToChat(content, data?.message_id);
    break;

  case "ASYNC_CONTENT":
    appendStreamingTokenToChat(content, data?.message_id);
    break;

  case "ASYNC_THOUGHT":
    appendThoughtToMessage(content, data);
    break;

  case "ASYNC_SOURCES":
    mergeSourcesIntoMessage(data?.sources, data?.message_id);
    break;

  case "ASYNC_APPROVAL_NEEDED":
    setPendingApproval({
      messageId: data.message_id,
      toolCall: data.pending_tool_call,
    });
    setShowApprovalModal(true);
    break;

  case "ASYNC_FINISH":
    finalizeStreamingResponse(
      content,
      data?.sources,
      data?.message_id,
      data?.timeline
    );
    break;

  case "ASYNC_ERROR":
    setWsError(data?.error || "Agent error");
    finalizeStreamingResponse(
      data?.error || "An unknown error occurred.",
      [],
      data?.message_id
    );
    break;
}
```

### Streaming Content Management

#### Token Appending

```typescript
function appendStreamingTokenToChat(
  token: string,
  overrideMessageId?: string
): string {
  if (!token) return "";

  let messageId = "";
  setChat((prev) => {
    const lastMessage = prev[prev.length - 1];

    // Append to existing assistant message
    if (lastMessage && lastMessage.isAssistant) {
      messageId = lastMessage.messageId || "";
      const updatedLast = {
        ...lastMessage,
        content: lastMessage.content + token,
        isComplete: false,
      };
      return [...prev.slice(0, -1), updatedLast];
    } else {
      // Create new assistant message
      messageId = overrideMessageId || `msg_${Date.now()}_${Math.random().toString(36).substr(2)}`;
      return [
        ...prev,
        {
          messageId,
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

  return messageId;
}
```

#### Response Finalization

```typescript
const finalizeStreamingResponse = (
  content: string,
  sourcesData?: WebSocketSources[],
  overrideId?: string,
  timelineData?: TimelineEntry[]
): void => {
  setChat((prev) => {
    if (!prev.length) return prev;

    // Find message to update
    let updateIdx = prev.findIndex((m) => m.messageId === overrideId);
    if (updateIdx === -1) {
      // Fallback to last assistant message
      const lastIdxRev = [...prev].reverse().findIndex((m) => m.isAssistant);
      if (lastIdxRev === -1) return prev;
      updateIdx = prev.length - 1 - lastIdxRev;
    }

    const updatedMessages = [...prev];
    const assistantMsg = updatedMessages[updateIdx];

    updatedMessages[updateIdx] = {
      ...assistantMsg,
      content,
      isComplete: true,
    };

    return updatedMessages;
  });

  // Store in sources atom for citation functionality
  handleCompleteMessage(content, sourcesData, overrideId, undefined, timelineData);
};
```

### Source State Integration

ChatTray integrates with the global source state for document citations:

```typescript
const {
  messages: sourcedMessages,
  selectedMessageId,
  setChatSourceState,
} = useChatSourceState();

// Store message sources for citation functionality
const handleCompleteMessage = (
  content: string,
  sourcesData?: Array<WebSocketSources>,
  overrideId?: string,
  overrideCreatedAt?: string,
  timelineData?: TimelineEntry[]
): void => {
  const messageId = overrideId ?? `msg_${Date.now()}`;
  const mappedSources = mapWebSocketSourcesToChatMessageSources(sourcesData, messageId);

  setChatSourceState((prev) => {
    const existingIndex = prev.messages.findIndex((m) => m.messageId === messageId);

    if (existingIndex !== -1) {
      // Update existing message
      const updatedMessages = [...prev.messages];
      updatedMessages[existingIndex] = {
        ...updatedMessages[existingIndex],
        content,
        sources: mappedSources.length ? mappedSources : updatedMessages[existingIndex].sources,
      };
      return { ...prev, messages: updatedMessages };
    } else {
      // Add new message
      return {
        ...prev,
        messages: [
          ...prev.messages,
          { messageId, content, timestamp: new Date().toISOString(), sources: mappedSources },
        ],
      };
    }
  });
};
```

### Approval Workflow

The approval system allows users to authorize tool execution:

```typescript
// Approval modal component
const ApprovalOverlay = () => {
  if (!pendingApproval || !showApprovalModal) return null;

  return (
    <motion.div style={{ /* modal styles */ }}>
      <motion.div style={{ /* content styles */ }}>
        <h3>Tool Approval Required</h3>
        <p>The assistant wants to execute the following tool:</p>

        <div style={{ /* tool display styles */ }}>
          <div>Tool: {pendingApproval.toolCall.name}</div>
          <pre>{JSON.stringify(pendingApproval.toolCall.arguments, null, 2)}</pre>
        </div>

        <div>
          <Button onClick={() => sendApprovalDecision(false)}>Reject</Button>
          <Button onClick={() => sendApprovalDecision(true)}>Approve</Button>
        </div>
      </motion.div>
    </motion.div>
  );
};

// Send approval decision
const sendApprovalDecision = useCallback((approved: boolean): void => {
  if (!pendingApproval || !socketRef.current || !wsReady) return;

  try {
    const messageData = {
      approval_decision: approved,
      llm_message_id: pendingApproval.messageId,
    };

    socketRef.current.send(JSON.stringify(messageData));
    setShowApprovalModal(false);
    updateMessageApprovalStatus(
      pendingApproval.messageId,
      approved ? "approved" : "rejected"
    );
    setPendingApproval(null);
  } catch (err) {
    console.error("Failed to send approval decision:", err);
    setWsError("Failed to send approval decision. Please try again.");
  }
}, [pendingApproval, wsReady]);
```

## CorpusChat Component

**Location:** `frontend/src/components/corpuses/CorpusChat.tsx`

### Key Features

1. **Full-Screen Interface**: Dedicated corpus conversation view
2. **Enhanced UI**: More sophisticated styling and animations
3. **Mobile-First**: Responsive design with mobile navigation
4. **Processing Indicators**: Visual feedback during LLM generation
5. **Conversation Management**: Create and load corpus conversations

### Enhanced State Management

CorpusChat includes additional state for better UX:

```typescript
// Processing state for visual feedback
const [isProcessing, setIsProcessing] = useState<boolean>(false);

// Enhanced conversation filtering
const [titleFilter, setTitleFilter] = useState<string>("");
const [debouncedTitle, setDebouncedTitle] = useState<string>("");
const [createdAtGte, setCreatedAtGte] = useState<string>("");
const [createdAtLte, setCreatedAtLte] = useState<string>("");

// UI state for responsive behavior
const { width } = useWindowDimensions();
const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;
```

### Processing State Management

CorpusChat provides enhanced visual feedback during processing:

```typescript
// Message processing with visual state updates
switch (msgType) {
  case "ASYNC_START":
    setIsProcessing(true);
    appendStreamingTokenToChat(content, data?.message_id);
    break;

  case "ASYNC_FINISH":
    finalizeStreamingResponse(content, data?.sources, data?.message_id, data?.timeline);
    setIsProcessing(false);
    break;

  case "ASYNC_ERROR":
    setWsError(data?.error || "Agent error");
    finalizeStreamingResponse(data?.error || "Error", [], data?.message_id);
    setIsProcessing(false);
    break;
}
```

### Enhanced UI Components

CorpusChat uses styled-components for sophisticated styling:

```typescript
// Processing indicator with animations
const ProcessingIndicator = styled(motion.div)`
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.5rem;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f2ff 100%);
  color: #4a90e2;
  border-radius: 24px;

  &::before {
    content: "";
    position: absolute;
    animation: shimmer 2s infinite;
  }

  .pulse-dot {
    animation: pulse 1.5s ease-in-out infinite;
  }
`;

// Enhanced input container with processing state
const EnhancedChatInputContainer = styled(ChatInputContainer)<{
  $disabled?: boolean;
}>`
  ${(props) =>
    props.$disabled &&
    `opacity: 0.6;`}
`;
```

### Mobile Navigation

CorpusChat includes dedicated mobile navigation:

```typescript
{use_mobile_layout && isConversation && (
  <ChatNavigationHeader>
    <BackButton
      onClick={() => {
        if (selectedConversationId || !isNewChat) {
          // Go back to conversation list
          setSelectedConversationId(undefined);
          setIsNewChat(false);
        } else {
          // Go back to corpus home
          showQueryViewState("ASK");
        }
      }}
    >
      <ArrowLeft size={20} />
    </BackButton>
    <NavigationTitle>
      {selectedConversationId ? "Conversation" : "New Chat"}
    </NavigationTitle>
    <IconButton onClick={() => showQueryViewState("ASK")}>
      <Home size={20} />
    </IconButton>
  </ChatNavigationHeader>
)}
```

## Shared Utilities

### WebSocket URL Generation

Both components use utility functions to generate WebSocket URLs:

```typescript
// Document chat URL
const wsUrl = getWebSocketUrl(
  documentId,
  auth_token || undefined,
  selectedConversationId,
  corpusId
);

// Corpus chat URL
const wsUrl = getCorpusQueryWebSocket(
  corpusId,
  auth_token,
  isNewChat ? undefined : selectedConversationId
);
```

### Message Type Definitions

Shared TypeScript interfaces ensure type safety:

```typescript
interface MessageData {
  type:
    | "ASYNC_START"
    | "ASYNC_CONTENT"
    | "ASYNC_FINISH"
    | "SYNC_CONTENT"
    | "ASYNC_THOUGHT"
    | "ASYNC_SOURCES"
    | "ASYNC_APPROVAL_NEEDED"
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

interface WebSocketSources {
  page: number;
  json: { start: number; end: number } | MultipageAnnotationJson;
  annotation_id: number;
  label: string;
  label_id: number;
  rawText: string;
}
```

## State Persistence

### Conversation Persistence

ChatTray persists conversation state using UI settings:

```typescript
const { chatTrayState, setChatTrayState } = useUISettings();

// Restore conversation on component mount
useEffect(() => {
  if (chatTrayState.conversationId) {
    loadConversation(chatTrayState.conversationId);
    setShowLoad(false);
  } else if (chatTrayState.isNewChat) {
    startNewChat();
  }
}, []);

// Keep state in sync
useEffect(() => {
  setChatTrayState((prev) => ({
    ...prev,
    conversationId: selectedConversationId ?? null,
    isNewChat,
  }));
}, [selectedConversationId, isNewChat, setChatTrayState]);
```

### Scroll Position Persistence

ChatTray remembers scroll position across navigation:

```typescript
// Save scroll position during scrolling
const handlePersistedScroll = useCallback(() => {
  const container = messagesContainerRef.current;
  if (!container) return;

  const offset = container.scrollTop;
  setChatTrayState((prev) => ({ ...prev, scrollOffset: offset }));

  // Update auto-scroll behavior
  const distanceFromBottom = container.scrollHeight - offset - container.clientHeight;
  autoScrollRef.current = distanceFromBottom < 100;
}, [setChatTrayState]);

// Restore scroll position after messages load
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
    initialRestoreDone.current = true;
  }
}, [combinedMessages, chatTrayState.conversationId, chatTrayState.scrollOffset, selectedConversationId]);
```

## Performance Optimizations

### Message Deduplication

Both components handle duplicate messages from server and local state:

```typescript
const combinedMessages = useMemo(() => {
  const messages = [...serverMessages, ...chat];

  // Remove duplicates by messageId, preferring most recent version
  const messageMap = new Map<string, ChatMessageProps>();
  const messagesWithoutId: ChatMessageProps[] = [];

  messages.forEach((msg) => {
    if (msg.messageId) {
      messageMap.set(msg.messageId, msg);
    } else {
      messagesWithoutId.push(msg);
    }
  });

  // Sort by timestamp to maintain chronological order
  const allMessages = [...messagesWithoutId, ...Array.from(messageMap.values())];
  return allMessages.sort((a, b) => {
    const timeA = new Date(a.timestamp).getTime();
    const timeB = new Date(b.timestamp).getTime();
    return timeA - timeB;
  });
}, [serverMessages, chat, pendingApproval]);
```

### Optimized Rendering

Components use React.memo and useMemo for expensive operations:

```typescript
// Memoized conversation list
const conversations = useMemo(() => {
  return data?.conversations?.edges?.map((edge) => edge?.node) || [];
}, [data]);

// Memoized source mapping
const sources = sourcedMessage?.sources.map((source, index) => ({
  text: source.rawText || `Source ${index + 1}`,
  onClick: () => {
    setChatSourceState((prev) => ({
      ...prev,
      selectedMessageId: sourcedMessage.messageId,
      selectedSourceIndex: index,
    }));
  },
})) || [];
```

### Debounced Search

Search inputs use debouncing to reduce API calls:

```typescript
// Debounce the title filter input
useEffect(() => {
  const timer = setTimeout(() => {
    setDebouncedTitle(titleFilter);
  }, 500);

  return () => clearTimeout(timer);
}, [titleFilter]);
```

## Error Handling

### Connection Errors

Both components handle WebSocket connection failures gracefully:

```typescript
newSocket.onerror = (event) => {
  setWsReady(false);
  setWsError("Error connecting to the websocket.");
  console.error("WebSocket error:", event);
};

newSocket.onclose = (event) => {
  setWsReady(false);
  console.warn("WebSocket closed:", event);
};
```

### Message Processing Errors

Errors during message processing are caught and displayed:

```typescript
try {
  const messageData: MessageData = JSON.parse(event.data);
  // Process message...
} catch (err) {
  console.error("Failed to parse WS message:", err);
  setWsError("Failed to parse message from server.");
}
```

### User-Friendly Error Display

Error states are presented with recovery options:

```typescript
{wsError ? (
  <ErrorMessage>
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
    >
      {wsError}
      <Button
        onClick={() => window.location.reload()}
        style={{
          marginLeft: "0.75rem",
          background: "#dc3545",
          color: "white",
        }}
      >
        Reconnect
      </Button>
    </motion.div>
  </ErrorMessage>
) : (
  <ConnectionStatus connected={wsReady} />
)}
```

## Testing Strategies

### Component Testing

Use React Testing Library for component behavior:

```typescript
test('sends message when form is submitted', async () => {
  const mockSocket = { send: jest.fn(), close: jest.fn() };

  render(<ChatTray documentId="123" showLoad={false} setShowLoad={() => {}} />);

  // Mock WebSocket connection
  jest.spyOn(window, 'WebSocket').mockImplementation(() => mockSocket);

  // Simulate user input and submission
  const input = screen.getByTestId('chat-input');
  const sendButton = screen.getByRole('button', { name: /send/i });

  fireEvent.change(input, { target: { value: 'test message' } });
  fireEvent.click(sendButton);

  expect(mockSocket.send).toHaveBeenCalledWith(
    JSON.stringify({ query: 'test message' })
  );
});
```

### WebSocket Integration Testing

Mock WebSocket for integration tests:

```typescript
test('handles streaming response correctly', async () => {
  const component = render(<ChatTray {...props} />);

  // Simulate WebSocket messages
  const mockSocket = getMockWebSocket();

  // Send ASYNC_START
  mockSocket.simulateMessage({
    type: 'ASYNC_START',
    content: '',
    data: { message_id: 'msg_123' }
  });

  // Send ASYNC_CONTENT
  mockSocket.simulateMessage({
    type: 'ASYNC_CONTENT',
    content: 'Hello',
    data: { message_id: 'msg_123' }
  });

  // Verify UI updates
  expect(screen.getByText('Hello')).toBeInTheDocument();
});
```

## Thread Conversation UI Patterns

### Thread UI Components

**Location:** [`frontend/src/components/threads/`](../../../frontend/src/components/threads/)

The thread system provides a rich discussion interface with the following key components:

| Component | Purpose |
|-----------|---------|
| `ThreadList.tsx` | Lists all threads for a context |
| `ThreadDetail.tsx` | Full thread view with messages |
| `ThreadListItem.tsx` | Individual thread in list |
| `MessageTree.tsx` | Nested message display |
| `MessageItem.tsx` | Individual message with actions |
| `MessageComposer.tsx` | Rich text input with mentions |
| `ReplyForm.tsx` | Reply input for messages |
| `CreateThreadForm.tsx` | New thread creation |
| `MentionPicker.tsx` | User @mention autocomplete |
| `UnifiedMentionPicker.tsx` | Combined user/agent mentions |
| `VoteButtons.tsx` | Upvote/downvote controls |
| `ModerationControls.tsx` | Admin moderation actions |

#### Thread Features

- **Nested Replies**: Full message tree with reply threading
- **@Mentions**: Mention users and agents (triggers agent responses)
- **Voting**: Stack Overflow-style voting on messages
- **Moderation**: Lock threads, delete messages, accept answers
- **Badges**: User reputation and achievement display
- **Real-time Updates**: Not yet wired up (see Issues #623, #697)
- **Markdown Support**: Full markdown rendering in messages

### WebSocket URL Utilities

**Source:** [`frontend/src/components/chat/get_websockets.ts`](../../../frontend/src/components/chat/get_websockets.ts)

Provides URL generation functions for all WebSocket endpoints:

```typescript
// Document chat WebSocket (with corpus context)
getWebSocketUrl(documentId, authToken, conversationId?, corpusId?)

// Corpus chat WebSocket
getCorpusQueryWebSocket(corpusId, authToken, conversationId?)

// Thread updates WebSocket
getThreadUpdatesWebSocket(conversationId, authToken?)
```

---

## Related Files

- [`frontend/src/components/widgets/chat/ChatMessage.tsx`](../../../frontend/src/components/widgets/chat/ChatMessage.tsx): Message rendering component
- [`frontend/src/components/annotator/context/ChatSourceAtom.ts`](../../../frontend/src/components/annotator/context/ChatSourceAtom.ts): Source state management
- [`frontend/src/components/chat/get_websockets.ts`](../../../frontend/src/components/chat/get_websockets.ts): WebSocket URL utilities
- [`frontend/src/graphql/queries.ts`](../../../frontend/src/graphql/queries.ts): GraphQL conversation queries
- [`frontend/src/hooks/useNetworkStatus.ts`](../../../frontend/src/hooks/useNetworkStatus.ts): Network/visibility status for reconnection
