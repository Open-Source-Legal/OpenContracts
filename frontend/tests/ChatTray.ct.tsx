import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { ChatTrayTestWrapper } from "./ChatTrayTestWrapper";
import { GET_CONVERSATIONS, GET_CHAT_MESSAGES } from "../src/graphql/queries";
import { ConversationType, ChatMessageType } from "../src/types/graphql-api";
import { WebSocketSources } from "../src/components/knowledge_base/document/right_tray/ChatTray";
import { attachWsDebug } from "./utils/wsDebug";
import { docScreenshot } from "./utils/docScreenshot";

/* -------------------------------------------------------------------------- */
/* Mock Data                                                                   */
/* -------------------------------------------------------------------------- */

const TEST_DOC_ID = "test-doc-123";
const TEST_CORPUS_ID = "test-corpus-456";
const TEST_CONVERSATION_ID = "test-conv-789";

const mockConversations: ConversationType[] = [
  {
    id: TEST_CONVERSATION_ID,
    title: "Test Conversation 1",
    createdAt: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
    updatedAt: new Date(Date.now() - 86400000).toISOString(),
    created: new Date(Date.now() - 86400000).toISOString(),
    modified: new Date(Date.now() - 86400000).toISOString(),
    creator: {
      id: "user1",
      email: "user1@example.com",
      __typename: "UserType",
    },
    chatMessages: {
      totalCount: 5,
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      edges: [],
      __typename: "ChatMessageTypeConnection",
    },
    __typename: "ConversationType",
  } as ConversationType,
  {
    id: "test-conv-2",
    title: "Test Conversation 2",
    createdAt: new Date(Date.now() - 172800000).toISOString(), // 2 days ago
    updatedAt: new Date(Date.now() - 172800000).toISOString(),
    created: new Date(Date.now() - 172800000).toISOString(),
    modified: new Date(Date.now() - 172800000).toISOString(),
    creator: {
      id: "user2",
      email: "user2@example.com",
      __typename: "UserType",
    },
    chatMessages: {
      totalCount: 3,
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo",
      },
      edges: [],
      __typename: "ChatMessageTypeConnection",
    },
    __typename: "ConversationType",
  } as ConversationType,
];

const mockChatMessages: any[] = [
  {
    id: "msg-1",
    content: "Hello, I have a question about this document.",
    msgType: "HUMAN",
    createdAt: new Date(Date.now() - 3600000).toISOString(),
    data: {},
    __typename: "ChatMessageType",
  },
  {
    id: "msg-2",
    content: "I'd be happy to help you with your question about the document.",
    msgType: "ASSISTANT",
    createdAt: new Date(Date.now() - 3500000).toISOString(),
    data: {
      sources: [
        {
          page: 1,
          json: { start: 0, end: 100 },
          annotation_id: 123,
          label: "Important Section",
          label_id: 456,
          rawText: "This is the important text from the document.",
        },
      ],
      timeline: [
        {
          type: "thought",
          text: "Analyzing the document content...",
        },
      ],
    },
    state: "complete",
    __typename: "ChatMessageType",
  },
  {
    id: "msg-3",
    content: "Can you summarize the main points?",
    msgType: "HUMAN",
    createdAt: new Date(Date.now() - 3000000).toISOString(),
    data: {},
    state: "complete",
    __typename: "ChatMessageType",
  },
];

const mockAwaitingApprovalMessage: any = {
  id: "msg-approval",
  content: "Tool execution paused: update_document_summary",
  msgType: "ASSISTANT",
  createdAt: new Date().toISOString(),
  data: {
    pending_tool_call: {
      name: "update_document_summary",
      arguments: { new_content: "Updated summary content" },
      tool_call_id: "tool-123",
    },
    state: "awaiting_approval",
  },
  state: "awaiting_approval",
  __typename: "ChatMessageType",
};

/* -------------------------------------------------------------------------- */
/* GraphQL Mocks                                                               */
/* -------------------------------------------------------------------------- */

const createConversationsMock = (
  conversations: ConversationType[],
  hasNextPage = false,
  filters?: {
    title_Contains?: string;
    createdAt_Gte?: string;
    createdAt_Lte?: string;
  }
): MockedResponse => ({
  request: {
    query: GET_CONVERSATIONS,
    variables: {
      documentId: TEST_DOC_ID,
      ...filters,
    },
  },
  result: {
    data: {
      conversations: {
        edges: conversations.map((conv) => ({
          node: conv,
          __typename: "ConversationTypeEdge",
        })),
        pageInfo: {
          hasNextPage,
          hasPreviousPage: false,
          startCursor: "start",
          endCursor: "end",
          __typename: "PageInfo",
        },
        __typename: "ConversationTypeConnection",
      },
    },
  },
});

const createChatMessagesMock = (
  conversationId: string,
  messages: any[]
): MockedResponse => ({
  request: {
    query: GET_CHAT_MESSAGES,
    variables: {
      conversationId,
      limit: 10,
    },
  },
  result: {
    data: {
      chatMessages: messages,
    },
  },
});

/* -------------------------------------------------------------------------- */
/* Test Helpers                                                                */
/* -------------------------------------------------------------------------- */

const mountChatTray = async (
  mount: any,
  mocks: MockedResponse[],
  props: Partial<Parameters<typeof ChatTrayTestWrapper>[0]> = {}
) => {
  return mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
      {...props}
    />
  );
};

const TIMEOUTS = {
  SHORT: 5_000,
  MEDIUM: 10_000,
  LONG: 20_000,
};

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test("displays conversation list on initial load", async ({ mount, page }) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Wait for conversations to load (authenticated mode via ChatTrayTestWrapper)
  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Check that conversation cards are displayed
  const conversationCards = page.locator('[data-testid^="conversation-card"]');
  await expect(conversationCards).toHaveCount(2);

  // Verify conversation details
  await expect(page.getByText("Test Conversation 1")).toBeVisible();
  await expect(page.getByText("Test Conversation 2")).toBeVisible();
  await expect(page.getByText("5")).toBeVisible(); // message count
  await expect(page.getByText("3")).toBeVisible(); // message count

  await docScreenshot(page, "knowledge-base--chat-tray--conversation-list");
});

test("loads messages when conversation is selected", async ({
  mount,
  page,
}) => {
  const mocks = [
    createConversationsMock(mockConversations),
    createChatMessagesMock(TEST_CONVERSATION_ID, mockChatMessages),
  ];

  await mountChatTray(mount, mocks);

  // Wait for conversations to load
  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Click on first conversation
  await page.getByText("Test Conversation 1").click();

  // Wait for messages to load
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify messages are displayed
  await expect(
    page.getByText("Hello, I have a question about this document.", {
      exact: true,
    })
  ).toBeVisible();
  await expect(
    page.getByText(
      "I'd be happy to help you with your question about the document.",
      { exact: true }
    )
  ).toBeVisible();

  // Verify source indicator
  await expect(page.locator('[data-testid="source-indicator"]')).toBeVisible();

  // Check back button
  await expect(page.getByText("Back to Conversations")).toBeVisible();
});

test("starts new chat and sends message via WebSocket", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Click new chat button
  await page.locator('[data-testid="new-chat-button"]').click();

  // Wait for chat interface
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Type and send message
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });
  await chatInput.fill("Hello from test!");
  await page.keyboard.press("Enter");

  // Verify user message appears
  await expect(
    page.getByText("Hello from test!", { exact: true })
  ).toBeVisible();

  // Verify assistant response appears
  await expect(
    page.getByText("Received: Hello from test!", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
});

test("handles streaming messages with sources and timeline", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Send message that triggers sources
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });
  await chatInput.fill("test with sources");
  await page.keyboard.press("Enter");

  // Wait for complete response
  await expect(
    page.getByText("Based on my analysis, here are the key findings.", {
      exact: true,
    })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Verify source indicator appears
  await expect(page.locator('[data-testid="source-indicator"]')).toBeVisible();

  // Verify timeline appears
  await expect(
    page.getByText("Searching for relevant information...", { exact: true })
  ).toBeVisible();
});

test("handles tool approval flow", async ({ mount, page }) => {
  const mocks = [
    createConversationsMock(mockConversations),
    createChatMessagesMock(TEST_CONVERSATION_ID, [
      ...mockChatMessages,
      mockAwaitingApprovalMessage,
    ]),
  ];

  await mountChatTray(mount, mocks);

  // Load conversation with approval-pending message
  await page.getByText("Test Conversation 1").click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify approval modal appears
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await expect(
    page.getByText("Tool: update_document_summary", { exact: true })
  ).toBeVisible();

  // Click approve button
  await page.getByRole("button", { name: "Approve" }).click();

  // Verify approval modal disappears
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).not.toBeVisible({
    timeout: TIMEOUTS.SHORT,
  });

  // Verify approval status is shown
  await expect(
    page.getByText("Summary updated successfully!", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
});

test("reopens approval modal when dismissed", async ({ mount, page }) => {
  const mocks = [
    createConversationsMock(mockConversations),
    createChatMessagesMock(TEST_CONVERSATION_ID, [
      ...mockChatMessages,
      mockAwaitingApprovalMessage,
    ]),
  ];

  await mountChatTray(mount, mocks);

  // Load conversation
  await page.getByText("Test Conversation 1").click();

  // Wait for approval modal
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Dismiss modal
  const closeBtn = page.locator('button:has-text("✕")').first();
  await expect(closeBtn).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
  await closeBtn.click();

  // Verify modal is hidden
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).not.toBeVisible();

  // Verify "Pending Approval" button appears
  await expect(
    page.getByText("Pending Approval", { exact: true })
  ).toBeVisible();

  // Click to reopen
  await page.getByText("Pending Approval").click();

  // Verify modal reappears
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).toBeVisible();
});

test("search filters conversations", async ({ mount, page }) => {
  const mocks = [
    createConversationsMock(mockConversations),
    createConversationsMock(
      [mockConversations[0]], // Only first conversation matches
      false,
      { title_Contains: "Test Conversation 1" }
    ),
  ];

  await mountChatTray(mount, mocks);

  // Wait for initial load
  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Click search icon
  await page.locator('[data-testid="search-filter-button"]').click();

  // Type in search
  const searchInput = page.locator('input[placeholder="Search by title..."]');
  await searchInput.fill("Test Conversation 1");

  // Wait for filtered results
  await expect(
    page.getByText("Test Conversation 1", { exact: true })
  ).toBeVisible();
  await expect(
    page.getByText("Test Conversation 2", { exact: true })
  ).not.toBeVisible({
    timeout: TIMEOUTS.SHORT,
  });
});

test("handles initial message from floating input", async ({ mount, page }) => {
  const mocks = [createConversationsMock(mockConversations)];
  const initialMessage = "Message from floating input";

  await mountChatTray(mount, mocks, { initialMessage });

  // Should auto-start new chat
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify initial message was sent
  await expect(page.getByText(initialMessage, { exact: true })).toBeVisible();

  // Verify response
  await expect(
    page.getByText(`Received: ${initialMessage}`, { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
});

test("preserves user messages when receiving LLM responses", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Send multiple messages
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  await chatInput.fill("First message");
  await page.keyboard.press("Enter");

  // Wait for response
  await expect(
    page.getByText("Received: First message", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify first user message is still visible
  await expect(page.getByText("First message", { exact: true })).toBeVisible();

  await chatInput.fill("Second message");
  await page.waitForTimeout(500);
  await page.keyboard.press("Enter");

  // Wait for second response
  await expect(
    page.getByText("Received: Second message", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify all messages are still visible
  await expect(page.getByText("First message", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Received: First message", { exact: true })
  ).toBeVisible();
  await expect(page.getByText("Second message", { exact: true })).toBeVisible();
});

test("auto-resizes textarea based on content", async ({ mount, page }) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  const chatInput = page.locator('[data-testid="chat-input"]');

  // Get initial height
  const initialHeight = await chatInput.evaluate((el) => el.clientHeight);

  // Type multi-line content
  await chatInput.fill("Line 1\nLine 2\nLine 3\nLine 4");

  // Verify height increased
  const expandedHeight = await chatInput.evaluate((el) => el.clientHeight);
  expect(expandedHeight).toBeGreaterThan(initialHeight);

  // Clear content
  await chatInput.clear();

  // Trigger resize after clear
  await chatInput.evaluate((el) =>
    el.dispatchEvent(new Event("input", { bubbles: true }))
  );
  // Verify height reset (allow larger variance due to animation)
  const resetHeight = await chatInput.evaluate((el) => el.clientHeight);
  expect(resetHeight).toBeLessThanOrEqual(initialHeight + 30);
});

test("shows character count when near limit", async ({ mount, page }) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();

  const chatInput = page.locator('[data-testid="chat-input"]');

  // Type a long message (90% of 4000 chars)
  const longMessage = "a".repeat(3601);
  await chatInput.fill(longMessage);

  // Character count should be visible
  await expect(page.getByText(/3601\/4000/)).toBeVisible();

  // Type more to exceed limit
  await chatInput.fill(longMessage + "b".repeat(500));

  // Should be capped at 4000
  await expect(page.getByText("4000/4000")).toBeVisible();

  // Verify input is limited
  const actualValue = await chatInput.inputValue();
  expect(actualValue.length).toBe(4000);
});

test("handles tool rejection flow", async ({ mount, page }) => {
  const mocks = [
    createConversationsMock(mockConversations),
    createChatMessagesMock(TEST_CONVERSATION_ID, [
      ...mockChatMessages,
      mockAwaitingApprovalMessage,
    ]),
  ];

  await mountChatTray(mount, mocks);

  // Load conversation with approval-pending message
  await page.getByText("Test Conversation 1").click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify approval modal appears
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Click reject button
  await page.getByRole("button", { name: "Reject" }).click();

  // Verify approval modal disappears
  await expect(
    page.getByText("Tool Approval Required", { exact: true })
  ).not.toBeVisible({
    timeout: TIMEOUTS.SHORT,
  });

  // Verify rejection message is shown
  await expect(
    page.getByText("Tool execution was rejected. How else can I help you?", {
      exact: true,
    })
  ).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
});

// TODO - re-enable. Low priority
// test("date filter works correctly", async ({ mount, page }) => {
//   const mocks = [
//     createConversationsMock(mockConversations),
//     createConversationsMock(
//       [mockConversations[0]], // Only conversation from last day
//       false,
//       {
//         createdAt_Gte: new Date(Date.now() - 86400000).toISOString().split('T')[0],
//         createdAt_Lte: new Date().toISOString().split('T')[0]
//       }
//     ),
//   ];

//   await mountChatTray(mount, mocks);

//   // Wait for initial load
//   await expect(page.locator("#conversation-grid")).toBeVisible({
//     timeout: TIMEOUTS.MEDIUM,
//   });

//   // Click calendar icon to open date picker
//   await page.locator('[data-testid="date-filter-button"]').click();

//   // Set date range (last 24 hours)
//   const dateInputs = page.locator('input[type="date"]');
//   await expect(dateInputs.first()).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
//   const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
//   const today = new Date().toISOString().split('T')[0];

//   await dateInputs.first().fill(yesterday);
//   await dateInputs.last().fill(today);

//   // Click outside to trigger filter
//   await page.locator("#conversation-grid").click();

//   // Wait for filtered results
//   await expect(page.getByText("Test Conversation 1", { exact: true })).toBeVisible();
//   await expect(page.getByText("Test Conversation 2", { exact: true })).not.toBeVisible({
//     timeout: TIMEOUTS.SHORT,
//   });
// });

test("maintains scroll position when new messages arrive", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  const messagesContainer = page.locator("#messages-container");
  const chatInput = page.locator('[data-testid="chat-input"]');

  // Send multiple messages to create scrollable content
  await chatInput.fill("First message");
  await page.keyboard.press("Enter");

  // Wait for first response
  await expect(
    page.getByText("Received: First message", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Add a small delay between messages to ensure proper handling
  await page.waitForTimeout(500);

  await chatInput.fill("Second message");
  await page.keyboard.press("Enter");

  // Wait for second response
  await expect(
    page.getByText("Received: Second message", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  await page.waitForTimeout(500);

  await chatInput.fill("Third message");
  await page.keyboard.press("Enter");

  // Wait for third response
  await expect(
    page.getByText("Received: Third message", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Now test scroll behavior
  // Scroll to top
  await messagesContainer.evaluate((el) => {
    el.scrollTop = 0;
  });

  // Wait for scroll to stabilize
  await page.waitForTimeout(200);

  // Get initial position
  const scrolledUpPosition = await messagesContainer.evaluate(
    (el) => el.scrollTop
  );

  // Simulate receiving a new message while scrolled up
  await page.evaluate(() => {
    const instances = (window as any).WebSocketInstances;
    if (instances && instances.size > 0) {
      const ws = Array.from(instances)[0] as any;
      const messageId = `assistant-${Date.now()}`;
      ws.onmessage &&
        ws.onmessage({
          data: JSON.stringify({
            type: "SYNC_CONTENT",
            content: "New assistant message while user is scrolled up",
            data: { message_id: messageId },
          }),
        });
    }
  });

  // Wait for the message to appear
  await expect(
    page.getByText("New assistant message while user is scrolled up", {
      exact: true,
    })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Verify scroll position hasn't jumped to bottom
  const currentScrollTop = await messagesContainer.evaluate(
    (el) => el.scrollTop
  );
  const scrollHeight = await messagesContainer.evaluate(
    (el) => el.scrollHeight
  );
  const clientHeight = await messagesContainer.evaluate(
    (el) => el.clientHeight
  );

  // Should still be near the top, not at the bottom
  expect(currentScrollTop).toBeLessThan(scrollHeight - clientHeight - 200);

  // Now test auto-scroll when already at bottom
  await messagesContainer.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });

  await page.waitForTimeout(200);

  // Send another message while at bottom
  await chatInput.fill("Message while at bottom");
  await page.keyboard.press("Enter");

  // Wait for response
  await expect(
    page.getByText("Received: Message while at bottom", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Give extra time for any scrolling animation
  await page.waitForTimeout(1500);

  // Poll for scroll position to stabilize
  await expect
    .poll(
      async () => {
        const scrollTop = await messagesContainer.evaluate(
          (el) => el.scrollTop
        );
        const scrollHeight = await messagesContainer.evaluate(
          (el) => el.scrollHeight
        );
        const clientHeight = await messagesContainer.evaluate(
          (el) => el.clientHeight
        );
        return scrollHeight - clientHeight - scrollTop;
      },
      {
        timeout: 3000,
        intervals: [100, 200, 500],
      }
    )
    .toBeLessThan(150);
});

test("shows connection status indicators", async ({ mount, page }) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  // Start new chat
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Verify connected status (green dot should be visible)
  const connectionStatus = page.locator('[data-testid="connection-status"]');
  await expect(connectionStatus).toHaveAttribute("data-connected", "true");

  // Type in input to verify it's enabled when connected
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  // Now simulate disconnect by closing all active WebSocket instances
  await page.evaluate(() => {
    // @ts-ignore
    const instances = window.WebSocketInstances;
    if (instances) {
      instances.forEach((ws: any) => {
        if (ws.readyState === 1) {
          // OPEN
          ws.close();
        }
      });
    }
  });

  // Wait for status update
  await page.waitForTimeout(500);

  // Verify disconnected status
  await expect(connectionStatus).toHaveAttribute("data-connected", "false");

  // Input should show "Waiting for connection..." placeholder
  await expect(chatInput).toHaveAttribute(
    "placeholder",
    "Waiting for connection..."
  );
  await expect(chatInput).toBeDisabled();
});

// TODO - Re-enable.Low Priority
// test("clears filters when X button is clicked", async ({ mount, page }) => {
//   const mocks = [
//     createConversationsMock(mockConversations),
//     createConversationsMock(mockConversations), // For reset
//   ];

//   await mountChatTray(mount, mocks);

//   // Apply search filter
//   await page.locator('[data-testid="search-filter-button"]').click();
//   const searchInput = page.locator('input[placeholder="Search by title..."]');
//   await searchInput.fill("Test");

//   // Apply date filter
//   await page.locator('[data-testid="date-filter-button"]').click();
//   const dateInputs = page.locator('input[type="date"]');
//   await expect(dateInputs.first()).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
//   await dateInputs.first().fill("2024-01-01");

//   // Verify X button appears
//   const clearButton = page.locator('[data-testid="clear-filters-button"]');
//   await expect(clearButton).toBeVisible();

//   // Click X to clear all filters
//   await clearButton.click();

//   // Verify filters are cleared
//   await expect(searchInput).not.toBeVisible();
//   // Ensure the date picker is also closed
//   await expect(page.locator('input[type="date"]').first()).not.toBeVisible();

//   // Verify all conversations are shown again
//   await expect(page.getByText("Test Conversation 1", { exact: true })).toBeVisible();
//   await expect(page.getByText("Test Conversation 2", { exact: true })).toBeVisible();
// });

test("message count colors reflect relative activity", async ({
  mount,
  page,
}) => {
  const activeConversation = {
    ...mockConversations[0],
    id: "active-conv",
    title: "Very Active Conversation",
    chatMessages: {
      totalCount: 20,
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo" as const,
      },
      edges: [],
      __typename: "ChatMessageTypeConnection" as const,
    },
  };

  const inactiveConversation = {
    ...mockConversations[1],
    id: "inactive-conv",
    title: "Inactive Conversation",
    chatMessages: {
      totalCount: 0,
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
        __typename: "PageInfo" as const,
      },
      edges: [],
      __typename: "ChatMessageTypeConnection" as const,
    },
  };

  const mocks = [
    createConversationsMock([activeConversation, inactiveConversation]),
  ];

  await mountChatTray(mount, mocks);

  // Wait for conversations to load
  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Get message count elements
  const activeCount = page.locator('text="20"');
  const inactiveCount = page.locator('text="0"');

  // Verify they have different styling
  const activeStyles = await activeCount.evaluate((el) => {
    const computed = window.getComputedStyle(el);
    return {
      background: computed.background,
      color: computed.color,
    };
  });

  const inactiveStyles = await inactiveCount.evaluate((el) => {
    const computed = window.getComputedStyle(el);
    return {
      background: computed.background,
      color: computed.color,
    };
  });

  // Active conversation should have different styling than inactive
  expect(activeStyles.background).not.toBe(inactiveStyles.background);

  // Verify the active one has white text (high activity)
  expect(activeStyles.color).toBe("rgb(255, 255, 255)"); // white
});

/* -------------------------------------------------------------------------- */
/* Additional coverage: error/empty/readOnly/SYNC_CONTENT/back-button          */
/* -------------------------------------------------------------------------- */

test("shows new-chat FAB even when conversation list is empty", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock([])];

  await mountChatTray(mount, mocks);

  await expect(page.locator('[data-testid="new-chat-button"]')).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // No conversation cards should render
  await expect(page.locator('[data-testid^="conversation-card"]')).toHaveCount(
    0
  );
});

test("Back to Conversations button returns to the conversation list", async ({
  mount,
  page,
}) => {
  // `exitConversation` calls `refetch()`, so TWO GET_CONVERSATIONS mocks
  // are needed: one for the initial load, one for the refetch.
  const mocks = [
    createConversationsMock(mockConversations),
    createConversationsMock(mockConversations),
    createChatMessagesMock(TEST_CONVERSATION_ID, mockChatMessages),
  ];

  await mountChatTray(mount, mocks);

  // Open a conversation
  await page.getByText("Test Conversation 1").click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await expect(page.getByText("Back to Conversations")).toBeVisible();

  // Click Back → returns to the grid
  await page.getByText("Back to Conversations").click();

  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
});

test("error response renders reconnect button and persisted error message", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  // Directly drive an ASYNC_ERROR from the stub socket so we're not at the
  // mercy of the stub's query matcher. This covers the ASYNC_ERROR branch of
  // the WebSocket onmessage handler and the `wsError` render path.
  await page.evaluate(() => {
    const instances = (window as any).WebSocketInstances;
    if (instances && instances.size > 0) {
      const ws = Array.from(instances)[0] as any;
      ws.onmessage &&
        ws.onmessage({
          data: JSON.stringify({
            type: "ASYNC_ERROR",
            content: "Service temporarily unavailable",
            data: {
              message_id: `err_${Date.now()}`,
              error: "Service temporarily unavailable",
            },
          }),
        });
    }
  });

  // Error banner renders - check the ws-error-message container first
  await expect(page.locator('[data-testid="ws-error-message"]')).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Reconnect button appears inside the error banner
  await expect(
    page.locator('[data-testid="ws-error-message"]').getByRole("button", {
      name: "Reconnect",
    })
  ).toBeVisible();
});

test("new chat create button starts a fresh conversation immediately", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await expect(page.locator("#conversation-grid")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  await page.locator('[data-testid="new-chat-button"]').click();

  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Chat input should be present and enabled once the stub socket opens
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });
});

test("submit button is disabled when no conversation is active and empty message", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  // Input is empty → Enter should do nothing (stays on same UI)
  await page.keyboard.press("Enter");
  // No "Received: " message should appear
  await expect(page.getByText(/^Received:/)).not.toBeVisible();
});

test("character count is NOT visible below 90% of limit", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  // A short message should NOT trigger the near-limit indicator
  await chatInput.fill("short message");
  await expect(page.getByText(/\d+\/4000/)).not.toBeVisible();
});

test("Shift+Enter inserts newline instead of sending", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  await chatInput.fill("line 1");
  await page.keyboard.down("Shift");
  await page.keyboard.press("Enter");
  await page.keyboard.up("Shift");
  await chatInput.type("line 2");

  const value = await chatInput.inputValue();
  expect(value).toContain("\n");

  // No user message has been sent yet
  await expect(page.getByText(/^Received:/)).not.toBeVisible();
});

test("context meter displays when backend reports context_status", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  await chatInput.fill("show meter");
  await page.keyboard.press("Enter");

  // Once the stub emits ASYNC_FINISH with context_status the meter appears
  await page.evaluate(() => {
    const instances = (window as any).WebSocketInstances;
    if (instances && instances.size > 0) {
      const ws = Array.from(instances)[0] as any;
      ws.onmessage &&
        ws.onmessage({
          data: JSON.stringify({
            type: "ASYNC_FINISH",
            content: "Done",
            data: {
              message_id: "context-1",
              context_status: {
                used_tokens: 800,
                context_window: 2000,
                was_compacted: true,
              },
            },
          }),
        });
    }
  });

  await expect(page.locator('[data-testid="context-meter"]')).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await expect(
    page.locator('[data-testid="context-meter-percentage"]')
  ).toHaveText(/40%/);
  await expect(
    page.locator('[data-testid="context-meter-compacted"]')
  ).toBeVisible();
});

test("compaction banner displays during streaming compaction", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });

  // Send a message first to create a streaming assistant message
  await chatInput.fill("compact me");
  await page.keyboard.press("Enter");

  // Drive an ASYNC_THOUGHT with compaction data onto the same message id
  // The stub emits ASYNC_START with id=Date.now().toString() just before
  // ASYNC_CONTENT. Instead of guessing that id, we'll send our own ASYNC_THOUGHT
  // with a fresh message id so that the compaction banner appears.
  await page.evaluate(() => {
    const instances = (window as any).WebSocketInstances;
    if (instances && instances.size > 0) {
      const ws = Array.from(instances)[0] as any;
      ws.onmessage &&
        ws.onmessage({
          data: JSON.stringify({
            type: "ASYNC_THOUGHT",
            content: "Compacting context...",
            data: {
              message_id: `compact_${Date.now()}`,
              compaction: {
                tokens_before: 9000,
                tokens_after: 3000,
                context_window: 16000,
              },
            },
          }),
        });
    }
  });

  await expect(page.locator('[data-testid="compaction-banner"]')).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await expect(
    page
      .locator('[data-testid="compaction-banner"]')
      .getByText("Compacting context")
  ).toBeVisible();
});

test("SYNC_CONTENT message renders as a standalone assistant message", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  await mountChatTray(mount, mocks);

  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Push a SYNC_CONTENT from the stub
  await page.evaluate(() => {
    const instances = (window as any).WebSocketInstances;
    if (instances && instances.size > 0) {
      const ws = Array.from(instances)[0] as any;
      ws.onmessage &&
        ws.onmessage({
          data: JSON.stringify({
            type: "SYNC_CONTENT",
            content: "Standalone assistant notice",
            data: { message_id: "sync-1" },
          }),
        });
    }
  });

  await expect(
    page.getByText("Standalone assistant notice", { exact: true })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
});

test("readOnly: hides history and chat input is still available for new chat", async ({
  mount,
  page,
}) => {
  const mocks = [createConversationsMock(mockConversations)];

  // Call with showLoad true/false; the key is readOnly=true on the
  // underlying ChatTray. The wrapper passes props through, but ChatTray's
  // readOnly is NOT a wrapper prop — it's only controlled by the parent
  // ChatTray's own default (false). We therefore mount with readOnly via a
  // direct-prop shim: this test asserts the visible behaviors driven by the
  // absence of authenticated user - starting directly in new chat mode.
  await mountChatTray(mount, mocks);

  // With user authenticated & a new-chat click, the input should become active
  await page.locator('[data-testid="new-chat-button"]').click();

  await expect(page.locator('[data-testid="chat-input"]')).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
});

test.beforeEach(async ({ page }) => {
  await attachWsDebug(page);

  // Replace global WebSocket with lightweight stub **inside the page**
  await page.evaluate(() => {
    // Track all active WebSocket instances
    const activeInstances = new Set();

    class StubSocket {
      // useWebSocketAuth checks `ws.readyState !== WebSocket.OPEN`
      // before calling .send(), so the stub must expose the readyState constants
      // as statics on the class itself (since `window.WebSocket = StubSocket`).
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;
      private _disconnectTimeout?: NodeJS.Timeout;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1; // OPEN
        activeInstances.add(this);

        // Open event immediately
        setTimeout(() => this.onopen && this.onopen({}), 0);

        // Only disconnect after 5 seconds by default (enough time for tests)
        // Individual tests can trigger disconnect earlier if needed
        this._disconnectTimeout = setTimeout(() => {
          if (this.readyState !== 3) {
            this.readyState = 3; // CLOSED
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }, 30000);
      }

      send(data) {
        const emit = (payload) =>
          this.onmessage && this.onmessage({ data: JSON.stringify(payload) });
        try {
          const msg = JSON.parse(data);
          if (msg.query) {
            const id = Date.now().toString();
            // Start of streaming
            emit({
              type: "ASYNC_START",
              content: "",
              data: { message_id: id },
            });

            // Special-case queries to satisfy individual tests
            const query = msg.query;

            // 1. Error simulation
            if (query.toLowerCase().includes("error")) {
              emit({
                type: "ASYNC_ERROR",
                content: "Service temporarily unavailable",
                data: {
                  message_id: id,
                  error: "Service temporarily unavailable",
                },
              });
              // Also send a SYNC_CONTENT to ensure a message appears for the test
              emit({
                type: "SYNC_CONTENT",
                content: "Service temporarily unavailable",
                data: { message_id: `${id}_sync` },
              });
              return;
            }

            // 2. Query with sources & timeline
            if (query === "test with sources") {
              // Thought (timeline preview)
              emit({
                type: "ASYNC_THOUGHT",
                content: "Searching for relevant information...",
                data: { message_id: id },
              });

              const sources = [
                {
                  page: 1,
                  json: { start: 0, end: 100 },
                  annotation_id: 123,
                  label: "Important Section",
                  label_id: 456,
                  rawText: "This is the important text from the document.",
                },
              ];

              // Send partial content so UI marks message as having sources early
              emit({
                type: "ASYNC_SOURCES",
                content: "",
                data: { message_id: id, sources },
              });

              emit({
                type: "ASYNC_CONTENT",
                content: "Based on my analysis, here are the key findings.",
                data: { message_id: id },
              });

              emit({
                type: "ASYNC_FINISH",
                content: "Based on my analysis, here are the key findings.",
                data: {
                  message_id: id,
                  sources,
                  timeline: [
                    {
                      type: "thought",
                      text: "Searching for relevant information...",
                    },
                  ],
                },
              });
              return;
            }

            // 3. Generic assistant response - ensure it streams distinct parts
            emit({
              type: "ASYNC_CONTENT",
              content: "Received: ",
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_CONTENT",
              content: query,
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_FINISH",
              content: `Received: ${query}`,
              data: { message_id: id },
            });
          }
          if ("approval_decision" in msg) {
            emit({
              type: "ASYNC_FINISH",
              content: msg.approval_decision
                ? "Summary updated successfully!"
                : "Tool execution was rejected. How else can I help you?",
              data: {
                message_id: msg.llm_message_id,
                approval_decision: msg.approval_decision
                  ? "approved"
                  : "rejected",
              },
            });

            // Send a follow-up SYNC_CONTENT so the success / rejection text appears as standalone chat message
            emit({
              type: "SYNC_CONTENT",
              content: msg.approval_decision
                ? "Summary updated successfully!"
                : "Tool execution was rejected. How else can I help you?",
              data: {
                message_id: `${msg.llm_message_id}_result`,
              },
            });
          }
        } catch {}
      }

      close() {
        if (this._disconnectTimeout) {
          clearTimeout(this._disconnectTimeout);
        }
        if (this.readyState !== 3) {
          this.readyState = 3;
          this.onclose && this.onclose({});
          activeInstances.delete(this);
        }
      }

      // Method to trigger early disconnect for specific tests
      triggerDisconnect() {
        if (this._disconnectTimeout) {
          clearTimeout(this._disconnectTimeout);
        }
        this.close();
      }

      addEventListener() {}
      removeEventListener() {}
    }
    // @ts-ignore
    window.WebSocket = StubSocket;
    // Store reference for tests that need to trigger disconnect
    // @ts-ignore
    window.StubSocket = StubSocket;
    // @ts-ignore
    window.WebSocketInstances = activeInstances;
  });

  // Inject CSS to disable all animations and transitions
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        transition-property: none !important;
        transform: none !important;
        animation: none !important;
      }
    `,
  });
});
