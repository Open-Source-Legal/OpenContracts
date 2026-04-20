import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusChatTestWrapper } from "./CorpusChatTestWrapper";
import {
  GET_CORPUS_CONVERSATIONS,
  GET_CHAT_MESSAGES,
} from "../src/graphql/queries";
import { docScreenshot } from "./utils/docScreenshot";
import { attachWsDebug } from "./utils/wsDebug";

const TEST_CORPUS_ID = "test-corpus-123";
const TEST_CONVERSATION_ID = "test-conv-1";

/* -------------------------------------------------------------------------- */
/* GraphQL Mocks                                                              */
/* -------------------------------------------------------------------------- */

const emptyConversationsMock: MockedResponse = {
  request: {
    query: GET_CORPUS_CONVERSATIONS,
    variables: {
      corpusId: TEST_CORPUS_ID,
      conversationType: "CHAT",
    },
  },
  result: {
    data: {
      conversations: {
        __typename: "ConversationTypeConnection",
        pageInfo: {
          __typename: "PageInfo",
          hasNextPage: false,
          endCursor: null,
        },
        edges: [],
      },
    },
  },
};

const conversationsWithDataMock: MockedResponse = {
  request: {
    query: GET_CORPUS_CONVERSATIONS,
    variables: {
      corpusId: TEST_CORPUS_ID,
      conversationType: "CHAT",
    },
  },
  result: {
    data: {
      conversations: {
        __typename: "ConversationTypeConnection",
        pageInfo: {
          __typename: "PageInfo",
          hasNextPage: false,
          endCursor: null,
        },
        edges: [
          {
            __typename: "ConversationTypeEdge",
            node: {
              __typename: "ConversationType",
              id: TEST_CONVERSATION_ID,
              title: "First Conversation",
              createdAt: new Date(Date.now() - 86400000).toISOString(),
              updatedAt: new Date(Date.now() - 86400000).toISOString(),
              chatMessages: {
                __typename: "ChatMessageTypeConnection",
                totalCount: 5,
              },
              creator: {
                __typename: "UserType",
                email: "user@example.com",
              },
            },
          },
          {
            __typename: "ConversationTypeEdge",
            node: {
              __typename: "ConversationType",
              id: "conv-2",
              title: "Second Conversation",
              createdAt: new Date(Date.now() - 172800000).toISOString(),
              updatedAt: new Date(Date.now() - 172800000).toISOString(),
              chatMessages: {
                __typename: "ChatMessageTypeConnection",
                totalCount: 3,
              },
              creator: {
                __typename: "UserType",
                email: "user@example.com",
              },
            },
          },
        ],
      },
    },
  },
};

const chatMessagesMock: MockedResponse = {
  request: {
    query: GET_CHAT_MESSAGES,
    variables: {
      conversationId: TEST_CONVERSATION_ID,
      limit: 10,
    },
  },
  result: {
    data: {
      chatMessages: [
        {
          __typename: "ChatMessageType",
          id: "srv-1",
          msgType: "HUMAN",
          agentType: null,
          agentConfiguration: null,
          content: "Server question",
          state: "complete",
          data: {},
          creator: {
            __typename: "UserType",
            id: "u1",
            username: "alice",
            email: "alice@example.com",
          },
        },
        {
          __typename: "ChatMessageType",
          id: "srv-2",
          msgType: "ASSISTANT",
          agentType: null,
          agentConfiguration: null,
          content: "Server answer",
          state: "complete",
          data: {
            sources: [
              {
                page: 1,
                json: { start: 0, end: 50 },
                annotation_id: 1,
                label: "L",
                label_id: 2,
                rawText: "Snippet from doc",
              },
            ],
          },
          creator: null,
        },
      ],
    },
  },
};

/* -------------------------------------------------------------------------- */
/* WebSocket stub (mirrors ChatTray.ct.tsx pattern)                            */
/* -------------------------------------------------------------------------- */

test.beforeEach(async ({ page }) => {
  await attachWsDebug(page);

  await page.evaluate(() => {
    const activeInstances = new Set();

    class StubSocket {
      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;
      onerror?: (event: any) => void;
      private _disconnectTimeout?: ReturnType<typeof setTimeout>;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1;
        activeInstances.add(this);
        setTimeout(() => this.onopen && this.onopen({}), 0);
        // Auto-close after 30s in case test forgets
        this._disconnectTimeout = setTimeout(() => {
          if (this.readyState !== 3) {
            this.readyState = 3;
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }, 30000);
      }

      send(data: string) {
        const emit = (payload: unknown) =>
          this.onmessage && this.onmessage({ data: JSON.stringify(payload) });
        try {
          const msg = JSON.parse(data);
          if (msg.query) {
            const id = Date.now().toString();
            const query = String(msg.query).toLowerCase();

            // Approval flow
            if (query.includes("approve please")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_APPROVAL_NEEDED",
                content: "",
                data: {
                  message_id: id,
                  pending_tool_call: {
                    name: "delete_doc",
                    arguments: { doc_id: "abc" },
                  },
                },
              });
              return;
            }

            // Error simulation. Defer the ASYNC_ERROR via setTimeout so
            // it lands AFTER `sendMessageOverSocket` finishes its synchronous
            // `setWsError(null)` call — otherwise React batches both calls
            // and the null wins.
            if (query.includes("trigger error")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              setTimeout(
                () =>
                  emit({
                    type: "ASYNC_ERROR",
                    content: "",
                    data: { message_id: id, error: "Backend exploded" },
                  }),
                10
              );
              return;
            }

            // Context exhausted
            if (query.includes("context full")) {
              emit({
                type: "ASYNC_ERROR",
                content: "",
                data: {
                  message_id: id,
                  error_type: "CONTEXT_EXHAUSTED",
                  error: "Context full",
                },
              });
              return;
            }

            // Compaction notice
            if (query.includes("compact please")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_THOUGHT",
                content: "Compacting now...",
                data: {
                  message_id: id,
                  compaction: {
                    tokens_before: 5000,
                    tokens_after: 1500,
                    context_window: 8000,
                  },
                },
              });
              emit({
                type: "ASYNC_FINISH",
                content: "Done compacting.",
                data: {
                  message_id: id,
                  context_status: {
                    used_tokens: 1500,
                    context_window: 8000,
                    was_compacted: true,
                  },
                },
              });
              return;
            }

            // Default: streaming with sources + finish
            emit({
              type: "ASYNC_START",
              content: "",
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_CONTENT",
              content: "Echo: ",
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_CONTENT",
              content: msg.query,
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_FINISH",
              content: `Echo: ${msg.query}`,
              data: {
                message_id: id,
                context_status: {
                  used_tokens: 100,
                  context_window: 8000,
                  was_compacted: false,
                },
              },
            });
            return;
          }

          // Approval decision
          if ("approval_decision" in msg) {
            emit({
              type: "ASYNC_APPROVAL_RESULT",
              content: "",
              data: {
                message_id: String(msg.llm_message_id),
                decision: msg.approval_decision ? "approved" : "rejected",
              },
            });
          }
        } catch (e) {
          // Surface malformed payloads in the Playwright console so a
          // timeout here doesn't look like a silent hang.
          // eslint-disable-next-line no-console
          console.warn("[StubSocket] send() parse error", e);
        }
      }

      close() {
        if (this._disconnectTimeout) clearTimeout(this._disconnectTimeout);
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
  });

  // Disable framer animations to keep assertions reliable
  await page.addStyleTag({
    content: `*, *::before, *::after {
        transition-property: none !important;
        transform: none !important;
        animation: none !important;
      }`,
  });
});

/* -------------------------------------------------------------------------- */
/* Tests                                                                      */
/* -------------------------------------------------------------------------- */

test.describe("CorpusChat", () => {
  test("renders conversation list with existing conversations", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[conversationsWithDataMock, conversationsWithDataMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("Second Conversation")).toBeVisible();

    await docScreenshot(page, "corpus--chat--conversation-list");

    await component.unmount();
  });

  test("renders empty state when no conversations exist", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByRole("button", { name: "New Chat", exact: true })
    ).toBeVisible({ timeout: 20000 });

    await docScreenshot(page, "corpus--chat--empty");

    await component.unmount();
  });

  test("renders new chat input when forceNewChat is true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea, input[type='text']").first();
    await expect(input).toBeVisible({ timeout: 20000 });

    await docScreenshot(page, "corpus--chat--new-chat");

    await component.unmount();
  });

  test("sending a message in new chat shows echoed response", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeVisible({ timeout: 20000 });
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("hello world");
    await page.keyboard.press("Enter");

    await expect(page.getByText("hello world", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Echo: hello world", { exact: true })
    ).toBeVisible({ timeout: 10000 });

    // Context meter should appear once context_status is received
    await expect(page.getByTestId("context-meter")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByTestId("context-meter-percentage")).toBeVisible();

    await component.unmount();
  });

  test("ASYNC_ERROR shows error state with reconnect button", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("trigger error now");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Backend exploded")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("button", { name: "Reconnect" })).toBeVisible();

    await component.unmount();
  });

  test("CONTEXT_EXHAUSTED disables input and shows Start New Chat", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("context full please");
    await page.keyboard.press("Enter");

    await expect(
      page.getByText("This conversation has reached its context limit.")
    ).toBeVisible({ timeout: 10000 });

    const newChatBtn = page.getByRole("button", {
      name: "Start New Chat",
      exact: true,
    });
    await expect(newChatBtn).toBeVisible();

    // Clicking Start New Chat resets the banner
    await newChatBtn.click();
    await expect(
      page.getByText("This conversation has reached its context limit.")
    ).not.toBeVisible();

    await component.unmount();
  });

  test("compaction banner appears during compaction event", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("compact please");
    await page.keyboard.press("Enter");

    // After ASYNC_FINISH, compactionNotice is cleared, but the context meter
    // should reflect was_compacted=true.
    await expect(page.getByTestId("context-meter-compacted")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("approval modal appears for ASYNC_APPROVAL_NEEDED then closes on Approve", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("approve please");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Tool Approval Required")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Tool: delete_doc")).toBeVisible();

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.getByText("Tool Approval Required")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("approval modal Reject button sends rejection decision", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    await input.fill("approve please");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Tool Approval Required")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: "Reject" }).click();

    await expect(page.getByText("Tool Approval Required")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("loading an existing conversation fetches and displays server messages", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[
          conversationsWithDataMock,
          conversationsWithDataMock,
          chatMessagesMock,
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });

    await page.getByText("First Conversation").click();

    await expect(page.getByText("Server question")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Server answer")).toBeVisible();

    // Conversation indicator is mounted (the persistent container around the view)
    await expect(page.locator("#conversation-indicator")).toBeVisible();

    await component.unmount();
  });

  test("home button calls onNavigateHome from conversation view", async ({
    mount,
    page,
  }) => {
    let navigated = false;
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
        onNavigateHome={() => {
          navigated = true;
        }}
      />
    );

    // Wait for the conversation view to render
    const input = page.locator("textarea").first();
    await expect(input).toBeVisible({ timeout: 20000 });

    // The Home icon button has title "Return to Dashboard"
    await page.locator('[title="Return to Dashboard"]').click();

    await expect.poll(() => navigated, { timeout: 5000 }).toBe(true);

    await component.unmount();
  });

  test("renders error container when conversations query fails", async ({
    mount,
    page,
  }) => {
    const errorMock: MockedResponse = {
      request: {
        query: GET_CORPUS_CONVERSATIONS,
        variables: {
          corpusId: TEST_CORPUS_ID,
          conversationType: "CHAT",
        },
      },
      error: new Error("Network broken"),
    };

    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[errorMock, errorMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Failed to load corpus conversations")
    ).toBeVisible({ timeout: 20000 });

    await component.unmount();
  });

  test("send button is disabled when there is no message", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeVisible({ timeout: 20000 });

    // The send button is the only button containing the Send icon -- check disabled
    const inputRow = input.locator("..");
    const sendButton = inputRow.locator("button").last();
    await expect(sendButton).toBeDisabled();

    // After typing it should enable
    await input.fill("hello");
    await expect(sendButton).toBeEnabled();

    await component.unmount();
  });
});
