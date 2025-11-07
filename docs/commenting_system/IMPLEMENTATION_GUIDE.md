# Frontend Implementation Guide: Commenting & Discussion System

## Table of Contents

### Foundation (Issues #573-577 - Completed)
1. [Architecture Overview](#architecture-overview)
2. [State Management Strategy](#state-management-strategy)
3. [Component Specifications](#component-specifications) - Components for #573-577
4. [Data Flow Patterns](#data-flow-patterns)
5. [Testing Strategy](#testing-strategy)

### Implementation History
6. [Implementation Checklist](#implementation-checklist) - Completed issues #573-577
7. [Pending Issues: Roadmap to Full Integration](#pending-issues-roadmap-to-full-integration) - Issues #578-580, #621-623
8. [Branch Dependency Tree](#branch-dependency-tree)

### Integration Work (Issues #621-623)
9. [Integration with Existing Views](#integration-with-existing-views) - Detailed specs for #621-623
   - [Routing Architecture](#routing-architecture)
   - [Corpus View Integration](#corpus-view-integration) - Issue #621
   - [DocumentKnowledgeBase Integration](#documentknowledgebase-integration) - Issue #622
   - [Global Discussions View](#global-discussions-view) - Issue #623
   - [@ Mentions Feature](#-mentions-feature) - Issue #623
   - [Conversation Type Flexibility](#conversation-type-flexibility)
   - [Implementation Checklist](#implementation-checklist-1) - Phases mapped to issues

### Reference Material
10. [Code Examples & Patterns](#code-examples--patterns)
11. [Performance Considerations](#performance-considerations)
12. [Accessibility Requirements](#accessibility-requirements)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                        │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Corpus   │  │   Document   │  │  Global Forum     │  │
│  │   Detail   │  │   Viewer     │  │  View (/forum)    │  │
│  └──────┬─────┘  └──────┬───────┘  └─────────┬─────────┘  │
│         │                │                     │             │
│         └────────────────┴─────────────────────┘             │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│              Thread Components Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  ThreadList  │  │ ThreadDetail │  │  ThreadSearch    │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬────────┘  │
│         │                  │                     │            │
│         │                  │                     │            │
│  ┌──────▼──────────────────▼─────────────────────▼────────┐ │
│  │          Shared Thread Components                       │ │
│  │  • MessageItem    • VoteButtons   • ModerationControls │ │
│  │  • MessageTree    • ReplyForm     • NotificationBell   │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                   State Management Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Jotai Atoms │  │ Apollo Cache │  │  Local Storage   │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                      Data Layer                               │
│  ┌─────────────────┐  ┌──────────────────────────────────┐  │
│  │  GraphQL API    │  │  Backend Django + GraphQL        │  │
│  │  (mutations &   │  │  (conversation models, signals)  │  │
│  │   queries)      │  │                                  │  │
│  └─────────────────┘  └──────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

### Technology Stack

- **State Management**: Jotai (atomic state)
- **GraphQL Client**: Apollo Client
- **Styling**: styled-components + existing theme system
- **Routing**: React Router
- **Testing**: Playwright Component Tests
- **Rich Text**: TipTap (for message composer)
- **Icons**: Lucide React (consistent with badge system)
- **Date Formatting**: date-fns
- **Markdown**: SafeMarkdown component (existing)

### Core Design Principles

1. **Component Reusability**: Build atomic components that work across corpus/document/global contexts
2. **Progressive Enhancement**: Basic functionality works, then add real-time updates later
3. **Permission-Aware**: All UI respects backend permissions (myPermissions field)
4. **Optimistic Updates**: Immediate UI feedback, rollback on error
5. **Responsive First**: Mobile-friendly from the start
6. **Accessibility**: Keyboard navigation, ARIA labels, screen reader support

---

## State Management Strategy

> **Note**: These atoms were created in **Issue #573** and are used across all integration work. For URL-driven state (like thread selection), see [Integration with Existing Views → Routing Architecture](#routing-architecture) which adds Apollo reactive vars in issues #621-623.

### Jotai Atoms Architecture

**File**: `frontend/src/atoms/threadAtoms.ts` (Created in Issue #573)

```typescript
import { atom } from "jotai";
import { ConversationType, ChatMessageType } from "../types/graphql-api";

// ============================================================================
// THREAD LIST STATE (Issue #573)
// ============================================================================

export type ThreadSortOption = "newest" | "active" | "upvoted" | "pinned";
export type ThreadFilterOptions = {
  showLocked: boolean;
  showDeleted: boolean;  // Only relevant for moderators
};

// Currently selected corpus for thread view
export const selectedCorpusIdAtom = atom<string | null>(null);

// Thread list sort order
export const threadSortAtom = atom<ThreadSortOption>("pinned");

// Thread list filters
export const threadFiltersAtom = atom<ThreadFilterOptions>({
  showLocked: true,
  showDeleted: false,
});

// ============================================================================
// THREAD DETAIL STATE (Issue #573)
// ============================================================================

// Currently viewing thread
export const currentThreadIdAtom = atom<string | null>(null);

// Currently selected message (for deep linking)
export const selectedMessageIdAtom = atom<string | null>(null);

// Message tree expansion state (for collapsible threads)
export const expandedMessageIdsAtom = atom<Set<string>>(new Set());

// ============================================================================
// UI STATE (Issues #573-574)
// ============================================================================

// Show/hide thread creation modal (Issue #574)
export const showCreateThreadModalAtom = atom<boolean>(false);

// Show/hide reply form for specific message (Issue #574)
export const replyingToMessageIdAtom = atom<string | null>(null);

// Editing message (for edit functionality in future)
export const editingMessageIdAtom = atom<string | null>(null);

// ============================================================================
// DERIVED ATOMS
// ============================================================================

/**
 * Computes whether current user can create threads in selected corpus
 * This is a derived atom that reads from corpus permissions
 */
export const canCreateThreadAtom = atom<boolean>((get) => {
  // Implementation will check permissions from Apollo cache
  // For now, placeholder
  return true;
});
```

### Apollo Cache Strategy

**Cache Policies**:
```typescript
// frontend/src/graphql/cache-config.ts

export const typePolicies = {
  ConversationType: {
    fields: {
      allMessages: {
        // Messages are in-memory only, not paginated
        merge: false,
      },
    },
  },

  ChatMessageType: {
    fields: {
      upvoteCount: {
        // Use optimistic updates for vote counts
        merge: (existing, incoming) => incoming,
      },
      downvoteCount: {
        merge: (existing, incoming) => incoming,
      },
    },
  },

  Query: {
    fields: {
      conversations: {
        keyArgs: ["corpusId", "documentId", "conversationType"],
        merge: (existing, incoming, { args }) => {
          if (!existing || !args?.after) {
            return incoming;
          }

          // Merge paginated results
          return {
            ...incoming,
            edges: [...existing.edges, ...incoming.edges],
          };
        },
      },
    },
  },
};
```

### Local Storage for User Preferences

```typescript
// frontend/src/hooks/useThreadPreferences.ts

const THREAD_PREFS_KEY = "opencontracts_thread_preferences";

interface ThreadPreferences {
  defaultSort: ThreadSortOption;
  compactView: boolean;
  showAvatars: boolean;
}

export function useThreadPreferences() {
  const [prefs, setPrefs] = useState<ThreadPreferences>(() => {
    const stored = localStorage.getItem(THREAD_PREFS_KEY);
    return stored
      ? JSON.parse(stored)
      : {
          defaultSort: "pinned",
          compactView: false,
          showAvatars: true,
        };
  });

  const updatePrefs = (updates: Partial<ThreadPreferences>) => {
    const newPrefs = { ...prefs, ...updates };
    setPrefs(newPrefs);
    localStorage.setItem(THREAD_PREFS_KEY, JSON.stringify(newPrefs));
  };

  return { prefs, updatePrefs };
}
```

---

## Component Specifications

> **Note**: This section describes components created in completed issues **#573-577** (Thread List, Message Composer, Voting, Moderation, Notifications). These are the **foundation components** that are reused in the integration work.
>
> For **new components** needed for integration with Corpuses, Documents, and Global views (issues #621-623), see the [Integration with Existing Views](#integration-with-existing-views) section.

### Component Tree Structure

```
Thread List Components:
├── ThreadList.tsx (container)
│   ├── ThreadListHeader.tsx
│   │   ├── ThreadSortDropdown.tsx
│   │   ├── ThreadFilterToggles.tsx
│   │   └── CreateThreadButton.tsx
│   ├── ThreadListItem.tsx (repeated)
│   │   ├── ThreadTitle.tsx
│   │   ├── ThreadMetadata.tsx
│   │   ├── ThreadStats.tsx
│   │   └── ThreadBadges.tsx (locked/pinned indicators)
│   ├── ThreadListEmpty.tsx
│   └── FetchMoreOnVisible.tsx (existing)

Thread Detail Components:
├── ThreadDetail.tsx (container)
│   ├── ThreadDetailHeader.tsx
│   │   ├── ThreadTitle.tsx (editable for creator/mods)
│   │   ├── ThreadMetadata.tsx
│   │   ├── ModerationControls.tsx (#576)
│   │   └── ThreadBreadcrumbs.tsx
│   ├── MessageTree.tsx
│   │   └── MessageItem.tsx (recursive)
│   │       ├── MessageHeader.tsx
│   │       │   ├── UserAvatar.tsx
│   │       │   ├── Username.tsx
│   │       │   └── MessageTimestamp.tsx
│   │       ├── MessageContent.tsx
│   │       │   └── SafeMarkdown.tsx (existing)
│   │       ├── MessageFooter.tsx
│   │       │   ├── VoteButtons.tsx (#575)
│   │       │   ├── ReplyButton.tsx (#574)
│   │       │   └── MessageActions.tsx (edit, delete)
│   │       └── MessageTree.tsx (nested replies)
│   └── ThreadDetailEmpty.tsx

Shared Components:
├── ThreadBadge.tsx (locked/pinned/deleted indicators)
├── UserBadge.tsx (moderator/creator badges)
└── RelativeTime.tsx (time formatting)
```

### Component-to-Issue Mapping

The components above were created across multiple issues. Here's the mapping:

**Issue #573 - Thread List and Detail Views:**
- `ThreadList.tsx`, `ThreadListItem.tsx`, `ThreadBadge.tsx`
- `ThreadDetail.tsx`, `MessageItem.tsx`, `MessageTree.tsx`
- `RelativeTime.tsx`, `utils.ts`, `threadAtoms.ts`

**Issue #574 - Message Composer and Reply UI:**
- `MessageComposer.tsx` (TipTap rich text editor)
- `CreateThreadForm.tsx` (thread creation modal)
- `ReplyForm.tsx` (inline reply component)
- GraphQL mutations: CREATE_THREAD, CREATE_THREAD_MESSAGE, REPLY_TO_MESSAGE

**Issue #575 - Voting UI and Reputation Display:**
- `VoteButtons.tsx` (upvote/downvote with optimistic updates)
- `ReputationBadge.tsx`, `ReputationDisplay.tsx`, `UserProfileReputation.tsx`
- GraphQL mutations: UPVOTE_MESSAGE, DOWNVOTE_MESSAGE, REMOVE_VOTE

**Issue #576 - Moderation UI and Controls:**
- `ModerationControls.tsx` (pin/lock/delete/restore actions)
- `ModeratorBadge.tsx` (visual moderator indicator)
- GraphQL mutations: PIN_THREAD, UNPIN_THREAD, LOCK_THREAD, UNLOCK_THREAD, DELETE_THREAD, RESTORE_THREAD

**Issue #577 - Notification Center UI:**
- `NotificationBell.tsx` (header bell icon with badge)
- `NotificationDropdown.tsx` (quick access dropdown)
- `NotificationItem.tsx` (individual notification display)
- `NotificationCenter.tsx` (full-page notification center)
- GraphQL queries: GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT
- GraphQL mutations: MARK_NOTIFICATION_READ, MARK_ALL_NOTIFICATIONS_READ, DELETE_NOTIFICATION

**Issues #621-623 - Integration Components (To Be Created):**
- `CorpusDiscussionsView.tsx` (Issue #621)
- `DocumentDiscussionsContent.tsx` (Issue #622)
- `GlobalDiscussions.tsx`, `MentionList.tsx`, `MessageContent.tsx` with mentions (Issue #623)

### Detailed Component Specs

#### 1. ThreadList.tsx (Issue #573)

**Purpose**: Container component that fetches and displays list of threads

**Created in**: Issue #573 - Thread List and Detail Views
**Reused in**: Issues #621, #622, #623 - All integration views

**Props**:
```typescript
interface ThreadListProps {
  corpusId?: string;
  documentId?: string;
  conversationType?: ConversationTypeEnum;
  embedded?: boolean;  // When embedded in corpus/document page
}
```

**State**:
- Jotai: `threadSortAtom`, `threadFiltersAtom`
- Apollo: `useQuery(GET_CONVERSATIONS)`

**Behavior**:
- Fetches threads on mount
- Applies sort and filter client-side
- Infinite scroll for pagination
- Refetches on interval (30s) for new threads

**GraphQL**:
```graphql
query GetThreads($corpusId: String, $conversationType: String) {
  conversations(corpusId: $corpusId, conversationType: $conversationType) {
    edges {
      node {
        id
        title
        description
        createdAt
        creator { username }
        chatMessages { totalCount }
        isPinned
        isLocked
        deletedAt
      }
    }
  }
}
```

**Styled Components**:
```typescript
const ThreadListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
  padding: ${spacing.lg};
  max-width: 1200px;
  margin: 0 auto;

  @media (max-width: 640px) {
    padding: ${spacing.sm};
    gap: ${spacing.sm};
  }
`;

const ThreadGrid = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.sm};
`;
```

**Testing**:
- ✅ Renders thread list with mocked data
- ✅ Applies sort correctly (newest, active, upvoted, pinned)
- ✅ Applies filters correctly (showLocked, showDeleted)
- ✅ Handles empty state
- ✅ Handles loading state
- ✅ Handles error state
- ✅ Infinite scroll triggers fetchMore
- ✅ Create thread button shows for users with permission

---

#### 2. ThreadListItem.tsx (Issue #573)

**Purpose**: Individual thread card in list view

**Created in**: Issue #573 - Thread List and Detail Views
**Reused in**: Issues #621, #622, #623 - All integration views

**Props**:
```typescript
interface ThreadListItemProps {
  thread: ConversationType;
  onClick: () => void;
  compact?: boolean;
}
```

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📌 [PINNED] 🔒 [LOCKED]                                     │
│                                                              │
│ Thread Title (bold, 18px)                                   │
│ Description excerpt... (truncated to 2 lines)               │
│                                                              │
│ 👤 username  •  🕒 2 hours ago  •  💬 23 replies  •  ⬆️ 45  │
└─────────────────────────────────────────────────────────────┘
```

**Styled Components**:
```typescript
const ThreadCard = styled.div<{ $isPinned?: boolean }>`
  background: ${color.N2};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  padding: ${spacing.md};
  cursor: pointer;
  transition: all 0.2s;

  ${props => props.$isPinned && `
    border-left: 4px solid ${color.B5};
    background: ${color.B1};
  `}

  &:hover {
    border-color: ${color.B5};
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transform: translateY(-1px);
  }
`;

const ThreadTitle = styled.h3`
  font-size: 18px;
  font-weight: 600;
  color: ${color.N10};
  margin: 0 0 ${spacing.xs} 0;
`;

const ThreadDescription = styled.p`
  font-size: 14px;
  color: ${color.N7};
  margin: 0 0 ${spacing.md} 0;

  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const ThreadMeta = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.md};
  font-size: 13px;
  color: ${color.N6};

  @media (max-width: 640px) {
    flex-wrap: wrap;
    gap: ${spacing.xs};
  }
`;

const BadgeRow = styled.div`
  display: flex;
  gap: ${spacing.xs};
  margin-bottom: ${spacing.sm};
`;
```

**Testing**:
- ✅ Renders thread data correctly
- ✅ Shows pinned badge when isPinned
- ✅ Shows locked badge when isLocked
- ✅ Truncates long descriptions
- ✅ Formats timestamps correctly
- ✅ onClick navigates to thread detail
- ✅ Hover effects work

---

#### 3. ThreadDetail.tsx (Issue #573)

**Purpose**: Full thread view with all messages

**Created in**: Issue #573 - Thread List and Detail Views
**Reused in**: Issues #621, #622, #623 - All integration views

**Props**:
```typescript
interface ThreadDetailProps {
  conversationId: string;
}
```

**State**:
- Apollo: `useQuery(GET_THREAD_DETAIL)`
- Jotai: `selectedMessageIdAtom`, `expandedMessageIdsAtom`

**Behavior**:
- Fetches full thread with all messages
- Builds message tree from flat message list
- Scrolls to selected message if `?message=id` in URL
- Highlights selected message briefly (3s)
- Handles deep linking

**Message Tree Algorithm**:
```typescript
interface MessageNode extends ChatMessageType {
  children: MessageNode[];
  depth: number;
}

function buildMessageTree(
  messages: ChatMessageType[],
  maxDepth: number = 10
): MessageNode[] {
  // Create map of message ID to message with children array
  const messageMap = new Map<string, MessageNode>();

  messages.forEach(msg => {
    messageMap.set(msg.id, {
      ...msg,
      children: [],
      depth: 0,
    });
  });

  // Build tree by linking children to parents
  const rootMessages: MessageNode[] = [];

  messages
    .sort((a, b) => new Date(a.created).getTime() - new Date(b.created).getTime())
    .forEach(msg => {
      const node = messageMap.get(msg.id)!;

      if (msg.parentMessage?.id) {
        const parent = messageMap.get(msg.parentMessage.id);
        if (parent) {
          node.depth = Math.min(parent.depth + 1, maxDepth);
          parent.children.push(node);
        } else {
          // Parent not found, treat as root
          rootMessages.push(node);
        }
      } else {
        rootMessages.push(node);
      }
    });

  return rootMessages;
}
```

**Deep Linking**:
```typescript
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const messageId = params.get("message");

  if (messageId && threadData?.conversation?.allMessages) {
    // Wait for messages to render
    setTimeout(() => {
      const messageEl = document.getElementById(`message-${messageId}`);
      if (messageEl) {
        messageEl.scrollIntoView({ behavior: "smooth", block: "center" });
        setSelectedMessageId(messageId);

        // Remove highlight after 3s
        setTimeout(() => setSelectedMessageId(null), 3000);
      }
    }, 100);
  }
}, [threadData, setSelectedMessageId]);
```

**Styled Components**:
```typescript
const ThreadDetailContainer = styled.div`
  max-width: 1000px;
  margin: 0 auto;
  padding: ${spacing.lg};

  @media (max-width: 640px) {
    padding: ${spacing.sm};
  }
`;

const ThreadHeader = styled.div`
  border-bottom: 1px solid ${color.N4};
  padding-bottom: ${spacing.lg};
  margin-bottom: ${spacing.lg};
`;

const ThreadTitleLarge = styled.h1`
  font-size: 28px;
  font-weight: 700;
  color: ${color.N10};
  margin: 0 0 ${spacing.sm} 0;
`;

const ThreadDescription = styled.p`
  font-size: 16px;
  color: ${color.N7};
  line-height: 1.6;
`;

const MessageListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.sm};
`;
```

**Testing**:
- ✅ Fetches and displays thread detail
- ✅ Builds message tree correctly
- ✅ Handles nested replies (up to 10 levels)
- ✅ Deep linking to specific message works
- ✅ Highlights linked message
- ✅ Empty state when no messages
- ✅ Loading state
- ✅ Error state
- ✅ Breadcrumbs navigation works

---

#### 4. MessageItem.tsx (Issue #573)

**Purpose**: Individual message with threading support

**Created in**: Issue #573 - Thread List and Detail Views
**Enhanced in**: Issue #574 (Reply UI), #575 (Voting), #576 (Moderation)

**Props**:
```typescript
interface MessageItemProps {
  message: MessageNode;
  depth: number;
  isHighlighted?: boolean;
  showReplyForm?: boolean;
  onReply?: (messageId: string) => void;
}
```

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ [depth * 24px margin-left]                                  │
│                                                              │
│ 👤 username [MODERATOR] [CREATOR] • 2 hours ago            │
│ ─────────────────────────────────────────────────────────   │
│ Message content goes here. Can be multiple paragraphs.     │
│ Supports **markdown** formatting.                           │
│                                                              │
│ ⬆️ 23  ⬇️ 2  |  💬 Reply  |  ⋯ More                        │
└─────────────────────────────────────────────────────────────┘
   │
   └─> Nested replies render recursively with increased margin
```

**Styled Components**:
```typescript
const MessageContainer = styled.div<{
  $depth: number;
  $isHighlighted?: boolean;
  $isDeleted?: boolean;
}>`
  margin-left: ${props => Math.min(props.$depth * 24, 240)}px;
  padding: ${spacing.md};
  background: ${props => props.$isHighlighted ? color.B1 : color.N2};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  transition: all 0.3s;

  ${props => props.$isDeleted && `
    opacity: 0.6;
    background: ${color.N3};
  `}

  @media (max-width: 640px) {
    margin-left: ${props => Math.min(props.$depth * 12, 48)}px;
    padding: ${spacing.sm};
  }
`;

const MessageHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.sm};
  padding-bottom: ${spacing.sm};
  border-bottom: 1px solid ${color.N4};
`;

const Username = styled.span`
  font-weight: 600;
  color: ${color.N10};
`;

const MessageTimestamp = styled.span`
  font-size: 13px;
  color: ${color.N6};
`;

const MessageContent = styled.div`
  color: ${color.N9};
  line-height: 1.6;
  margin-bottom: ${spacing.md};

  p {
    margin: 0 0 ${spacing.sm} 0;
  }

  code {
    background: ${color.N3};
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
  }
`;

const MessageFooter = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.md};

  @media (max-width: 640px) {
    flex-wrap: wrap;
  }
`;
```

**Testing**:
- ✅ Renders message content correctly
- ✅ Applies correct indentation based on depth
- ✅ Shows user badges (moderator, creator)
- ✅ Formats timestamp as relative time
- ✅ Renders markdown content safely
- ✅ Voting buttons appear and work (#575)
- ✅ Reply button appears and works (#574)
- ✅ Nested replies render recursively
- ✅ Deleted messages show as [deleted]
- ✅ Highlighted state applies correctly

---

#### 5. MessageTree.tsx (Issue #573)

**Purpose**: Recursive component for rendering message hierarchy

**Created in**: Issue #573 - Thread List and Detail Views

**Props**:
```typescript
interface MessageTreeProps {
  messages: MessageNode[];
  highlightedMessageId?: string | null;
}
```

**Implementation**:
```typescript
export function MessageTree({ messages, highlightedMessageId }: MessageTreeProps) {
  return (
    <>
      {messages.map(message => (
        <React.Fragment key={message.id}>
          <MessageItem
            message={message}
            depth={message.depth}
            isHighlighted={message.id === highlightedMessageId}
          />

          {message.children.length > 0 && (
            <MessageTree
              messages={message.children}
              highlightedMessageId={highlightedMessageId}
            />
          )}
        </React.Fragment>
      ))}
    </>
  );
}
```

**Testing**:
- ✅ Renders flat list of messages
- ✅ Renders nested messages correctly
- ✅ Maintains proper depth through recursion
- ✅ Passes highlighted state through tree
- ✅ Performance is acceptable with 100+ messages

---

### Supporting Components

#### ThreadBadge.tsx

**Purpose**: Visual indicator for thread state

```typescript
interface ThreadBadgeProps {
  type: "pinned" | "locked" | "deleted";
  compact?: boolean;
}

const BadgeContainer = styled.span<{ $type: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;

  ${props => {
    switch (props.$type) {
      case "pinned":
        return `
          background: ${color.B2};
          color: ${color.B8};
        `;
      case "locked":
        return `
          background: ${color.R2};
          color: ${color.R8};
        `;
      case "deleted":
        return `
          background: ${color.N4};
          color: ${color.N7};
        `;
    }
  }}
`;

export function ThreadBadge({ type, compact }: ThreadBadgeProps) {
  const icons = {
    pinned: <Pin size={14} />,
    locked: <Lock size={14} />,
    deleted: <Trash2 size={14} />,
  };

  const labels = {
    pinned: "Pinned",
    locked: "Locked",
    deleted: "Deleted",
  };

  return (
    <BadgeContainer $type={type}>
      {icons[type]}
      {!compact && <span>{labels[type]}</span>}
    </BadgeContainer>
  );
}
```

---

#### RelativeTime.tsx

**Purpose**: Format timestamps as relative time

```typescript
import { formatDistanceToNow } from "date-fns";

interface RelativeTimeProps {
  date: string | Date;
  suffix?: boolean;
}

export function RelativeTime({ date, suffix = true }: RelativeTimeProps) {
  const [time, setTime] = useState(() =>
    formatDistanceToNow(new Date(date), { addSuffix: suffix })
  );

  // Update every minute
  useEffect(() => {
    const interval = setInterval(() => {
      setTime(formatDistanceToNow(new Date(date), { addSuffix: suffix }));
    }, 60000);

    return () => clearInterval(interval);
  }, [date, suffix]);

  return <span title={new Date(date).toLocaleString()}>{time}</span>;
}
```

---

## Data Flow Patterns

### 1. Fetch and Display Threads

```
User navigates to corpus → ThreadList mounts
  ↓
ThreadList useQuery(GET_CONVERSATIONS, { corpusId })
  ↓
Apollo sends GraphQL request to backend
  ↓
Backend returns conversations with message counts
  ↓
Apollo stores in cache
  ↓
ThreadList receives data → applies sort/filter → renders
  ↓
User sees list of threads
```

### 2. Sort and Filter (Client-Side)

```typescript
// In ThreadList.tsx

const [sortBy] = useAtom(threadSortAtom);
const [filters] = useAtom(threadFiltersAtom);

const sortedAndFilteredThreads = useMemo(() => {
  let threads = data?.conversations?.edges?.map(e => e.node) || [];

  // Apply filters
  if (!filters.showLocked) {
    threads = threads.filter(t => !t.isLocked);
  }
  if (!filters.showDeleted) {
    threads = threads.filter(t => !t.deletedAt);
  }

  // Apply sort
  threads = threads.sort((a, b) => {
    // Pinned always first
    if (a.isPinned && !b.isPinned) return -1;
    if (!a.isPinned && b.isPinned) return 1;

    switch (sortBy) {
      case "newest":
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      case "active":
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
      case "upvoted":
        // TODO: Calculate total upvotes from messages
        return 0;
      default:
        return 0;
    }
  });

  return threads;
}, [data, sortBy, filters]);
```

### 3. Open Thread Detail

```
User clicks thread → navigate to /discussions/:corpusId/thread/:threadId
  ↓
ThreadDetail mounts with conversationId prop
  ↓
ThreadDetail useQuery(GET_THREAD_DETAIL, { conversationId })
  ↓
Apollo sends GraphQL request
  ↓
Backend returns conversation with allMessages array
  ↓
Apollo stores in cache
  ↓
ThreadDetail receives data → builds message tree → renders
  ↓
User sees full thread with nested messages
```

### 4. Infinite Scroll Pagination

```typescript
// In ThreadList.tsx

const { data, loading, fetchMore } = useQuery(GET_CONVERSATIONS, {
  variables: {
    corpusId,
    limit: 20,
  },
});

const handleLoadMore = () => {
  if (data?.conversations?.pageInfo?.hasNextPage) {
    fetchMore({
      variables: {
        cursor: data.conversations.pageInfo.endCursor,
      },
    });
  }
};

// In JSX
<FetchMoreOnVisible fetchNextPage={handleLoadMore} />
```

### 5. Refetch on Interval

```typescript
// Refetch thread list every 30 seconds for new threads
const { data, refetch } = useQuery(GET_CONVERSATIONS, {
  variables: { corpusId },
  pollInterval: 30000,  // 30 seconds
});
```

---

## Testing Strategy

> **Note**: Testing patterns established in **Issues #573-577** (foundation components) should be followed for **Issues #621-623** (integration views). All new components need comprehensive Playwright component tests following these patterns.

### Test File Structure

```
frontend/tests/threads/
├── ThreadList.test.tsx
├── ThreadListItem.test.tsx
├── ThreadDetail.test.tsx
├── MessageItem.test.tsx
├── MessageTree.test.tsx
├── utils/
│   ├── mockThreadData.ts
│   └── ThreadTestWrapper.tsx
└── __snapshots__/
```

### Test Wrapper Pattern

```typescript
// frontend/tests/threads/utils/ThreadTestWrapper.tsx

import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";

export function ThreadTestWrapper({
  children,
  mocks = [],
  initialRoute = "/"
}: {
  children: React.ReactNode;
  mocks?: any[];
  initialRoute?: string;
}) {
  return (
    <MemoryRouter initialEntries={[initialRoute]}>
      <MockedProvider mocks={mocks} addTypename={false}>
        <JotaiProvider>
          {children}
        </JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
}
```

### Mock Data Factory

```typescript
// frontend/tests/threads/utils/mockThreadData.ts

export function createMockThread(overrides?: Partial<ConversationType>): ConversationType {
  return {
    id: "thread-1",
    conversationType: "THREAD",
    title: "Test Thread",
    description: "Test description",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    creator: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
    chatWithCorpus: {
      id: "corpus-1",
      title: "Test Corpus",
    },
    chatMessages: {
      totalCount: 5,
    },
    isPinned: false,
    isLocked: false,
    deletedAt: null,
    myPermissions: ["READ", "WRITE"],
    ...overrides,
  };
}

export function createMockMessage(overrides?: Partial<ChatMessageType>): ChatMessageType {
  return {
    id: "message-1",
    msgType: "HUMAN",
    content: "Test message content",
    createdAt: new Date().toISOString(),
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
    upvoteCount: 5,
    downvoteCount: 1,
    userVote: null,
    parentMessage: null,
    deletedAt: null,
    ...overrides,
  };
}
```

### Example Test: ThreadList

```typescript
// frontend/tests/threads/ThreadList.test.tsx

import { test, expect } from "@playwright/experimental-ct-react";
import { ThreadList } from "../../src/components/threads/ThreadList";
import { ThreadTestWrapper } from "./utils/ThreadTestWrapper";
import { createMockThread } from "./utils/mockThreadData";
import { GET_CONVERSATIONS } from "../../src/graphql/queries";

test("renders thread list with mocked data", async ({ mount }) => {
  const mockThreads = [
    createMockThread({ id: "1", title: "First Thread", isPinned: true }),
    createMockThread({ id: "2", title: "Second Thread" }),
  ];

  const mocks = [
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: { corpusId: "corpus-1", conversationType: "THREAD" },
      },
      result: {
        data: {
          conversations: {
            edges: mockThreads.map(thread => ({ node: thread })),
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: "",
              endCursor: "",
            },
            totalCount: 2,
          },
        },
      },
    },
  ];

  const component = await mount(
    <ThreadTestWrapper mocks={mocks}>
      <ThreadList corpusId="corpus-1" />
    </ThreadTestWrapper>
  );

  // Wait for data to load
  await component.waitFor({ timeout: 2000 });

  // Check that threads are rendered
  await expect(component.getByText("First Thread")).toBeVisible();
  await expect(component.getByText("Second Thread")).toBeVisible();

  // Check that pinned badge shows
  await expect(component.getByText("Pinned")).toBeVisible();
});

test("applies sort correctly", async ({ mount, page }) => {
  const mockThreads = [
    createMockThread({
      id: "1",
      title: "Old Thread",
      createdAt: "2024-01-01T00:00:00Z",
    }),
    createMockThread({
      id: "2",
      title: "New Thread",
      createdAt: "2024-12-01T00:00:00Z",
    }),
  ];

  const mocks = [
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: { corpusId: "corpus-1" },
      },
      result: {
        data: {
          conversations: {
            edges: mockThreads.map(thread => ({ node: thread })),
            pageInfo: {},
            totalCount: 2,
          },
        },
      },
    },
  ];

  const component = await mount(
    <ThreadTestWrapper mocks={mocks}>
      <ThreadList corpusId="corpus-1" />
    </ThreadTestWrapper>
  );

  await component.waitFor({ timeout: 2000 });

  // Get initial order
  const threadTitles = await component.locator("h3").allTextContents();
  expect(threadTitles).toEqual(["New Thread", "Old Thread"]);

  // Click sort dropdown and select "oldest first" (if implemented)
  // await component.getByRole("button", { name: /sort/i }).click();
  // await page.getByText("Oldest First").click();

  // Check new order
  // const newThreadTitles = await component.locator("h3").allTextContents();
  // expect(newThreadTitles).toEqual(["Old Thread", "New Thread"]);
});

test("shows empty state when no threads", async ({ mount }) => {
  const mocks = [
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: { corpusId: "corpus-1" },
      },
      result: {
        data: {
          conversations: {
            edges: [],
            pageInfo: {},
            totalCount: 0,
          },
        },
      },
    },
  ];

  const component = await mount(
    <ThreadTestWrapper mocks={mocks}>
      <ThreadList corpusId="corpus-1" />
    </ThreadTestWrapper>
  );

  await component.waitFor({ timeout: 2000 });

  await expect(component.getByText(/no discussions yet/i)).toBeVisible();
});
```

### Running Tests

```bash
# Run all thread tests
yarn run test:ct --reporter=list -g "Thread"

# Run specific test file
yarn run test:ct --reporter=list frontend/tests/threads/ThreadList.test.tsx

# Run with UI for debugging
yarn run test:ct --ui frontend/tests/threads/ThreadList.test.tsx
```

---

## Implementation Checklist

### ✅ Issue #573: Thread List and Detail Views (COMPLETED)

**Branch**: `feature/thread-list-detail-573`
**Status**: ✅ Complete and committed (with linting fixes)
**Commit**: `ba31e15b`

#### Components Created
- [x] `ThreadList.tsx` - Container with sorting/filtering
- [x] `ThreadListItem.tsx` - Individual thread cards
- [x] `ThreadBadge.tsx` - Pinned/locked/deleted indicators
- [x] `ThreadDetail.tsx` - Full thread view with message tree
- [x] `MessageItem.tsx` - Individual message with nesting
- [x] `MessageTree.tsx` - Recursive message rendering
- [x] `RelativeTime.tsx` - Time formatting with date-fns
- [x] `utils.ts` - Message tree building, sorting, filtering
- [x] `useThreadPreferences.ts` - Hook for user preferences
- [x] `threadAtoms.ts` - Jotai state management
- [x] GraphQL queries and TypeScript types

#### Testing
- [x] ThreadList.test.tsx
- [x] ThreadDetail.test.tsx
- [x] utils.test.ts
- [x] Mock data factories
- [x] Test wrapper

---

### ✅ Issue #574: Message Composer and Reply UI (COMPLETED)

**Branch**: `feature/message-composer-574` (based on #573)
**Status**: ✅ Complete and committed
**Commit**: `9f2f7739`

#### Components Created
- [x] `MessageComposer.tsx` - TipTap rich text editor
- [x] `CreateThreadForm.tsx` - Thread creation modal
- [x] `ReplyForm.tsx` - Inline reply component
- [x] GraphQL mutations (CREATE_THREAD, CREATE_THREAD_MESSAGE, REPLY_TO_MESSAGE)
- [x] TipTap dependencies installed

#### Testing
- [x] MessageComposer.ct.tsx (15 tests)
- [x] CreateThreadForm.ct.tsx (12 tests)
- [x] ReplyForm.ct.tsx (14 tests)

---

### ✅ Issue #575: Voting UI and Reputation Display (COMPLETED)

**Branch**: `feature/voting-ui-575` (based on #574)
**Status**: ✅ Complete and committed
**Commit**: `c637ebdc`

#### Components Created
- [x] `VoteButtons.tsx` - Upvote/downvote with optimistic updates
- [x] `ReputationBadge.tsx` - Compact display with tooltip
- [x] `ReputationDisplay.tsx` - User context display
- [x] `UserProfileReputation.tsx` - Full profile section
- [x] GraphQL mutations (UPVOTE_MESSAGE, DOWNVOTE_MESSAGE, REMOVE_VOTE)

#### Testing
- [x] VoteButtons.ct.tsx (15 tests)
- [x] ReputationBadge.ct.tsx (12 tests)

---

### ✅ Issue #576: Moderation UI and Controls (COMPLETED)

**Branch**: `feature/moderation-ui-576` (based on #575)
**Status**: ✅ Complete and committed
**Commit**: `3b72d22c`

#### Components Created
- [x] `ModerationControls.tsx` - Unified moderation component with pin/lock/delete/restore
- [x] `ModeratorBadge.tsx` - Visual moderator indicator with Shield icon
- [x] GraphQL mutations (PIN_THREAD, UNPIN_THREAD, LOCK_THREAD, UNLOCK_THREAD, DELETE_THREAD, RESTORE_THREAD)

#### Testing
- [x] ModerationControls.ct.tsx (16 tests)
  - Button rendering and state changes
  - All mutation scenarios
  - Confirmation dialog flow
  - Error handling
  - Permission checks

---

### ✅ Issue #577: Notification Center UI (COMPLETED)

**Branch**: `feature/notification-center-577` (based on #576)
**Status**: ✅ Complete and committed
**Commit**: `fa78527d`

#### Components Created
- [x] `NotificationBell.tsx` - Bell icon with unread count badge and dropdown trigger
- [x] `NotificationDropdown.tsx` - Quick notification access from header
- [x] `NotificationItem.tsx` - Individual notification display with all notification types
- [x] `NotificationCenter.tsx` - Full page notification center with filtering
- [x] GraphQL queries (GET_NOTIFICATIONS, GET_UNREAD_NOTIFICATION_COUNT)
- [x] GraphQL mutations (MARK_NOTIFICATION_READ, MARK_NOTIFICATION_UNREAD, MARK_ALL_NOTIFICATIONS_READ, DELETE_NOTIFICATION)

#### Features
- Unread count badge with 99+ overflow handling
- Real-time polling (configurable interval, default 30s)
- Deep linking to threads/messages
- Filter notifications (all/unread/read)
- Mark individual or all notifications as read/unread
- Delete notifications
- Click-outside-to-close dropdown
- Responsive design for mobile/desktop
- Apollo cache refetching for instant updates

#### Testing
- [x] NotificationBell.ct.tsx (7 tests)
- [x] NotificationItem.ct.tsx (15 tests)
- [x] NotificationCenter.ct.tsx (11 tests)
- 33 comprehensive tests covering all notification types and interactions

---

## Pending Issues: Roadmap to Full Integration

The remaining issues (#578-580, #610-611, #621-623, #634) complete the discussion system by adding supporting features and full integration into existing views. Issues **#621-623 now link to detailed specifications** in the [Integration with Existing Views](#integration-with-existing-views) section.

**Key Update**: Issues #621-623 have been enhanced with:
- Comprehensive routing architecture following `docs/frontend/routing_system.md`
- Detailed component specifications with code examples
- @ mentions feature for cross-referencing corpuses and documents
- Implementation checklists mapped to specific phases

**NEW: Agent/Bot Configuration** (Issue #634):
- Backend model for configurable bots with custom tools, instructions, badges
- Blocks frontend work on #610, #611 (user/bot badge display)
- Foundation for showing bot identity consistently across the app

**Progression Summary**:
1. **#634**: Backend agent/bot configuration (FOUNDATION - blocks #610, #611)
2. **#612**: ✅ Badge notification system (COMPLETED)
3. **#578-580**: Supporting features (badges, analytics, search)
4. **#610**: Display user & bot badges in conversations (depends on #634)
5. **#611**: User profile page (depends on #634, #610)
6. **#621**: Corpus integration with full-page thread routing
7. **#622**: Document integration with sidebar discussions
8. **#623**: Global discussions view + @ mentions

---

### ⏳ Issue #634: Backend: Configurable Agent/Bot Profiles for Conversations

**Status**: ⏳ Pending (foundational - should be next after #577)
**Estimated**: 12-16 hours (2 days)
**Blocks**: #610, #611

**Scope**:
- Create `AgentConfiguration` model with tools, instructions, badges, display metadata
- Add `agent_configuration` FK to `ChatMessage`
- GraphQL schema for querying/managing agents
- Permission model: global agents (public read) vs corpus agents (inherit corpus perms)
- Data migration to create default agents from settings
- Tests for model, permissions, GraphQL operations

**Why First**:
- #610 needs agent badge data to display bot badges alongside user badges
- #611 should use same UI patterns as #610 for consistency
- Implementing backend first avoids retrofitting frontend later

**Related Issues**: #610, #611

---

### ⏳ Issue #578: Badge Display and Management UI

**Status**: ⏳ Pending (after #577)
**Estimated**: 4 days

---

### ⏳ Issue #579: Analytics Dashboard

**Status**: ⏳ Pending (after #578)
**Estimated**: 4 days

---

### ⏳ Issue #580: Thread Search UI

**Status**: ⏳ Pending (after #579)
**Estimated**: 4 days

---

### ⏳ Issue #610: Display User Badges in Conversation/Chat UI

**Status**: ⏳ Pending (after #634)
**Estimated**: 6-8 hours
**Depends On**: #634 (Backend: Agent Configuration)

**Scope**:
- Display earned badges as small pills next to usernames in conversation threads
- Display bot/agent badges from `agent_configuration.badge_config`
- Use consistent rendering patterns for both user and bot badges
- GraphQL queries to fetch user badge data and agent configuration
- Badge priority/filtering (show top 2-3 badges, hover for more)
- Performance optimization (no lag from badge queries)
- Mobile-responsive (may hide badges on small screens)

**Why After #634**:
- Needs `agent_configuration` field from ChatMessage
- Needs `badge_config` JSON structure from AgentConfiguration model
- Should render user and bot badges with same visual pattern

**Related Issues**: #634 (depends on), #611 (establishes patterns for)

---

### ⏳ Issue #611: Create User Profile Page with Badge Display and Stats

**Status**: ⏳ Pending (after #610)
**Estimated**: 8-10 hours
**Depends On**: #634 (Backend: Agent Configuration), #610 (Badge UI patterns)

**Scope**:
- Create routes `/profile` (current user) and `/users/:userId` (any user)
- UserProfile view component with sections:
  - User info (avatar, name, bio, join date)
  - Badge showcase (reuse patterns from #610)
  - Contribution statistics
  - Recent activity feed
- Permissions/privacy settings
- Mobile-responsive layout
- Navigation from username clicks throughout app

**Why After #610**:
- Should reuse badge display components from #610
- Same visual style across conversation UI and profile page
- #610 establishes badge UI patterns to follow

**Related Issues**: #634 (depends on), #610 (depends on, reuses patterns)

---

### ✅ Issue #612: Badge Notification System for Auto-Awarded Badges (COMPLETED)

**Status**: ✅ Complete
**Estimated**: 10-12 hours (Extra Large)
**Completed**: November 7, 2025
**PR**: #638

**Scope**:
Implemented a comprehensive badge notification system that provides immediate visual feedback when users earn badges through auto-award criteria or manual awards. The system includes:

#### Components Created

**1. `useBadgeNotifications` Hook** (`frontend/src/hooks/useBadgeNotifications.ts`)
- Polls for BADGE notification types from backend
- Detects newly awarded badges in real-time (30-second polling interval)
- Filters out already-shown badges to prevent duplicates
- Skips initial load to avoid showing old badge awards
- Returns badge data: name, description, icon, color, award context

**2. `BadgeToast` Component** (`frontend/src/components/badges/BadgeToast.tsx`)
- Compact toast notification using react-toastify
- Displays badge icon with custom color
- Shows badge name and awarding context
- Differentiates between auto-awarded and manual awards
- Uses Lucide React icons with fallback to Award icon

**3. `BadgeCelebrationModal` Component** (`frontend/src/components/badges/BadgeCelebrationModal.tsx`)
- Full-screen celebration modal with rich animations
- Framer Motion animations for entrance, icon spin, and sparkles
- 6 sparkle animations around badge icon with staggered timing
- Badge display: icon (120px), name, description, award message
- "View Your Badges" button navigates to `/badges` route
- Click-outside or close button to dismiss
- Responsive design for mobile and desktop

**4. `useBadgeCelebration` Hook** (`frontend/src/hooks/useBadgeCelebration.ts`)
- Manages badge celebration state and queueing
- Prevents duplicate celebrations using Set-based tracking
- Queues multiple badges earned simultaneously
- Configurable delays between showing badges (default: 500ms)
- Shows toast for all badges, modal for significant badges (auto-awarded)
- Options for toast duration, queue delay, enable/disable toast or modal

**5. App Integration** (`frontend/src/App.tsx`)
- Integrated badge notification system into main app
- Polls every 30 seconds for new badge awards
- Renders BadgeCelebrationModal when badges are earned
- Navigation to `/badges` route on "View Your Badges" click

#### Features

**Real-Time Detection**:
- Polling-based approach (30-second interval)
- Uses existing GET_NOTIFICATIONS GraphQL query
- Filters for BADGE notification type
- Compatible with existing notification infrastructure

**Visual Feedback**:
- **Toast Notification**: Appears for all badge awards (top-right, 5s duration)
- **Celebration Modal**: Full-screen modal for significant badges (auto-awarded)
- **Animations**: Smooth entrance, icon spin, sparkle effects using Framer Motion
- **Customizable Icons**: Uses Lucide React icon system with fallback

**Queue Management**:
- Handles multiple badges earned simultaneously
- Prevents overwhelming user with notifications
- Configurable delay between badge displays
- Tracks shown badges to prevent duplicates
- Persists across page navigation until dismissed

**Award Context**:
- Shows "You earned the [badge] badge!" for auto-awards
- Shows "[username] awarded you the [badge] badge!" for manual awards
- Displays badge description and achievement details

#### Testing

**Component Tests** (`frontend/tests/BadgeCelebration.ct.tsx`)
- ✅ 10 comprehensive tests using Playwright Component Testing
- BadgeCelebrationModal tests (6 tests):
  - Renders with badge information
  - Shows awarded by message for manual awards
  - Calls onClose when close button clicked
  - Calls onViewBadges when button clicked
  - Displays badge icon
  - Closes when clicking close button
- BadgeToast tests (4 tests):
  - Renders badge information in toast
  - Shows awarded by message for manual awards
  - Displays badge icon with correct color
  - Handles unknown icon gracefully

**All tests passing**: 10/10 passed in 6.9s

#### Backend Integration

The backend already had all necessary infrastructure:
- `UserBadge` model for tracking badge awards
- `create_badge_notification` signal handler creates notifications when badges are awarded
- `check_auto_badges` Celery task for auto-awarding badges based on criteria
- `GET_NOTIFICATIONS` GraphQL query returns badge notification data

**Notification Data Structure**:
```json
{
  "notificationType": "BADGE",
  "data": {
    "badge_id": "...",
    "badge_name": "First Post",
    "badge_description": "Made your first post",
    "badge_icon": "Trophy",
    "badge_color": "#05313d",
    "is_auto_awarded": true
  },
  "actor": { "username": "..." } // Present for manual awards
}
```

#### Technical Decisions

**Why Polling Instead of WebSockets**:
- Reuses existing NotificationBell polling infrastructure (30s interval)
- Simpler implementation with no additional backend changes
- Consistent with existing notification system
- Near-real-time performance acceptable for badge awards

**Why Separate Toast and Modal**:
- Toast for all badges (non-intrusive, quick feedback)
- Modal for significant achievements (celebration moment)
- User can dismiss modal and continue working
- Provides flexibility in notification intensity

**Why Queue System**:
- Prevents overwhelming user with multiple simultaneous notifications
- Ensures user sees and appreciates each badge
- Configurable delays allow tuning UX
- Handles edge cases like earning multiple badges at once

#### Acceptance Criteria

- ✅ Toast notification appears when badge is auto-awarded
- ✅ Celebration modal displays for significant badges
- ✅ Animations are smooth and non-intrusive
- ✅ Notifications don't spam user (debounced/queued)
- ✅ Works in real-time (30-second polling)
- ✅ User can dismiss notifications
- ✅ Notifications persist across page navigation (until dismissed)
- ✅ Backend event emission is reliable (signal-based)

#### Files Changed

**Created**:
- `frontend/src/hooks/useBadgeNotifications.ts` - Badge detection hook
- `frontend/src/hooks/useBadgeCelebration.ts` - Celebration state management
- `frontend/src/components/badges/BadgeToast.tsx` - Toast component
- `frontend/src/components/badges/BadgeCelebrationModal.tsx` - Modal component
- `frontend/tests/BadgeCelebration.ct.tsx` - Component tests

**Modified**:
- `frontend/src/App.tsx` - Integrated badge celebration system

#### Performance Considerations

- Polling every 30 seconds (same as NotificationBell)
- Set-based duplicate tracking (O(1) lookups)
- Minimal re-renders using useState and useCallback
- Animations use GPU-accelerated transforms
- Toast notifications auto-close after 5 seconds
- Modal animations use Framer Motion with spring physics

#### Future Enhancements (Optional)

- WebSocket support for instant notifications
- Confetti animation library integration
- Sound effects for badge awards
- Badge tier system (bronze/silver/gold celebration intensity)
- Social sharing of badge achievements
- Badge award history timeline

**Related Issues**: #558 (Badge System Epic), #572 (Social Features), Backend signal infrastructure already in place

---

### ⏳ Issue #621: Forum-like Corpus Discussion View

**Status**: ⏳ Pending (after #580)
**Estimated**: 3 days (updated to include routing)
**Specification**: See [Integration with Existing Views → Corpus View Integration](#corpus-view-integration)

**Scope**:
- Implement routing infrastructure (Phase 1 of Implementation Checklist)
- Add Discussions tab to Corpuses sidebar
- Create `CorpusDiscussionsView.tsx` component
- Implement full-page thread navigation via `/c/:user/:corpus/discussions/:threadId`
- Wire up CreateThreadButton in corpus context
- Complete Phase 2 tasks from Implementation Checklist

**Related Sections**:
- [Component Specifications](#component-specifications) - Reuse ThreadList, ThreadDetail, CreateThreadForm
- [Testing Strategy](#testing-strategy) - Test patterns for component tests
- [Performance Considerations](#performance-considerations) - Virtual scrolling, memoization patterns
- [Accessibility Requirements](#accessibility-requirements) - Keyboard nav, ARIA labels

---

### ⏳ Issue #622: Document-Specific Discussions

**Status**: ⏳ Pending (after #621)
**Estimated**: 3 days
**Specification**: See [Integration with Existing Views → DocumentKnowledgeBase Integration](#documentknowledgebase-integration)

**Scope**:
- Add Discussions tab to DocumentKnowledgeBase sidebar
- Create `DocumentDiscussionsContent.tsx` component
- Implement auto-open sidebar on `?thread=` query param
- Add thread count badge to sidebar tab
- Wire up CreateThreadButton in document context
- Complete Phase 3 tasks from Implementation Checklist

**Related Sections**:
- [Component Specifications](#component-specifications) - Reuse ThreadList, ThreadDetail, CreateThreadForm
- [State Management Strategy](#state-management-strategy) - Sidebar state management patterns
- [Testing Strategy](#testing-strategy) - Test patterns for sidebar integration
- [Performance Considerations](#performance-considerations) - Lazy loading, debounced updates
- [Accessibility Requirements](#accessibility-requirements) - Focus management for sidebar

---

### ⏳ Issue #623: Global Discussions Forum View

**Status**: ⏳ Pending (after #622)
**Estimated**: 4 days (updated to include @ mentions)
**Specification**: See [Integration with Existing Views → Global Discussions View](#global-discussions-view) and [@ Mentions Feature](#-mentions-feature)

**Scope**:
- Create `GlobalDiscussionsRoute.tsx` and `GlobalDiscussions.tsx`
- Implement tabbed sections (All/Corpus/Document/General)
- Add search/filter functionality
- Implement FAB for creating threads
- Add rich visual design with animations
- **NEW**: Implement @ mentions feature for cross-referencing corpuses and documents
- Complete Phase 4 and Phase 5 tasks from Implementation Checklist

**Note**: This issue now includes the @ mentions feature, which adds significant value for cross-referencing resources within discussions.

**Related Sections**:
- [Component Specifications](#component-specifications) - Reuse ThreadList, ThreadDetail, MessageComposer
- [State Management Strategy](#state-management-strategy) - Global state and filter atoms
- [Testing Strategy](#testing-strategy) - Test patterns for full-page views and @ mentions
- [Code Examples & Patterns](#code-examples--patterns) - Animation patterns, optimistic updates
- [Performance Considerations](#performance-considerations) - Virtual scrolling for large lists
- [Accessibility Requirements](#accessibility-requirements) - Tabbed navigation, mention autocomplete

---

## Branch Dependency Tree

```
v3.0.0.b3 (base)
└─ feature/thread-list-detail-573 ✅ (committed)
   └─ feature/message-composer-574 ✅ (committed)
      └─ feature/voting-ui-575 ✅ (committed)
         └─ feature/moderation-ui-576 ✅ (committed)
            └─ feature/notification-center-577 ✅ (committed)
               ├─ feature/badge-notification-612 ✅ (COMPLETED - 1.5 days)
               ├─ feature/agent-configuration-634 ⏳ (2 days - NEXT, foundational)
               │  └─ feature/badge-display-610 ⏳ (1 day - depends on #634)
               │     └─ feature/user-profile-611 ⏳ (1.5 days - depends on #634, #610)
               └─ feature/badge-management-578 ⏳ (4 days)
                  └─ feature/analytics-dashboard-579 ⏳ (4 days)
                     └─ feature/thread-search-580 ⏳ (4 days)
                        └─ feature/corpus-discussions-621 ⏳ (3 days - includes routing)
                           └─ feature/document-discussions-622 ⏳ (3 days)
                              └─ feature/global-discussions-623 ⏳ (4 days - includes @ mentions)
```

**IMPORTANT**: Each branch builds on the previous issue's branch to maintain a clean dependency chain.

**Key Dependencies**:
- **#612 (Badge Notifications)** ✅ Complete - standalone feature, no dependencies
- **#634 (Agent Configuration)** is foundational and should be implemented next
- **#610 and #611** branch from #634 (not from #578) because they need agent data
- **#578-580** can proceed in parallel with #634→#610→#611 track
- **#621-623** are integration work that comes after all UI components are done

**Total Remaining Effort**: ~25 days across 8 issues (#634, #578-580, #610-611, #621-623)

---

## Code Examples & Patterns

### Pattern 1: Fetch with Loading/Error States

```typescript
export function ThreadList({ corpusId }: ThreadListProps) {
  const { data, loading, error, refetch } = useQuery(GET_CONVERSATIONS, {
    variables: { corpusId, conversationType: "THREAD" },
    pollInterval: 30000,
  });

  if (loading) {
    return <ModernLoadingDisplay type="default" message="Loading discussions..." />;
  }

  if (error) {
    return (
      <ModernErrorDisplay
        type="generic"
        error={error.message}
        onRetry={() => refetch()}
      />
    );
  }

  const threads = data?.conversations?.edges?.map(e => e.node) || [];

  if (threads.length === 0) {
    return <ThreadListEmpty corpusId={corpusId} />;
  }

  return (
    <ThreadListContainer>
      <ThreadListHeader corpusId={corpusId} />
      <ThreadGrid>
        {threads.map(thread => (
          <ThreadListItem key={thread.id} thread={thread} />
        ))}
      </ThreadGrid>
    </ThreadListContainer>
  );
}
```

### Pattern 2: Optimistic Updates (for Voting - #575)

```typescript
const [voteMessage] = useMutation(VOTE_MESSAGE, {
  optimisticResponse: ({ messageId, voteType }) => ({
    voteMessage: {
      ok: true,
      obj: {
        id: messageId,
        upvoteCount: voteType === "UPVOTE" ? message.upvoteCount + 1 : message.upvoteCount,
        downvoteCount: voteType === "DOWNVOTE" ? message.downvoteCount + 1 : message.downvoteCount,
        userVote: voteType,
      },
    },
  }),
});
```

### Pattern 3: Permission-Based Rendering

```typescript
function ThreadDetailHeader({ thread }: { thread: ConversationType }) {
  const canModerate = thread.myPermissions?.includes("MODERATE");
  const isCreator = thread.creator.id === currentUser.id;

  return (
    <ThreadHeader>
      <ThreadTitleLarge>{thread.title}</ThreadTitleLarge>
      {thread.description && <ThreadDescription>{thread.description}</ThreadDescription>}

      {(canModerate || isCreator) && (
        <ModerationControls thread={thread} />
      )}
    </ThreadHeader>
  );
}
```

### Pattern 4: Error Boundary Usage

```typescript
<ErrorBoundary
  fallback={(error, reset) => (
    <ModernErrorDisplay
      type="generic"
      error={error.message}
      onRetry={reset}
    />
  )}
>
  <ThreadList corpusId={corpusId} />
</ErrorBoundary>
```

### Pattern 5: Responsive Design

```typescript
const ThreadCard = styled.div`
  padding: ${spacing.md};

  @media (max-width: 640px) {
    padding: ${spacing.sm};
  }

  @media (min-width: 641px) and (max-width: 900px) {
    padding: ${spacing.md};
  }

  @media (min-width: 901px) {
    padding: ${spacing.lg};
  }
`;
```

---

## Performance Considerations

> **Note**: These performance patterns apply to **all issues** (#573-577, #621-623). When implementing any discussion feature, review these strategies to ensure optimal performance, especially with large datasets.

### Optimization Strategies

1. **Message Tree Memoization**:
```typescript
const messageTree = useMemo(
  () => buildMessageTree(thread.allMessages || []),
  [thread.allMessages]
);
```

2. **Virtual Scrolling** (if >100 threads):
```typescript
import { useVirtualizer } from "@tanstack/react-virtual";

const virtualizer = useVirtualizer({
  count: threads.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: () => 120, // Estimated thread card height
});
```

3. **Lazy Loading Images**:
```typescript
<img
  src={user.avatar}
  loading="lazy"
  alt={user.username}
/>
```

4. **Debounced Search**:
```typescript
const debouncedSearch = useMemo(
  () => debounce((value: string) => {
    setSearchTerm(value);
  }, 300),
  []
);
```

---

## Accessibility Requirements

> **Note**: Accessibility is **critical** for all discussion features. These requirements apply across **all issues** (#573-577, #621-623). Every component must be keyboard-navigable, screen-reader friendly, and WCAG 2.1 AA compliant.

### WCAG 2.1 AA Compliance

1. **Keyboard Navigation**:
   - Tab through thread list items
   - Enter to open thread
   - Arrow keys for navigation
   - Escape to close modals

2. **ARIA Labels**:
```typescript
<button
  aria-label={`Reply to ${message.creator.username}'s message`}
  onClick={handleReply}
>
  Reply
</button>
```

3. **Focus Management**:
```typescript
const focusTrap = useFocusTrap(modalRef, isOpen);
```

4. **Screen Reader Announcements**:
```typescript
<div role="status" aria-live="polite" aria-atomic="true">
  {loading && "Loading discussions..."}
  {error && `Error: ${error.message}`}
</div>
```

---

## Integration with Existing Views

This section provides detailed instructions for integrating the discussion system into existing OpenContracts views, following the centralized routing architecture and maintaining UI/UX consistency.

### Overview: Integration Points

The discussion system integrates into three main areas:

1. **Corpus View** (`Corpuses.tsx`) - Full-page thread discussions
2. **Document Viewer** (`DocumentKnowledgeBase.tsx`) - Sidebar thread discussions
3. **Global Discussions View** - Standalone route with rich visual design

### Routing Architecture

Following the routing mantra in `docs/frontend/routing_system.md`, ALL routing logic is centralized in `CentralRouteManager.tsx`. The discussion system extends this architecture with minimal new routes.

#### New Routes

**Full-Page Thread View (Corpus Context):**
```typescript
// In App.tsx
<Route
  path="/c/:userIdent/:corpusIdent/discussions/:threadId"
  element={<CorpusThreadRoute />}
/>
```

**Global Discussions View:**
```typescript
// In App.tsx
<Route
  path="/discussions"
  element={<GlobalDiscussionsRoute />}
/>
```

**Document Thread View (Query Param):**
- NO new route needed
- Existing `/d/:userIdent/:docIdent` handles thread via query param
- Example: `/d/john/my-doc?thread=abc123`

#### Reactive Vars

**File**: `frontend/src/graphql/cache.ts`

```typescript
// Thread selection state (set by CentralRouteManager Phase 2)
export const selectedThreadId = makeVar<string | null>(null);

// Thread list filters (local to views, NOT in URL)
// These use Jotai atoms, not reactive vars
// Defined in: frontend/src/atoms/threadAtoms.ts
```

**Why `selectedThreadId` is a reactive var:**
- Needs to be in URL for deep linking
- CentralRouteManager Phase 2 parses `?thread=` param
- CentralRouteManager Phase 4 syncs changes back to URL

**Why filters are Jotai atoms:**
- User preferences, NOT part of URL state
- Don't need deep linking or URL sync
- Already have Jotai atoms defined in implementation

#### CentralRouteManager Integration

**Phase 2: Query Params → Reactive Vars**

**File**: `frontend/src/routing/CentralRouteManager.tsx` (lines ~444-484)

```typescript
// Add to existing Phase 2 effect
useEffect(() => {
  // ... existing annotation/analysis param parsing

  // NEW: Thread selection
  const threadId = searchParams.get("thread");
  const currentThreadId = selectedThreadId();

  if (threadId !== currentThreadId) {
    selectedThreadId(threadId);
  }
}, [searchParams]);
```

**Phase 4: Reactive Vars → URL Sync**

**File**: `frontend/src/routing/CentralRouteManager.tsx` (lines ~514-544)

```typescript
// Add to existing Phase 4 dependencies
const threadId = useReactiveVar(selectedThreadId);

useEffect(() => {
  // Don't sync on initial mount
  if (!hasInitializedFromUrl.current) return;

  // Don't sync while route is loading
  if (routeLoading()) return;

  const queryString = buildQueryParams({
    annotationIds: annIds,
    analysisIds,
    extractIds,
    threadId, // NEW: Add thread param
    showStructural: structural,
    showSelectedOnly: selectedOnly,
    showBoundingBoxes: boundingBoxes,
    labelDisplay: labels,
  });

  if (currentSearch !== queryString) {
    navigate({ search: queryString }, { replace: true });
  }
}, [annIds, analysisIds, extractIds, threadId, structural, selectedOnly, boundingBoxes, labels]);
```

**Navigation Utilities**

**File**: `frontend/src/utils/navigationUtils.ts`

```typescript
/**
 * Update thread selection in URL
 */
export function updateThreadSelection(
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void,
  threadId: string | null
) {
  const searchParams = new URLSearchParams(location.search);

  if (threadId) {
    searchParams.set("thread", threadId);
  } else {
    searchParams.delete("thread");
  }

  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Clear thread selection from URL
 */
export function clearThreadSelection(
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void
) {
  updateThreadSelection(location, navigate, null);
}

/**
 * Generate corpus thread URL
 */
export function getCorpusThreadUrl(
  corpus: { creator: { slug: string }; slug: string },
  threadId: string
): string {
  if (!corpus.creator?.slug || !corpus.slug) {
    console.warn("Corpus missing slug data:", corpus);
    return "#";
  }
  return `/c/${corpus.creator.slug}/${corpus.slug}/discussions/${threadId}`;
}

/**
 * Navigate to corpus thread (full page)
 */
export function navigateToCorpusThread(
  corpus: { creator: { slug: string }; slug: string },
  threadId: string,
  navigate: (path: string) => void,
  currentPath: string
) {
  const url = getCorpusThreadUrl(corpus, threadId);
  if (url !== "#" && currentPath !== url) {
    navigate(url);
  }
}

/**
 * Navigate to document thread (sidebar)
 */
export function navigateToDocumentThread(
  threadId: string,
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void
) {
  updateThreadSelection(location, navigate, threadId);
}
```

### Integration 1: Corpuses View

**File**: `frontend/src/views/Corpuses.tsx`

#### Step 1: Add Navigation Tab

**Location**: `navigationItems` array (around line 1820)

```typescript
const navigationItems = useMemo(() => {
  return [
    {
      id: "home",
      label: "Home",
      icon: Home,
      onClick: () => setActiveTab(0),
    },
    {
      id: "documents",
      label: "Documents",
      icon: FileText,
      badge: stats.totalDocs > 0 ? stats.totalDocs : undefined,
      onClick: () => setActiveTab(1),
    },
    // ... existing tabs

    // NEW: Discussions tab
    {
      id: "discussions",
      label: "Discussions",
      icon: MessageSquare,
      badge: stats.totalThreads > 0 ? stats.totalThreads : undefined,
      onClick: () => setActiveTab(DISCUSSIONS_TAB_INDEX), // Define constant
    },

    // ... remaining tabs
  ];
}, [stats, setActiveTab]);
```

#### Step 2: Add Tab Constant

**Location**: Top of file with other constants

```typescript
const HOME_TAB_INDEX = 0;
const DOCUMENTS_TAB_INDEX = 1;
const ANNOTATIONS_TAB_INDEX = 2;
const ANALYSES_TAB_INDEX = 3;
const EXTRACTS_TAB_INDEX = 4;
const DISCUSSIONS_TAB_INDEX = 5; // NEW
const CHAT_TAB_INDEX = 6;
const BADGES_TAB_INDEX = 7;
const SETTINGS_TAB_INDEX = 8;
```

#### Step 3: Add Stats Query

**File**: `frontend/src/graphql/queries.ts`

```typescript
export const GET_CORPUS_STATS = gql`
  query GetCorpusStats($corpusId: ID!) {
    corpusStats(corpusId: $corpusId) {
      totalDocs
      totalAnnotations
      totalAnalyses
      totalExtracts
      totalThreads  # NEW: Add to existing query
    }
  }
`;
```

#### Step 4: Render Discussions Content

**Location**: Main content rendering switch (around line 2100)

```typescript
// In the main content area render logic
{activeTab === DISCUSSIONS_TAB_INDEX && opened_corpus && (
  <CorpusDiscussionsView corpusId={opened_corpus.id} />
)}
```

#### Step 5: Create CorpusDiscussionsView Component

**File**: `frontend/src/components/discussions/CorpusDiscussionsView.tsx`

```typescript
import React from "react";
import { useNavigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import { ThreadList } from "./ThreadList";
import { CreateThreadButton } from "./CreateThreadButton";
import { openedCorpus } from "../../graphql/cache";
import { navigateToCorpusThread } from "../../utils/navigationUtils";
import styled from "styled-components";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
`;

const Title = styled.h2`
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
`;

interface CorpusDiscussionsViewProps {
  corpusId: string;
}

export const CorpusDiscussionsView: React.FC<CorpusDiscussionsViewProps> = ({
  corpusId,
}) => {
  const navigate = useNavigate();
  const corpus = useReactiveVar(openedCorpus);

  const handleThreadClick = (threadId: string) => {
    if (corpus) {
      navigateToCorpusThread(corpus, threadId, navigate, location.pathname);
    }
  };

  return (
    <Container>
      <Header>
        <Title>Corpus Discussions</Title>
        <CreateThreadButton corpusId={corpusId} />
      </Header>

      <ThreadList
        corpusId={corpusId}
        conversationType="THREAD"
        onThreadClick={handleThreadClick}
      />
    </Container>
  );
};
```

### Integration 2: DocumentKnowledgeBase

**File**: `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`

#### Step 1: Add Discussions to SidebarViewMode Type

**Location**: Type definitions (around line 150)

```typescript
export type SidebarViewMode = "feed" | "analysis" | "extract" | "discussions"; // Add "discussions"
```

#### Step 2: Add State for Sidebar Tab

**Location**: State declarations (around line 800)

```typescript
const [sidebarViewMode, setSidebarViewMode] = useState<SidebarViewMode>("feed");
```

#### Step 3: Auto-Open Sidebar on Thread Deep Link

**Location**: Effects section (around line 920)

```typescript
/**
 * Auto-open sidebar when thread param is in URL
 */
useEffect(() => {
  const threadId = useReactiveVar(selectedThreadId);

  if (threadId && opened_document) {
    // Batch updates to prevent cascade of re-renders
    unstable_batchedUpdates(() => {
      setShowRightPanel(true);
      setMode("half"); // 50% width
      setSidebarViewMode("discussions");
    });
  }
}, [selectedThreadId, opened_document, setShowRightPanel, setMode, setSidebarViewMode]);
```

#### Step 4: Add Discussions Tab to Sidebar

**Location**: SidebarTabsContainer render (around line 2400)

```typescript
<SidebarTabsContainer>
  <SidebarTab
    isActive={sidebarViewMode === "feed"}
    onClick={() => setSidebarViewMode("feed")}
  >
    <Layers size={18} />
    {!isMobile && <span>Feed</span>}
  </SidebarTab>

  {/* Existing tabs... */}

  {/* NEW: Discussions Tab */}
  <SidebarTab
    isActive={sidebarViewMode === "discussions"}
    onClick={() => {
      setSidebarViewMode("discussions");
      if (!showRightPanel) {
        setShowRightPanel(true);
        setMode("half"); // 50% width
      }
    }}
  >
    <MessageSquare size={18} />
    {!isMobile && <span>Discussions</span>}
    {threadCount > 0 && (
      <NotificationBadge>{threadCount}</NotificationBadge>
    )}
  </SidebarTab>
</SidebarTabsContainer>
```

#### Step 5: Render Discussions Content in Sidebar

**Location**: Sidebar content rendering (around line 2600)

```typescript
{showRightPanel && (
  <SlidingPanel
    isOpen={showRightPanel}
    width={`${getPanelWidthPercentage()}%`}
  >
    <SidebarHeader>
      {/* Header content */}
    </SidebarHeader>

    {/* Existing sidebar content for other tabs */}

    {/* NEW: Discussions content */}
    {sidebarViewMode === "discussions" && (
      <DocumentDiscussionsContent
        documentId={documentId}
        corpusId={corpusId}
      />
    )}
  </SlidingPanel>
)}
```

#### Step 6: Create DocumentDiscussionsContent Component

**File**: `frontend/src/components/discussions/DocumentDiscussionsContent.tsx`

```typescript
import React from "react";
import { useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import { ThreadList } from "./ThreadList";
import { ThreadDetail } from "./ThreadDetail";
import { CreateThreadButton } from "./CreateThreadButton";
import { selectedThreadId } from "../../graphql/cache";
import { updateThreadSelection, clearThreadSelection } from "../../utils/navigationUtils";
import styled from "styled-components";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
`;

const Title = styled.h3`
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
`;

const Content = styled.div`
  flex: 1;
  overflow-y: auto;
  min-height: 0;
`;

interface DocumentDiscussionsContentProps {
  documentId: string;
  corpusId?: string;
}

export const DocumentDiscussionsContent: React.FC<DocumentDiscussionsContentProps> = ({
  documentId,
  corpusId,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const threadId = useReactiveVar(selectedThreadId);

  const handleThreadClick = (clickedThreadId: string) => {
    updateThreadSelection(location, navigate, clickedThreadId);
  };

  const handleBack = () => {
    clearThreadSelection(location, navigate);
  };

  return (
    <Container>
      <Header>
        <Title>
          {threadId ? "Discussion Thread" : "Document Discussions"}
        </Title>
        {!threadId && <CreateThreadButton documentId={documentId} corpusId={corpusId} />}
      </Header>

      <Content>
        {threadId ? (
          <ThreadDetail
            conversationId={threadId}
            onBack={handleBack}
          />
        ) : (
          <ThreadList
            documentId={documentId}
            conversationType="THREAD"
            onThreadClick={handleThreadClick}
          />
        )}
      </Content>
    </Container>
  );
};
```

#### Step 7: Query Thread Count

**Location**: Add to existing stats query or create new hook

```typescript
// In DocumentKnowledgeBase component
const { data: threadData } = useQuery(GET_DOCUMENT_THREAD_COUNT, {
  variables: { documentId },
  skip: !documentId,
});

const threadCount = threadData?.documentThreads?.totalCount || 0;
```

**GraphQL Query:**

```typescript
export const GET_DOCUMENT_THREAD_COUNT = gql`
  query GetDocumentThreadCount($documentId: ID!) {
    documentThreads(documentId: $documentId) {
      totalCount
    }
  }
`;
```

### Integration 3: Global Discussions View

This view showcases all discussions across the platform with a rich, engaging visual design.

#### Step 1: Create Route Component

**File**: `frontend/src/components/routes/GlobalDiscussionsRoute.tsx`

```typescript
import React from "react";
import { GlobalDiscussions } from "../../views/GlobalDiscussions";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import { MetaTags } from "../widgets/MetaTags";

export const GlobalDiscussionsRoute: React.FC = () => {
  return (
    <ErrorBoundary>
      <MetaTags title="Discussions" type="discussions" />
      <GlobalDiscussions />
    </ErrorBoundary>
  );
};
```

#### Step 2: Create GlobalDiscussions View

**File**: `frontend/src/views/GlobalDiscussions.tsx`

```typescript
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, Database, FileText, Plus, Search, SlidersHorizontal } from "lucide-react";
import { ThreadList } from "../components/discussions/ThreadList";
import { CreateThreadButton } from "../components/discussions/CreateThreadButton";
import { CardLayout } from "../components/layout/CardLayout";

const Container = styled.div`
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

const Header = styled.div`
  margin-bottom: 2rem;
`;

const TitleRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
`;

const Title = styled.h1`
  font-size: 2rem;
  font-weight: 800;
  color: #0f172a;
  margin: 0;
  letter-spacing: -0.025em;

  @media (max-width: 768px) {
    font-size: 1.5rem;
  }
`;

const FilterBar = styled.div`
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
`;

const TabContainer = styled.div`
  display: flex;
  gap: 0.5rem;
  background: #f8fafc;
  padding: 0.375rem;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
`;

const Tab = styled(motion.button)<{ isActive: boolean }>`
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  border: none;
  background: ${props => props.isActive ? "white" : "transparent"};
  color: ${props => props.isActive ? "#0f172a" : "#64748b"};
  font-weight: ${props => props.isActive ? "600" : "500"};
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: ${props => props.isActive ? "0 1px 3px rgba(0,0,0,0.1)" : "none"};
  display: flex;
  align-items: center;
  gap: 0.5rem;

  &:hover {
    background: ${props => props.isActive ? "white" : "rgba(255,255,255,0.6)"};
  }
`;

const SearchInput = styled.input`
  flex: 1;
  min-width: 200px;
  padding: 0.625rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.9375rem;

  &:focus {
    outline: none;
    border-color: #4a90e2;
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
  }
`;

const FAB = styled(motion.button)`
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(74, 144, 226, 0.4);
  z-index: 100;

  &:hover {
    box-shadow: 0 12px 32px rgba(74, 144, 226, 0.5);
  }

  @media (max-width: 768px) {
    bottom: 1rem;
    right: 1rem;
  }
`;

const SectionContainer = styled(motion.div)`
  margin-bottom: 2.5rem;
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid #e2e8f0;
`;

const SectionIcon = styled.div<{ color: string }>`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: ${props => props.color};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
`;

const SectionTitle = styled.h2`
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
`;

const SectionCount = styled.span`
  font-size: 0.875rem;
  color: #64748b;
  font-weight: 500;
`;

type FilterTab = "all" | "corpus" | "document" | "general";

export const GlobalDiscussions: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  return (
    <CardLayout>
      <Container>
        <Header>
          <TitleRow>
            <Title>Discussions</Title>
          </TitleRow>

          <FilterBar>
            <TabContainer>
              <Tab
                isActive={activeTab === "all"}
                onClick={() => setActiveTab("all")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <MessageSquare size={16} />
                All
              </Tab>
              <Tab
                isActive={activeTab === "corpus"}
                onClick={() => setActiveTab("corpus")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Database size={16} />
                Corpus
              </Tab>
              <Tab
                isActive={activeTab === "document"}
                onClick={() => setActiveTab("document")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <FileText size={16} />
                Document
              </Tab>
              <Tab
                isActive={activeTab === "general"}
                onClick={() => setActiveTab("general")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <MessageSquare size={16} />
                General
              </Tab>
            </TabContainer>

            <SearchInput
              placeholder="Search discussions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </FilterBar>
        </Header>

        <AnimatePresence mode="wait">
          {(activeTab === "all" || activeTab === "corpus") && (
            <SectionContainer
              key="corpus-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <SectionHeader>
                <SectionIcon color="linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
                  <Database size={18} />
                </SectionIcon>
                <SectionTitle>Corpus Discussions</SectionTitle>
                <SectionCount>(23)</SectionCount>
              </SectionHeader>

              <ThreadList
                conversationType="THREAD"
                filterByContext="corpus"
                searchQuery={searchQuery}
                onThreadClick={(threadId, corpus) => {
                  if (corpus) {
                    navigate(`/c/${corpus.creator.slug}/${corpus.slug}/discussions/${threadId}`);
                  }
                }}
              />
            </SectionContainer>
          )}

          {(activeTab === "all" || activeTab === "document") && (
            <SectionContainer
              key="document-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <SectionHeader>
                <SectionIcon color="linear-gradient(135deg, #f093fb 0%, #f5576c 100%)">
                  <FileText size={18} />
                </SectionIcon>
                <SectionTitle>Document Discussions</SectionTitle>
                <SectionCount>(15)</SectionCount>
              </SectionHeader>

              <ThreadList
                conversationType="THREAD"
                filterByContext="document"
                searchQuery={searchQuery}
                onThreadClick={(threadId, document, corpus) => {
                  if (document && corpus) {
                    navigate(`/d/${corpus.creator.slug}/${corpus.slug}/${document.slug}?thread=${threadId}`);
                  } else if (document) {
                    navigate(`/d/${document.creator.slug}/${document.slug}?thread=${threadId}`);
                  }
                }}
              />
            </SectionContainer>
          )}

          {(activeTab === "all" || activeTab === "general") && (
            <SectionContainer
              key="general-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, delay: 0.2 }}
            >
              <SectionHeader>
                <SectionIcon color="linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
                  <MessageSquare size={18} />
                </SectionIcon>
                <SectionTitle>General Discussions</SectionTitle>
                <SectionCount>(8)</SectionCount>
              </SectionHeader>

              <ThreadList
                conversationType="THREAD"
                filterByContext="general"
                searchQuery={searchQuery}
                onThreadClick={(threadId) => {
                  navigate(`/discussions/${threadId}`);
                }}
              />
            </SectionContainer>
          )}
        </AnimatePresence>

        <FAB
          onClick={() => setShowCreateModal(true)}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
        >
          <Plus size={28} />
        </FAB>

        {showCreateModal && (
          <CreateThreadModal onClose={() => setShowCreateModal(false)} />
        )}
      </Container>
    </CardLayout>
  );
};
```

### Feature: @ Mentions for Resources

The @ mention system allows users to reference corpuses, documents, and corpus documents in messages with autocomplete and clickable navigation.

#### Backend: Mentioned Resources GraphQL

**File**: `config/graphql/graphene_types.py`

```python
class MentionedResourceType(graphene.ObjectType):
    """
    Represents a corpus or document mentioned in a message using @ syntax.

    Examples:
      @corpus:legal-contracts
      @document:contract-template
      @corpus:legal-contracts/document:contract-template
    """
    type = graphene.String(required=True)  # "corpus" or "document"
    id = graphene.ID(required=True)
    slug = graphene.String(required=True)
    title = graphene.String(required=True)
    url = graphene.String(required=True)

    # Optional corpus context for documents
    corpus = graphene.Field(lambda: MentionedResourceType)

class ChatMessageType(DjangoObjectType):
    # ... existing fields

    mentioned_resources = graphene.List(
        MentionedResourceType,
        description="Corpuses and documents mentioned in this message using @ syntax"
    )

    def resolve_mentioned_resources(root, info):
        """
        Parse content for @mentions and return structured resource references.

        Patterns:
          @corpus:slug → Corpus
          @document:slug → Document
          @corpus:corpus-slug/document:doc-slug → Document in Corpus
        """
        import re
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        content = root.content or ""
        mentions = []

        # Pattern: @corpus:slug/document:slug
        corpus_doc_pattern = r'@corpus:([a-z0-9-]+)/document:([a-z0-9-]+)'
        for corpus_slug, doc_slug in re.findall(corpus_doc_pattern, content):
            try:
                corpus = Corpus.objects.get(slug=corpus_slug)
                document = Document.objects.filter(
                    slug=doc_slug,
                    corpus=corpus
                ).first()

                if document and corpus:
                    mentions.append(MentionedResourceType(
                        type="document",
                        id=document.id,
                        slug=document.slug,
                        title=document.title,
                        url=f"/d/{corpus.creator.slug}/{corpus.slug}/{document.slug}",
                        corpus=MentionedResourceType(
                            type="corpus",
                            id=corpus.id,
                            slug=corpus.slug,
                            title=corpus.title,
                            url=f"/c/{corpus.creator.slug}/{corpus.slug}"
                        )
                    ))
            except (Corpus.DoesNotExist, Document.DoesNotExist):
                continue

        # Pattern: @corpus:slug
        corpus_pattern = r'@corpus:([a-z0-9-]+)'
        for slug in re.findall(corpus_pattern, content):
            # Skip if already matched in corpus/document pattern
            if f"@corpus:{slug}/document:" in content:
                continue

            try:
                corpus = Corpus.objects.get(slug=slug)
                mentions.append(MentionedResourceType(
                    type="corpus",
                    id=corpus.id,
                    slug=corpus.slug,
                    title=corpus.title,
                    url=f"/c/{corpus.creator.slug}/{corpus.slug}"
                ))
            except Corpus.DoesNotExist:
                continue

        # Pattern: @document:slug
        doc_pattern = r'@document:([a-z0-9-]+)'
        for slug in re.findall(doc_pattern, content):
            # Skip if already matched in corpus/document pattern
            if f"/document:{slug}" in content:
                continue

            try:
                document = Document.objects.get(slug=slug)
                url = f"/d/{document.creator.slug}/{document.slug}"

                # Include corpus context if available
                corpus = document.corpus.first() if hasattr(document, 'corpus') else None

                mentions.append(MentionedResourceType(
                    type="document",
                    id=document.id,
                    slug=document.slug,
                    title=document.title,
                    url=url,
                    corpus=MentionedResourceType(
                        type="corpus",
                        id=corpus.id,
                        slug=corpus.slug,
                        title=corpus.title,
                        url=f"/c/{corpus.creator.slug}/{corpus.slug}"
                    ) if corpus else None
                ))
            except Document.DoesNotExist:
                continue

        return mentions
```

#### Frontend: TipTap Mention Extension

**File**: `frontend/src/components/discussions/MessageComposer.tsx`

**Add mention extension configuration:**

```typescript
import { Mention } from "@tiptap/extension-mention";
import { ReactRenderer } from "@tiptap/react";
import { SuggestionOptions } from "@tiptap/suggestion";
import tippy, { Instance as TippyInstance } from "tippy.js";
import { MentionList } from "./MentionList";

// GraphQL query for mention autocomplete
const SEARCH_RESOURCES_FOR_MENTION = gql`
  query SearchResourcesForMention($query: String!) {
    searchCorpuses(textSearch: $query, limit: 5) {
      edges {
        node {
          id
          slug
          title
          creator { slug }
        }
      }
    }
    searchDocuments(textSearch: $query, limit: 5) {
      edges {
        node {
          id
          slug
          title
          creator { slug }
          corpus {
            id
            slug
            creator { slug }
          }
        }
      }
    }
  }
`;

const suggestion: Omit<SuggestionOptions, "editor"> = {
  items: async ({ query }) => {
    // Query both corpuses and documents
    const { data } = await apolloClient.query({
      query: SEARCH_RESOURCES_FOR_MENTION,
      variables: { query },
    });

    const corpuses = data?.searchCorpuses?.edges?.map((e: any) => ({
      type: "corpus",
      id: e.node.id,
      slug: e.node.slug,
      title: e.node.title,
      creatorSlug: e.node.creator.slug,
    })) || [];

    const documents = data?.searchDocuments?.edges?.map((e: any) => ({
      type: "document",
      id: e.node.id,
      slug: e.node.slug,
      title: e.node.title,
      creatorSlug: e.node.creator.slug,
      corpusSlug: e.node.corpus?.slug,
      corpusCreatorSlug: e.node.corpus?.creator?.slug,
    })) || [];

    return [...corpuses, ...documents];
  },

  render: () => {
    let component: ReactRenderer;
    let popup: TippyInstance[];

    return {
      onStart: (props) => {
        component = new ReactRenderer(MentionList, {
          props,
          editor: props.editor,
        });

        popup = tippy("body", {
          getReferenceClientRect: props.clientRect as any,
          appendTo: () => document.body,
          content: component.element,
          showOnCreate: true,
          interactive: true,
          trigger: "manual",
          placement: "bottom-start",
        });
      },

      onUpdate(props) {
        component.updateProps(props);

        popup[0].setProps({
          getReferenceClientRect: props.clientRect as any,
        });
      },

      onKeyDown(props) {
        if (props.event.key === "Escape") {
          popup[0].hide();
          return true;
        }
        return component.ref?.onKeyDown(props);
      },

      onExit() {
        popup[0].destroy();
        component.destroy();
      },
    };
  },
};

// In extensions array
const extensions = [
  // ... other extensions

  Mention.configure({
    HTMLAttributes: {
      class: "mention",
    },
    suggestion,
    renderLabel({ node }) {
      // Format label based on resource type
      const type = node.attrs.type;
      const slug = node.attrs.slug;

      if (type === "corpus") {
        return `@corpus:${slug}`;
      } else if (type === "document") {
        const corpusSlug = node.attrs.corpusSlug;
        if (corpusSlug) {
          return `@corpus:${corpusSlug}/document:${slug}`;
        }
        return `@document:${slug}`;
      }
      return `@${slug}`;
    },
  }),
];
```

#### Frontend: Mention Dropdown Component

**File**: `frontend/src/components/discussions/MentionList.tsx`

```typescript
import React, { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import styled from "styled-components";
import { Database, FileText } from "lucide-react";

const Container = styled.div`
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  max-height: 300px;
  overflow-y: auto;
  min-width: 300px;
`;

const Item = styled.div<{ isSelected: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  background: ${props => props.isSelected ? "#f8fafc" : "white"};
  border-bottom: 1px solid #f1f5f9;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: #f8fafc;
  }
`;

const Icon = styled.div<{ type: string }>`
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: ${props =>
    props.type === "corpus"
      ? "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
      : "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"
  };
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
`;

const Content = styled.div`
  flex: 1;
  min-width: 0;
`;

const Title = styled.div`
  font-weight: 600;
  color: #0f172a;
  font-size: 0.9375rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Subtitle = styled.div`
  font-size: 0.8125rem;
  color: #64748b;
  margin-top: 0.125rem;
`;

interface MentionListProps {
  items: any[];
  command: (item: any) => void;
}

export const MentionList = forwardRef((props: MentionListProps, ref) => {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const selectItem = (index: number) => {
    const item = props.items[index];
    if (item) {
      props.command(item);
    }
  };

  const upHandler = () => {
    setSelectedIndex((selectedIndex + props.items.length - 1) % props.items.length);
  };

  const downHandler = () => {
    setSelectedIndex((selectedIndex + 1) % props.items.length);
  };

  const enterHandler = () => {
    selectItem(selectedIndex);
  };

  useEffect(() => setSelectedIndex(0), [props.items]);

  useImperativeHandle(ref, () => ({
    onKeyDown: ({ event }: { event: KeyboardEvent }) => {
      if (event.key === "ArrowUp") {
        upHandler();
        return true;
      }
      if (event.key === "ArrowDown") {
        downHandler();
        return true;
      }
      if (event.key === "Enter") {
        enterHandler();
        return true;
      }
      return false;
    },
  }));

  return (
    <Container>
      {props.items.map((item, index) => (
        <Item
          key={item.id}
          isSelected={index === selectedIndex}
          onClick={() => selectItem(index)}
        >
          <Icon type={item.type}>
            {item.type === "corpus" ? <Database size={16} /> : <FileText size={16} />}
          </Icon>
          <Content>
            <Title>{item.title}</Title>
            <Subtitle>
              {item.type === "corpus"
                ? `@corpus:${item.slug}`
                : item.corpusSlug
                  ? `@corpus:${item.corpusSlug}/document:${item.slug}`
                  : `@document:${item.slug}`
              }
            </Subtitle>
          </Content>
        </Item>
      ))}
    </Container>
  );
});

MentionList.displayName = "MentionList";
```

#### Frontend: Render Mentions as Links

**File**: `frontend/src/components/discussions/MessageContent.tsx`

```typescript
import React from "react";
import styled from "styled-components";
import { Database, FileText } from "lucide-react";
import { SafeMarkdown } from "../markdown/SafeMarkdown";
import { useNavigate } from "react-router-dom";

const MentionChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  color: #0f172a;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
    border-color: #4a90e2;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(74, 144, 226, 0.2);
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

interface MessageContentProps {
  content: string;
  mentionedResources?: Array<{
    type: "corpus" | "document";
    id: string;
    slug: string;
    title: string;
    url: string;
    corpus?: {
      slug: string;
      title: string;
      url: string;
    };
  }>;
}

export const MessageContent: React.FC<MessageContentProps> = ({
  content,
  mentionedResources = [],
}) => {
  const navigate = useNavigate();

  // Replace @mentions in content with clickable chips
  let processedContent = content;

  mentionedResources.forEach((resource) => {
    let pattern = "";

    if (resource.type === "corpus") {
      pattern = `@corpus:${resource.slug}`;
    } else if (resource.type === "document") {
      if (resource.corpus) {
        pattern = `@corpus:${resource.corpus.slug}/document:${resource.slug}`;
      } else {
        pattern = `@document:${resource.slug}`;
      }
    }

    const replacement = `<span class="mention" data-type="${resource.type}" data-url="${resource.url}" data-title="${resource.title}">${pattern}</span>`;
    processedContent = processedContent.replace(pattern, replacement);
  });

  const handleMentionClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains("mention")) {
      const url = target.getAttribute("data-url");
      const title = target.getAttribute("data-title");
      const type = target.getAttribute("data-type");

      if (url) {
        navigate(url);
      }
    }
  };

  return (
    <div onClick={handleMentionClick}>
      <SafeMarkdown content={processedContent} />
    </div>
  );
};
```

**Add CSS for mention styling:**

```css
.mention {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  color: #0f172a;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mention:hover {
  background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
  border-color: #4a90e2;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(74, 144, 226, 0.2);
}
```

### Conversation Types: Backend Agnosticism

The conversation system supports multiple interaction modes determined by access method (GraphQL vs WebSocket) rather than hard-coded types.

#### Backend: Flexible Conversation Model

**File**: `opencontractserver/conversations/models.py`

```python
class Conversation(BaseOCModel):
    """
    Agnostic conversation model that supports multiple interaction modes.

    Access Method determines behavior:
      - GraphQL: Traditional threaded discussions (THREAD/COMMENT)
      - WebSocket: Real-time chat (CHAT)

    conversationType field is a hint, but backend doesn't enforce strict behavior.
    Frontend adapts UI based on context, not type checks.
    """

    class ConversationType(models.TextChoices):
        THREAD = "THREAD", "Thread (Forum-style discussion with title)"
        COMMENT = "COMMENT", "Comment (Simple comment, no title)"
        CHAT = "CHAT", "Chat (Real-time conversation)"

    conversation_type = models.CharField(
        max_length=10,
        choices=ConversationType.choices,
        default=ConversationType.THREAD,
        help_text="Hint for frontend UI, not enforced backend behavior"
    )

    # Title/description optional - COMMENT type might not use them
    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional - used for THREAD, not COMMENT/CHAT"
    )

    description = models.TextField(
        blank=True,
        help_text="Optional - used for THREAD, not COMMENT/CHAT"
    )

    # Context fields determine scope
    chat_with_corpus = models.ForeignKey(
        "corpuses.Corpus",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conversations",
    )

    chat_with_document = models.ForeignKey(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conversations",
    )

    # ... other fields
```

**Key Design Principles:**

1. **Type is a Hint, Not Enforcement**: Backend doesn't enforce different behavior for THREAD vs COMMENT vs CHAT. Frontend decides based on context.

2. **Access Method Determines Interaction**:
   - GraphQL queries/mutations → Traditional request/response
   - WebSocket subscriptions (future) → Real-time updates
   - Same models, different access patterns

3. **Optional Fields**: Title/description are optional. COMMENT type conversations might not use them. Frontend adapts.

4. **Context-Based**: `chat_with_corpus`, `chat_with_document` fields determine scope. A conversation can be corpus-level, document-level, or general.

#### Frontend: Adaptive UI

**File**: `frontend/src/components/discussions/ThreadList.tsx`

```typescript
// ThreadList adapts based on conversationType prop
interface ThreadListProps {
  corpusId?: string;
  documentId?: string;
  conversationType?: "THREAD" | "COMMENT" | "CHAT";
  // ...
}

// When conversationType="COMMENT", show simpler cards without title
// When conversationType="THREAD", show full thread cards with title/description
// When conversationType="CHAT" (future), show chat-style UI with avatars/timestamps

// But backend doesn't care - it's all Conversation model
```

**File**: `frontend/src/components/discussions/CreateThreadForm.tsx`

```typescript
// Form adapts based on context
interface CreateThreadFormProps {
  corpusId?: string;
  documentId?: string;
  conversationType?: "THREAD" | "COMMENT";
  // ...
}

// When conversationType="COMMENT":
//   - Hide title/description fields
//   - Show simple content editor
//   - Submit as COMMENT type
//
// When conversationType="THREAD":
//   - Show title/description fields
//   - Show full editor with formatting
//   - Submit as THREAD type
//
// Backend stores both in same Conversation model
```

### Implementation Checklist

This checklist maps to the pending issues as follows:
- **Phase 1-2**: Issue #621 (Corpus Integration)
- **Phase 3**: Issue #622 (Document Integration)
- **Phase 4**: Issue #623 (Global View)
- **Phase 5**: Issue #623 (@ Mentions, same issue)
- **Phase 6**: Refinement across #621-623
- **Phase 7**: Final polish for all integration work

---

**Phase 1: Routing Infrastructure** (Issue #621)
- [ ] Add `selectedThreadId` reactive var to `cache.ts`
- [ ] Update `CentralRouteManager.tsx` Phase 2 for `?thread=` param
- [ ] Update `CentralRouteManager.tsx` Phase 4 for thread URL sync
- [ ] Add utility functions to `navigationUtils.ts`
- [ ] Add route to `App.tsx` for `/c/:user/:corpus/discussions/:threadId`
- [ ] Add route to `App.tsx` for `/discussions`

**Phase 2: Corpus Integration** (Issue #621)
- [ ] Add `totalThreads` to `GET_CORPUS_STATS` query
- [ ] Add Discussions tab to Corpuses sidebar navigation
- [ ] Create `CorpusDiscussionsView.tsx` component
- [ ] Wire up CreateThreadButton in corpus context
- [ ] Test full-page thread navigation

**Phase 3: Document Integration** (Issue #622)
- [ ] Add `discussions` to `SidebarViewMode` type
- [ ] Add Discussions tab to DocumentKnowledgeBase sidebar
- [ ] Create `DocumentDiscussionsContent.tsx` component
- [ ] Implement auto-open sidebar on `?thread=` param
- [ ] Add `GET_DOCUMENT_THREAD_COUNT` query
- [ ] Wire up CreateThreadButton in document context
- [ ] Test sidebar thread navigation

**Phase 4: Global View** (Issue #623)
- [ ] Create `GlobalDiscussionsRoute.tsx`
- [ ] Create `GlobalDiscussions.tsx` view
- [ ] Implement tabbed sections (All/Corpus/Document/General)
- [ ] Add search/filter functionality
- [ ] Implement FAB for creating threads
- [ ] Add smooth animations and transitions
- [ ] Test navigation from global view to context views

**Phase 5: @ Mentions** (Issue #623)
- [ ] Add `MentionedResourceType` to GraphQL schema
- [ ] Implement `resolve_mentioned_resources` in backend
- [ ] Add `SEARCH_RESOURCES_FOR_MENTION` GraphQL query
- [ ] Configure TipTap Mention extension
- [ ] Create `MentionList.tsx` dropdown component
- [ ] Implement mention rendering in `MessageContent.tsx`
- [ ] Add mention click navigation
- [ ] Test autocomplete and navigation

**Phase 6: Conversation Type Flexibility** (Refinement across #621-623)
- [ ] Review backend Conversation model for flexibility
- [ ] Implement adaptive UI in ThreadList
- [ ] Implement adaptive UI in CreateThreadForm
- [ ] Test THREAD vs COMMENT types
- [ ] Document WebSocket integration path for CHAT type (future)

**Phase 7: Polish & Testing** (Final polish for #621-623)
- [ ] Add loading states to all views
- [ ] Add error boundaries
- [ ] Implement keyboard shortcuts
- [ ] Test mobile responsive design
- [ ] Write Playwright component tests
- [ ] Performance optimization (virtual scrolling, memoization)
- [ ] Accessibility audit (ARIA labels, keyboard nav)

---

## Quick Reference: Where to Find Everything

This section provides a quick lookup for developers working on specific issues.

### For Issue #621 (Corpus Integration)

**Primary Specifications**:
- [Routing Architecture](#routing-architecture) - Add reactive vars and route handling
- [Corpus View Integration](#corpus-view-integration) - Step-by-step implementation
- [Implementation Checklist Phase 1-2](#implementation-checklist-1) - Detailed tasks

**Reusable Components** (from #573-577):
- [ThreadList.tsx](#1-threadlisttsx-issue-573) - Main thread list
- [ThreadDetail.tsx](#3-threaddetailtsx-issue-573) - Thread detail view
- [CreateThreadForm.tsx](#component-to-issue-mapping) - From Issue #574

**Reference Material**:
- [State Management Strategy](#state-management-strategy) - Jotai atoms
- [Testing Strategy](#testing-strategy) - Test patterns
- [Performance Considerations](#performance-considerations) - Optimization
- [Accessibility Requirements](#accessibility-requirements) - A11y compliance

### For Issue #622 (Document Integration)

**Primary Specifications**:
- [DocumentKnowledgeBase Integration](#documentknowledgebase-integration) - Step-by-step implementation
- [Implementation Checklist Phase 3](#implementation-checklist-1) - Detailed tasks

**Reusable Components** (from #573-577):
- [ThreadList.tsx](#1-threadlisttsx-issue-573) - Sidebar thread list
- [ThreadDetail.tsx](#3-threaddetailtsx-issue-573) - Thread detail in sidebar
- [CreateThreadForm.tsx](#component-to-issue-mapping) - From Issue #574

**Reference Material**:
- [State Management Strategy](#state-management-strategy) - Sidebar state patterns
- [Testing Strategy](#testing-strategy) - Sidebar integration tests
- [Code Examples & Patterns](#code-examples--patterns) - Batched updates for sidebar

### For Issue #623 (Global View + @ Mentions)

**Primary Specifications**:
- [Global Discussions View](#global-discussions-view) - Complete component specs
- [@ Mentions Feature](#-mentions-feature) - TipTap configuration & backend parsing
- [Implementation Checklist Phase 4-5](#implementation-checklist-1) - Detailed tasks

**Reusable Components** (from #573-577):
- [ThreadList.tsx](#1-threadlisttsx-issue-573) - Global thread list
- [MessageComposer.tsx](#component-to-issue-mapping) - Enhanced with mentions (Issue #574)
- All components from #573-577

**Reference Material**:
- [State Management Strategy](#state-management-strategy) - Global filter atoms
- [Testing Strategy](#testing-strategy) - Full-page view tests
- [Code Examples & Patterns](#code-examples--patterns) - Animations, autocomplete
- [Performance Considerations](#performance-considerations) - Virtual scrolling

### For All Issues (#578-580, #621-623)

**Cross-Cutting Concerns**:
- [Architecture Overview](#architecture-overview) - Overall system design
- [Component Specifications](#component-specifications) - All foundation components
- [Data Flow Patterns](#data-flow-patterns) - GraphQL patterns
- [Performance Considerations](#performance-considerations) - Required for all views
- [Accessibility Requirements](#accessibility-requirements) - Required for all components

**Implementation Process**:
1. Review [Pending Issues](#pending-issues-roadmap-to-full-integration) for your issue
2. Check [Branch Dependency Tree](#branch-dependency-tree) for dependencies
3. Follow [Implementation Checklist](#implementation-checklist-1) phases
4. Reference [Component-to-Issue Mapping](#component-to-issue-mapping) for reusable parts
5. Apply patterns from [Code Examples & Patterns](#code-examples--patterns)

---

## Conclusion

This implementation guide provides a comprehensive roadmap for building the commenting and discussion system frontend. Follow this guide systematically, and each component will integrate seamlessly with the existing backend APIs.

**Key Takeaways**:
- Build reusable components from the start
- Test thoroughly with Playwright
- Follow existing patterns in the codebase (especially routing mantra)
- Keep accessibility in mind
- Optimize for performance with large datasets
- Leverage @ mentions for rich cross-referencing
- Design for flexibility (conversation types, access methods)

Ready to implement! 🚀
