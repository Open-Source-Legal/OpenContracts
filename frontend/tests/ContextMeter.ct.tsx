import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { ChatTrayTestWrapper } from "./ChatTrayTestWrapper";
import { GET_CONVERSATIONS } from "../src/graphql/queries";
import { ConversationType } from "../src/types/graphql-api";
import { attachWsDebug } from "./utils/wsDebug";
import { docScreenshot } from "./utils/docScreenshot";

/* -------------------------------------------------------------------------- */
/* Mock Data                                                                   */
/* -------------------------------------------------------------------------- */

const TEST_DOC_ID = "test-doc-ctx-1";
const TEST_CORPUS_ID = "test-corpus-ctx-1";

const mockConversations: ConversationType[] = [
  {
    id: "ctx-conv-1",
    title: "Context Meter Test",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    creator: {
      id: "user1",
      email: "user1@example.com",
      __typename: "UserType",
    },
    chatMessages: {
      totalCount: 0,
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

/* -------------------------------------------------------------------------- */
/* GraphQL Mocks                                                               */
/* -------------------------------------------------------------------------- */

const createConversationsMock = (
  conversations: ConversationType[]
): MockedResponse => ({
  request: {
    query: GET_CONVERSATIONS,
    variables: { documentId: TEST_DOC_ID },
  },
  result: {
    data: {
      conversations: {
        edges: conversations.map((conv) => ({
          node: conv,
          __typename: "ConversationTypeEdge",
        })),
        pageInfo: {
          hasNextPage: false,
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

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

const TIMEOUTS = { SHORT: 5_000, MEDIUM: 10_000 };

/** Chat-tray-sized viewport for clean screenshots (no clipping needed). */
const CHAT_VIEWPORT = { width: 420, height: 720 };

interface ContextStatusPayload {
  used_tokens: number;
  context_window: number;
  was_compacted: boolean;
  tokens_before_compaction: number;
}

/** Scripted reply per user query — makes the conversation look realistic. */
const SCRIPTED_REPLIES: Record<string, string> = {
  "What are the key terms in this contract?":
    "The contract contains several key terms: a 24-month duration, automatic renewal clause, and a $50,000 annual fee with 3% escalation.",
  "Are there any liability caps?":
    "Yes, Section 8.2 limits total liability to the aggregate fees paid in the prior 12 months, with carve-outs for IP indemnification.",
  "Summarize the termination provisions":
    "Either party may terminate for convenience with 90 days written notice. Termination for cause requires a 30-day cure period.",
  "How does the indemnification work?":
    "Each party indemnifies the other against third-party claims arising from breach. The indemnifying party controls defense and settlement.",
};

interface WsStubOptions {
  contextStatus: ContextStatusPayload;
  /** If set, emit an ASYNC_THOUGHT with a compaction message before ASYNC_FINISH. */
  emitCompactionThought?: boolean;
}

/**
 * Install a WebSocket stub with scripted replies and context_status in ASYNC_FINISH.
 */
async function installWsStub(page: any, opts: WsStubOptions) {
  await page.evaluate(
    ({
      ctxStatus,
      replies,
      emitCompaction,
    }: {
      ctxStatus: ContextStatusPayload;
      replies: Record<string, string>;
      emitCompaction: boolean;
    }) => {
      const activeInstances = new Set();
      let msgCounter = 0;

      class StubSocket {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;

        url: string;
        readyState: number;
        onopen?: (event: any) => void;
        onmessage?: (event: any) => void;
        onclose?: (event: any) => void;

        constructor(url: string) {
          this.url = url;
          this.readyState = 1;
          activeInstances.add(this);
          setTimeout(() => this.onopen && this.onopen({}), 0);
          setTimeout(() => {
            if (this.readyState !== 3) {
              this.readyState = 3;
              this.onclose && this.onclose({});
              activeInstances.delete(this);
            }
          }, 30000);
        }

        send(data: string) {
          const emit = (payload: any) =>
            this.onmessage && this.onmessage({ data: JSON.stringify(payload) });
          try {
            const msg = JSON.parse(data);
            if (msg.query) {
              const id = `msg-${++msgCounter}-${Date.now()}`;
              const reply =
                replies[msg.query] ||
                `I can help you with that. Here's what I found regarding "${msg.query}".`;

              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });

              // Emit compaction thought if requested
              if (emitCompaction) {
                emit({
                  type: "ASYNC_THOUGHT",
                  content: `Conversation history compacted: ${ctxStatus.tokens_before_compaction.toLocaleString()} \u2192 ${ctxStatus.used_tokens.toLocaleString()} estimated tokens (${ctxStatus.context_window.toLocaleString()} token window)`,
                  data: {
                    message_id: id,
                    compaction: {
                      tokens_before: ctxStatus.tokens_before_compaction,
                      tokens_after: ctxStatus.used_tokens,
                      context_window: ctxStatus.context_window,
                    },
                  },
                });
              }

              emit({
                type: "ASYNC_THOUGHT",
                content: "Searching document for relevant sections\u2026",
                data: { message_id: id },
              });

              emit({
                type: "ASYNC_CONTENT",
                content: reply,
                data: { message_id: id },
              });

              emit({
                type: "ASYNC_FINISH",
                content: reply,
                data: {
                  message_id: id,
                  context_status: ctxStatus,
                },
              });
            }
          } catch {}
        }

        close() {
          if (this.readyState !== 3) {
            this.readyState = 3;
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }

        addEventListener() {}
        removeEventListener() {}
      }

      // @ts-ignore
      window.WebSocket = StubSocket;
      // @ts-ignore
      window.WebSocketInstances = activeInstances;
    },
    {
      ctxStatus: opts.contextStatus,
      replies: SCRIPTED_REPLIES,
      emitCompaction: opts.emitCompactionThought ?? false,
    }
  );
}

/** Send a message and wait for the reply to appear. */
async function sendAndWait(page: any, message: string, expectedReply: string) {
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });
  await chatInput.fill(message);
  await page.waitForTimeout(300);
  await page.keyboard.press("Enter");
  await expect(page.getByText(expectedReply, { exact: false })).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  // Let the UI settle before the next interaction
  await page.waitForTimeout(300);
}

/** Start a new chat and send a couple of warm-up messages to populate the view. */
async function startChatWithHistory(page: any) {
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await sendAndWait(
    page,
    "What are the key terms in this contract?",
    "24-month duration"
  );
  await sendAndWait(
    page,
    "Are there any liability caps?",
    "Section 8.2 limits"
  );
}

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test.beforeEach(async ({ page }) => {
  await attachWsDebug(page);

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

test("shows context meter with green bar at low usage", async ({
  mount,
  page,
}) => {
  await installWsStub(page, {
    contextStatus: {
      used_tokens: 3000,
      context_window: 10000,
      was_compacted: false,
      tokens_before_compaction: 0,
    },
  });

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  await startChatWithHistory(page);

  // Context meter should appear
  const meter = page.locator('[data-testid="context-meter"]');
  await expect(meter).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  // Verify percentage text
  const percentage = page.locator('[data-testid="context-meter-percentage"]');
  await expect(percentage).toHaveText("30%");

  // Verify title attribute
  await expect(percentage).toHaveAttribute(
    "title",
    "~3,000 / 10,000 tokens used"
  );

  // Verify fill bar is green (30% < 60%)
  const fill = page.locator('[data-testid="context-meter-fill"]');
  const bgColor = await fill.evaluate(
    (el) => window.getComputedStyle(el).backgroundColor
  );
  expect(bgColor).toBe("rgb(34, 197, 94)");

  // Compacted badge should NOT be visible
  await expect(
    page.locator('[data-testid="context-meter-compacted"]')
  ).not.toBeVisible();

  await page.setViewportSize(CHAT_VIEWPORT);
  await page.waitForTimeout(200);
  await docScreenshot(page, "chat--context-meter--green");
});

test("shows yellow bar at medium usage", async ({ mount, page }) => {
  await installWsStub(page, {
    contextStatus: {
      used_tokens: 7200,
      context_window: 10000,
      was_compacted: false,
      tokens_before_compaction: 0,
    },
  });

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  await startChatWithHistory(page);

  const meter = page.locator('[data-testid="context-meter"]');
  await expect(meter).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  await expect(
    page.locator('[data-testid="context-meter-percentage"]')
  ).toHaveText("72%");

  const fill = page.locator('[data-testid="context-meter-fill"]');
  const bgColor = await fill.evaluate(
    (el) => window.getComputedStyle(el).backgroundColor
  );
  // OS_LEGAL_COLORS.folderIcon = #D97706
  expect(bgColor).toBe("rgb(217, 119, 6)");

  await page.setViewportSize(CHAT_VIEWPORT);
  await page.waitForTimeout(200);
  await docScreenshot(page, "chat--context-meter--yellow");
});

test("shows red bar at high usage", async ({ mount, page }) => {
  await installWsStub(page, {
    contextStatus: {
      used_tokens: 9200,
      context_window: 10000,
      was_compacted: false,
      tokens_before_compaction: 0,
    },
  });

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  await startChatWithHistory(page);

  // Send a third message to make it feel like a long conversation
  await sendAndWait(
    page,
    "Summarize the termination provisions",
    "90 days written notice"
  );

  const meter = page.locator('[data-testid="context-meter"]');
  await expect(meter).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  await expect(
    page.locator('[data-testid="context-meter-percentage"]')
  ).toHaveText("92%");

  const fill = page.locator('[data-testid="context-meter-fill"]');
  const bgColor = await fill.evaluate(
    (el) => window.getComputedStyle(el).backgroundColor
  );
  // OS_LEGAL_COLORS.danger = #dc2626
  expect(bgColor).toBe("rgb(220, 38, 38)");

  await page.setViewportSize(CHAT_VIEWPORT);
  await page.waitForTimeout(200);
  await docScreenshot(page, "chat--context-meter--red");
});

test("shows compacted badge when was_compacted is true", async ({
  mount,
  page,
}) => {
  await installWsStub(page, {
    contextStatus: {
      used_tokens: 4500,
      context_window: 10000,
      was_compacted: true,
      tokens_before_compaction: 9500,
    },
    emitCompactionThought: true,
  });

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  await startChatWithHistory(page);

  // Send a third message that triggers compaction
  await sendAndWait(
    page,
    "How does the indemnification work?",
    "indemnifies the other"
  );

  const meter = page.locator('[data-testid="context-meter"]');
  await expect(meter).toBeVisible({ timeout: TIMEOUTS.MEDIUM });

  await expect(
    page.locator('[data-testid="context-meter-percentage"]')
  ).toHaveText("45%");

  // Compacted badge should be visible
  const compacted = page.locator('[data-testid="context-meter-compacted"]');
  await expect(compacted).toBeVisible();
  await expect(compacted).toHaveText("Compacted");

  await page.setViewportSize(CHAT_VIEWPORT);
  await page.waitForTimeout(200);
  await docScreenshot(page, "chat--context-meter--compacted");
});

test("shows compaction thought in timeline during streaming", async ({
  mount,
  page,
}) => {
  // Stub that responds instantly to the first 2 messages (warm-up),
  // then delays ASYNC_FINISH on the 3rd message so we can screenshot
  // the compaction thought mid-stream.
  await page.evaluate((replies: Record<string, string>) => {
    const activeInstances = new Set();
    let msgCounter = 0;

    class StubSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1;
        activeInstances.add(this);
        setTimeout(() => this.onopen && this.onopen({}), 0);
        setTimeout(() => {
          if (this.readyState !== 3) {
            this.readyState = 3;
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }, 30000);
      }

      send(data: string) {
        const self = this;
        const emit = (payload: any) =>
          self.onmessage && self.onmessage({ data: JSON.stringify(payload) });
        try {
          const msg = JSON.parse(data);
          if (msg.query) {
            msgCounter++;
            const id = `msg-${msgCounter}-${Date.now()}`;
            const reply =
              replies[msg.query] || `I can help with "${msg.query}".`;

            emit({
              type: "ASYNC_START",
              content: "",
              data: { message_id: id },
            });

            // First 2 messages: instant response with normal context status
            if (msgCounter <= 2) {
              emit({
                type: "ASYNC_THOUGHT",
                content: "Searching document for relevant sections\u2026",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_CONTENT",
                content: reply,
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_FINISH",
                content: reply,
                data: {
                  message_id: id,
                  context_status: {
                    used_tokens: 3000 + msgCounter * 2000,
                    context_window: 10000,
                    was_compacted: false,
                    tokens_before_compaction: 0,
                  },
                },
              });
              return;
            }

            // 3rd+ message: delayed response with compaction thought
            emit({
              type: "ASYNC_THOUGHT",
              content:
                "Conversation history compacted: 9,500 \u2192 4,500 estimated tokens (10,000 token window)",
              data: {
                message_id: id,
                compaction: {
                  tokens_before: 9500,
                  tokens_after: 4500,
                  context_window: 10000,
                },
              },
            });

            setTimeout(() => {
              emit({
                type: "ASYNC_THOUGHT",
                content: "Searching document for relevant sections\u2026",
                data: { message_id: id },
              });
            }, 400);

            setTimeout(() => {
              emit({
                type: "ASYNC_CONTENT",
                content: reply,
                data: { message_id: id },
              });
            }, 1200);

            setTimeout(() => {
              emit({
                type: "ASYNC_FINISH",
                content: reply,
                data: {
                  message_id: id,
                  context_status: {
                    used_tokens: 4500,
                    context_window: 10000,
                    was_compacted: true,
                    tokens_before_compaction: 9500,
                  },
                },
              });
            }, 4000);
          }
        } catch {}
      }

      close() {
        if (this.readyState !== 3) {
          this.readyState = 3;
          this.onclose && this.onclose({});
          activeInstances.delete(this);
        }
      }

      addEventListener() {}
      removeEventListener() {}
    }

    // @ts-ignore
    window.WebSocket = StubSocket;
    // @ts-ignore
    window.WebSocketInstances = activeInstances;
  }, SCRIPTED_REPLIES);

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  // Warm up with 2 instant-reply messages
  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });
  await sendAndWait(
    page,
    "What are the key terms in this contract?",
    "24-month duration"
  );
  await sendAndWait(
    page,
    "Are there any liability caps?",
    "Section 8.2 limits"
  );

  // 3rd message triggers delayed compaction flow
  const chatInput = page.locator('[data-testid="chat-input"]');
  await expect(chatInput).toBeEnabled({ timeout: TIMEOUTS.MEDIUM });
  await chatInput.fill("How does the indemnification work?");
  await page.waitForTimeout(300);
  await page.keyboard.press("Enter");

  // Wait for the standalone compaction banner to appear
  const banner = page.locator('[data-testid="compaction-banner"]');
  await expect(banner).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
  await expect(banner.locator("text=Compacting context")).toBeVisible();
  await expect(banner.locator("text=9,500")).toBeVisible();

  // Resize viewport, let auto-scroll settle, then screenshot
  await page.setViewportSize(CHAT_VIEWPORT);
  await page.waitForTimeout(500);

  // Ensure the compaction thought is scrolled into view
  const msgContainer = page.locator("#messages-container");
  await msgContainer.evaluate((el: HTMLElement) => {
    el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(200);

  await docScreenshot(page, "chat--context-meter--compaction-underway");

  // Verify the flow completes
  await expect(
    page.getByText("indemnifies the other", { exact: false })
  ).toBeVisible({ timeout: TIMEOUTS.MEDIUM });
});

test("context meter not visible before first response", async ({
  mount,
  page,
}) => {
  // Install a stub that never sends ASYNC_FINISH
  await page.evaluate(() => {
    const activeInstances = new Set();
    class StubSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1;
        activeInstances.add(this);
        setTimeout(() => this.onopen && this.onopen({}), 0);
      }

      send() {}
      close() {
        this.readyState = 3;
        activeInstances.delete(this);
      }
      addEventListener() {}
      removeEventListener() {}
    }
    // @ts-ignore
    window.WebSocket = StubSocket;
    // @ts-ignore
    window.WebSocketInstances = activeInstances;
  });

  const mocks = [createConversationsMock(mockConversations)];
  await mount(
    <ChatTrayTestWrapper
      mocks={mocks}
      documentId={TEST_DOC_ID}
      corpusId={TEST_CORPUS_ID}
    />
  );

  await page.locator('[data-testid="new-chat-button"]').click();
  await expect(page.locator("#messages-container")).toBeVisible({
    timeout: TIMEOUTS.MEDIUM,
  });

  // Context meter should NOT be visible since no ASYNC_FINISH was received
  await expect(page.locator('[data-testid="context-meter"]')).not.toBeVisible();
});
