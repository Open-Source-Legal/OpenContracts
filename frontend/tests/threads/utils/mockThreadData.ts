import {
  ConversationType,
  ChatMessageType,
} from "../../../src/types/graphql-api";

/**
 * Mock data factories for thread testing
 */

export function createMockThread(
  overrides?: Partial<ConversationType>
): ConversationType {
  const baseThread: ConversationType = {
    id: "thread-1",
    conversationType: "THREAD",
    title: "Test Thread",
    description: "This is a test thread description",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      slug: "testuser",
      name: "Test User",
      firstName: "Test",
      lastName: "User",
      phone: null,
      isUsageCapped: false,
    },
    chatWithCorpus: {
      id: "corpus-1",
      title: "Test Corpus",
      slug: "test-corpus",
      description: "Test corpus description",
      icon: "book",
      isPublic: false,
      myPermissions: ["READ", "WRITE"],
    },
    chatWithDocument: null,
    chatMessages: {
      totalCount: 5,
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: "",
        endCursor: "",
      },
      edges: [],
    },
    allMessages: [],
    isPublic: false,
    myPermissions: ["READ", "WRITE"],
    isPinned: false,
    isLocked: false,
    lockedBy: null,
    lockedAt: null,
    pinnedBy: null,
    pinnedAt: null,
    deletedAt: null,
  };

  return { ...baseThread, ...overrides };
}

export function createMockMessage(
  overrides?: Partial<ChatMessageType>
): ChatMessageType {
  const baseMessage: ChatMessageType = {
    id: "message-1",
    msgType: "HUMAN",
    agentType: null,
    content: "This is a test message content.",
    data: null,
    state: "COMPLETED",
    createdAt: new Date().toISOString(),
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      slug: "testuser",
      name: "Test User",
      firstName: "Test",
      lastName: "User",
      phone: null,
      isUsageCapped: false,
    },
    conversation: createMockThread(),
    sourceDocument: null,
    sourceAnnotations: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: "",
        endCursor: "",
      },
      totalCount: 0,
    },
    createdAnnotations: {
      edges: [],
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: "",
        endCursor: "",
      },
      totalCount: 0,
    },
    isPublic: false,
    myPermissions: ["READ"],
    parentMessage: null,
    replies: [],
    upvoteCount: 0,
    downvoteCount: 0,
    userVote: null,
    deletedAt: null,
    deletedBy: null,
  };

  return { ...baseMessage, ...overrides };
}

/**
 * Creates a thread with nested messages for testing tree rendering
 */
export function createMockThreadWithMessages(): ConversationType {
  const thread = createMockThread({ id: "thread-with-messages" });

  const message1 = createMockMessage({
    id: "msg-1",
    content: "First message",
    parentMessage: null,
  });

  const message2 = createMockMessage({
    id: "msg-2",
    content: "Reply to first message",
    parentMessage: { id: "msg-1" } as ChatMessageType,
  });

  const message3 = createMockMessage({
    id: "msg-3",
    content: "Another reply to first message",
    parentMessage: { id: "msg-1" } as ChatMessageType,
  });

  const message4 = createMockMessage({
    id: "msg-4",
    content: "Nested reply",
    parentMessage: { id: "msg-2" } as ChatMessageType,
  });

  thread.allMessages = [message1, message2, message3, message4];
  thread.chatMessages = {
    ...thread.chatMessages,
    totalCount: 4,
  };

  return thread;
}
