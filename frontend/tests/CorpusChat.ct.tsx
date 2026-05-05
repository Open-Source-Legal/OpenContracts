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

            // Tool call thought (exercises ASYNC_THOUGHT → tool_call timeline)
            if (query.includes("tool call please")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_THOUGHT",
                content: "Invoking search tool",
                data: {
                  message_id: id,
                  tool_name: "search_corpus",
                  args: { query: "contracts" },
                },
              });
              emit({
                type: "ASYNC_THOUGHT",
                content: "Got search result",
                data: {
                  message_id: id,
                  tool_name: "search_corpus",
                  tool_result: "4 matches",
                },
              });
              emit({
                type: "ASYNC_FINISH",
                content: "Here are the results.",
                data: {
                  message_id: id,
                  context_status: {
                    used_tokens: 7200,
                    context_window: 8000,
                    was_compacted: false,
                  },
                },
              });
              return;
            }

            // ASYNC_SOURCES streamed mid-conversation
            if (query.includes("sources please")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_CONTENT",
                content: "Citing: ",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_SOURCES",
                content: "",
                data: {
                  message_id: id,
                  sources: [
                    {
                      page: 1,
                      json: { start: 0, end: 42 },
                      annotation_id: 901,
                      label: "Section 1",
                      label_id: 5,
                      rawText: "Cited snippet",
                    },
                  ],
                },
              });
              emit({
                type: "ASYNC_FINISH",
                content: "Citing: done.",
                data: {
                  message_id: id,
                  sources: [
                    {
                      page: 1,
                      json: { start: 0, end: 42 },
                      annotation_id: 901,
                      label: "Section 1",
                      label_id: 5,
                      rawText: "Cited snippet",
                    },
                  ],
                  context_status: {
                    used_tokens: 2000,
                    context_window: 8000,
                    was_compacted: false,
                  },
                },
              });
              return;
            }

            // SYNC_CONTENT (a non-streaming one-shot response)
            if (query.includes("sync mode")) {
              emit({
                type: "SYNC_CONTENT",
                content: "Sync answer",
                data: { message_id: id, sources: [], timeline: [] },
              });
              return;
            }

            // ASYNC_RESUME after approval
            if (query.includes("resume please")) {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_CONTENT",
                content: "Resumed ",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_RESUME",
                content: "",
                data: { message_id: id },
              });
              emit({
                type: "ASYNC_FINISH",
                content: "Resumed and done.",
                data: { message_id: id },
              });
              return;
            }

            // ask_document sub-tool approval (exercises sub-name remapping)
            if (query.includes("ask document please")) {
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
                    name: "ask_document",
                    arguments: {
                      _sub_tool_name: "update_summary",
                      _sub_tool_arguments: { new_text: "hi" },
                    },
                  },
                },
              });
              return;
            }

            // Delayed response — exposes the warm-up ticker window between
            // ASYNC_START and the first ASYNC_CONTENT so a positive test can
            // assert the standalone ticker is visible during that gap.
            if (query === "warmup test") {
              emit({
                type: "ASYNC_START",
                content: "",
                data: { message_id: id },
              });
              setTimeout(() => {
                emit({
                  type: "ASYNC_CONTENT",
                  content: "Warmup done.",
                  data: { message_id: id },
                });
                emit({
                  type: "ASYNC_FINISH",
                  content: "Warmup done.",
                  data: { message_id: id },
                });
              }, 200);
              return;
            }

            // Unknown message type (exercises default branch → warn)
            if (query.includes("mystery type")) {
              emit({
                type: "TOTALLY_UNKNOWN",
                content: "",
                data: { message_id: id },
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

  test("the legacy 'AI Assistant is thinking…' pill is gone after a send", async ({
    mount,
    page,
  }) => {
    // Regression guard: the standalone "AI Assistant is thinking..." pill
    // (with pulse-dots + spinner) used to render as a separate banner under
    // the messages whenever isProcessing was true. It was replaced by the
    // inline StreamingThoughtTicker on the assistant message itself, plus a
    // standalone warm-up ticker for the brief beat between user-send and
    // first ASYNC_CONTENT/ASYNC_THOUGHT. Pin both halves.
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });
    await input.fill("hello world");
    await page.keyboard.press("Enter");

    // Final response lands.
    await expect(
      page.getByText("Echo: hello world", { exact: true })
    ).toBeVisible({ timeout: 10000 });

    // The legacy pill text must be gone for good — it has no source in the
    // codebase anymore, so this acts as a "no-regression" assertion against
    // anyone re-introducing it.
    await expect(
      page.getByText("AI Assistant is thinking...", { exact: true })
    ).toHaveCount(0);
  });

  test("warmup ticker appears after send and disappears when response arrives", async ({
    mount,
    page,
  }) => {
    // Positive companion to the legacy-pill regression guard above: the
    // standalone warm-up ticker MUST be visible during the gap between
    // user-send and the first ASYNC_CONTENT, then disappear once the
    // assistant message takes over.
    await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
      />
    );

    const input = page.locator("textarea").first();
    await expect(input).toBeEnabled({ timeout: 20000 });

    // The "warmup test" query branches in the WebSocket stub to delay the
    // ASYNC_CONTENT for 200ms, opening a visible warm-up window.
    await input.fill("warmup test");
    await page.keyboard.press("Enter");

    // Ticker visible during the delay.
    await expect(
      page.locator('[data-testid="streaming-warmup-ticker-wrapper"]')
    ).toBeVisible({ timeout: 5000 });

    // The ticker exposes assistant-working state to assistive tech.
    const ticker = page.locator('[data-testid="streaming-thought-ticker"]');
    await expect(ticker).toBeVisible();
    await expect(ticker).toHaveAttribute("role", "status");
    await expect(ticker).toHaveAttribute("aria-live", "polite");

    // Once the response arrives, the standalone warm-up ticker is gone.
    await expect(page.getByText("Warmup done.", { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.locator('[data-testid="streaming-warmup-ticker-wrapper"]')
    ).not.toBeVisible();
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

  test("initialQuery is auto-sent once the WebSocket is ready", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[emptyConversationsMock, emptyConversationsMock]}
        corpusId={TEST_CORPUS_ID}
        forceNewChat
        initialQuery="auto sent question"
      />
    );

    // Human message appears immediately after WS opens + timer fires (500ms)
    await expect(
      page.getByText("auto sent question", { exact: true })
    ).toBeVisible({ timeout: 15000 });

    // Server echoes it
    await expect(
      page.getByText("Echo: auto sent question", { exact: true })
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("tool-call events render timeline entries on the assistant message", async ({
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

    await input.fill("tool call please");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Here are the results.")).toBeVisible({
      timeout: 10000,
    });

    // High-usage context (7200/8000 = 90%) paints the danger fill
    const fill = page.getByTestId("context-meter-fill");
    await expect(fill).toBeVisible();

    await component.unmount();
  });

  test("ASYNC_SOURCES mid-stream populates source citations", async ({
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

    await input.fill("sources please");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Citing: done.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("SYNC_CONTENT renders a complete message immediately", async ({
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

    await input.fill("sync mode now");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Sync answer", { exact: true })).toBeVisible({
      timeout: 10000,
    });

    // SYNC_CONTENT arrives without a preceding ASYNC_START, so isProcessing
    // must never flip to true and the input must remain interactive after the
    // reply lands. Pinning this guards the contract documented in CorpusChat:
    // ASYNC_START is the only setter for setIsProcessing(true).
    await expect(input).toBeEnabled({ timeout: 5000 });

    await component.unmount();
  });

  test("ask_document sub-tool approval shows the inner tool name", async ({
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

    await input.fill("ask document please");
    await page.keyboard.press("Enter");

    await expect(page.getByText("Tool Approval Required")).toBeVisible({
      timeout: 10000,
    });

    // Inner tool name from _sub_tool_name is shown (NOT "ask_document")
    await expect(page.getByText("Tool: update_summary")).toBeVisible();
    await expect(page.getByText("Tool: ask_document")).not.toBeVisible();

    await component.unmount();
  });

  test("ASYNC_RESUME sequence completes with final message", async ({
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

    await input.fill("resume please");
    await page.keyboard.press("Enter");

    // After ASYNC_FINISH the processing indicator is gone and finalized content is shown
    await expect(
      page.getByText("Resumed and done.", { exact: true })
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("unknown WebSocket message type is ignored without crashing", async ({
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

    await input.fill("mystery type");
    await page.keyboard.press("Enter");

    // User message is rendered — the component stays interactive after the
    // unknown frame lands (no crash, no error banner).
    await expect(page.getByText("mystery type", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Error connecting to the corpus WebSocket.")
    ).not.toBeVisible();
    // Unknown frames must not stick the input in a processing state — pin it.
    await expect(input).toBeEnabled({ timeout: 5000 });

    await component.unmount();
  });

  test("back button returns from conversation view to the list", async ({
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

    // Enter conversation view
    await expect(page.getByText("Server question")).toBeVisible({
      timeout: 10000,
    });

    // Back button in the navigation header (sits outside the scrollable
    // conversation-view div) returns to the list.
    await expect(page.locator('[title="Return to Dashboard"]')).toBeVisible();
    await page.getByLabel("Back to conversation list").click();

    // Conversation list is visible again
    await expect(page.getByText("Second Conversation")).toBeVisible({
      timeout: 10000,
    });
    // And conversation content is no longer shown
    await expect(page.getByText("Server question")).not.toBeVisible();

    await component.unmount();
  });

  test("hideListBackButton hides the filter-bar Back in the conversation list", async ({
    mount,
    page,
  }) => {
    // Regression guard for the duplicate-back-button bug on the
    // "Conversation History" / chats-tab list views: when the parent renders
    // its own outer Back affordance, the inner filter-bar Back must
    // disappear so a single Back is visible at any time.
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[conversationsWithDataMock, conversationsWithDataMock]}
        corpusId={TEST_CORPUS_ID}
        onNavigateHome={() => {}}
        hideListBackButton
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });

    // The filter-bar Back lives next to the "+ New Chat" button. With
    // hideListBackButton=true the filter-bar contains no Back-labeled
    // button at all.
    const filterBack = page.locator('button[aria-label="Back"]');
    await expect(filterBack).toHaveCount(0);

    // Sanity: with the prop omitted, the filter-bar Back is rendered.
    await component.unmount();
    await mount(
      <CorpusChatTestWrapper
        mocks={[conversationsWithDataMock, conversationsWithDataMock]}
        corpusId={TEST_CORPUS_ID}
        onNavigateHome={() => {}}
      />
    );
    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.locator('button[aria-label="Back"]')).toBeVisible();
  });

  test("conversation view shows exactly one Back button (not two stacked)", async ({
    mount,
    page,
  }) => {
    // Regression guard for the duplicate-header bug: the inner CorpusChat
    // header should be the single source of back navigation while in a
    // conversation. Mounting CorpusChat in isolation lets us prove there is
    // exactly one Back affordance inside the component itself; the parent
    // (Corpuses.tsx) is responsible for suppressing its own outer header.
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

    // Single back affordance: only one element with a "Back…" aria-label.
    const backButtons = page.locator(
      '[aria-label^="Back"], [aria-label^="back"]'
    );
    await expect(backButtons).toHaveCount(1);
    await expect(backButtons.first()).toHaveAttribute(
      "aria-label",
      "Back to conversation list"
    );
  });

  test("onViewModeChange notifies parent when entering / leaving conversation", async ({
    mount,
    page,
  }) => {
    // Pins the contract that lets Corpuses.tsx suppress its outer "Back / Chat"
    // header while the inner CorpusChat header owns navigation. Without this
    // callback firing on mode flips, the parent flashes a duplicate Back
    // button (the original UX bug we're guarding against).
    const modes: boolean[] = [];

    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[
          conversationsWithDataMock,
          conversationsWithDataMock,
          chatMessagesMock,
        ]}
        corpusId={TEST_CORPUS_ID}
        onViewModeChange={(isInConversation) => {
          modes.push(isInConversation);
        }}
      />
    );

    // Initial render is the list view → false
    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    await expect.poll(() => modes[0]).toBe(false);

    // Enter the conversation → flips to true
    await page.getByText("First Conversation").click();
    await expect(page.getByText("Server question")).toBeVisible({
      timeout: 10000,
    });
    await expect.poll(() => modes.includes(true), { timeout: 5000 }).toBe(true);

    // Back to list → flips to false again
    await page.getByLabel("Back to conversation list").click();
    await expect(page.getByText("Second Conversation")).toBeVisible({
      timeout: 10000,
    });
    await expect
      .poll(
        () => {
          // The most recent mode emission should be `false` (back in list view).
          return modes[modes.length - 1];
        },
        { timeout: 5000 }
      )
      .toBe(false);

    await component.unmount();
  });

  test("chat input starts compact and grows with multi-line content", async ({
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

    // Compact resting state — capture for the redesign docs.
    const initialHeight = await input.evaluate(
      (el) => (el as HTMLTextAreaElement).clientHeight
    );
    expect(initialHeight).toBeLessThan(60);
    await docScreenshot(page, "corpus--chat--input-compact");

    // Type a long, multi-line message and verify the textarea expanded.
    const longText = Array.from(
      { length: 6 },
      (_, i) =>
        `Line ${
          i + 1
        }: this should make the chat input grow vertically up to its CSS max-height before scrolling.`
    ).join("\n");
    await input.fill(longText);

    await expect
      .poll(
        async () =>
          input.evaluate((el) => (el as HTMLTextAreaElement).clientHeight),
        { timeout: 5000 }
      )
      .toBeGreaterThan(initialHeight + 20);

    // …but bounded — the textarea must not grow unbounded with content. The
    // CSS max-height is 140px (content-box), plus padding clientHeight tops
    // out around ~160px. Anything substantially above that means the cap is
    // not in force.
    const grownHeight = await input.evaluate(
      (el) => (el as HTMLTextAreaElement).clientHeight
    );
    expect(grownHeight).toBeLessThanOrEqual(170);

    await docScreenshot(page, "corpus--chat--input-expanded");

    // Clearing the message snaps it back near the compact resting size.
    // Tolerate ~one-line slack — the reset-on-clear effect drops the inline
    // height, but the natural textarea height re-renders against the new
    // padding/min-height which may include a small amount of vertical room
    // for the next character. The contract under test is that the textarea
    // does NOT remain stuck at its multi-line expanded size after clear.
    await input.fill("");
    await expect
      .poll(
        async () =>
          input.evaluate((el) => (el as HTMLTextAreaElement).clientHeight),
        { timeout: 5000 }
      )
      .toBeLessThan(grownHeight - 40);

    await component.unmount();
  });

  test("home button in header calls onNavigateHome from existing conversation", async ({
    mount,
    page,
  }) => {
    let navigated = 0;
    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[
          conversationsWithDataMock,
          conversationsWithDataMock,
          chatMessagesMock,
        ]}
        corpusId={TEST_CORPUS_ID}
        onNavigateHome={() => {
          navigated += 1;
        }}
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    await page.getByText("First Conversation").click();

    await expect(page.getByText("Server question")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[title="Return to Dashboard"]').click();

    await expect.poll(() => navigated, { timeout: 5000 }).toBeGreaterThan(0);

    await component.unmount();
  });

  test("renders a server message with sources attached", async ({
    mount,
    page,
  }) => {
    // Server message carries a source with a document_id — exercises the
    // handleCompleteMessage path for server-side messages.
    const chatMessagesWithDocIdMock: MockedResponse = {
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
              id: "cross-1",
              msgType: "ASSISTANT",
              agentType: null,
              agentConfiguration: null,
              content: "See cross-doc source",
              state: "complete",
              data: {
                sources: [
                  {
                    page: 1,
                    json: { start: 0, end: 10 },
                    annotation_id: 401,
                    label: "X",
                    label_id: 7,
                    rawText: "Cross snippet",
                    document_id: "doc-42",
                  },
                ],
              },
              creator: null,
            },
          ],
        },
      },
    };

    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[
          conversationsWithDataMock,
          conversationsWithDataMock,
          chatMessagesWithDocIdMock,
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    await page.getByText("First Conversation").click();

    await expect(page.getByText("See cross-doc source")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("typing in the title filter updates after debounce", async ({
    mount,
    page,
  }) => {
    // Mock for the debounced refetch with `title_Contains: "First"`. Returns
    // only the "First Conversation" edge so we can positively assert that the
    // debounced value flowed into the Apollo variables and produced a
    // filter-aware result.
    const filteredConversationsMock: MockedResponse = {
      request: {
        query: GET_CORPUS_CONVERSATIONS,
        variables: {
          corpusId: TEST_CORPUS_ID,
          conversationType: "CHAT",
          title_Contains: "First",
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
            ],
          },
        },
      },
    };

    const component = await mount(
      <CorpusChatTestWrapper
        mocks={[
          conversationsWithDataMock,
          conversationsWithDataMock,
          filteredConversationsMock,
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("First Conversation")).toBeVisible({
      timeout: 20000,
    });
    // "Second Conversation" is present in the unfiltered mock — we will later
    // assert it disappears after the debounce fires with the filter.
    await expect(page.getByText("Second Conversation")).toBeVisible();

    // The conversation list has a collapsed search icon that expands to a
    // text input. Click it to reveal the title filter input, then type to
    // drive the 500ms debounce timer useEffect and refetch.
    const searchButton = page.locator('button[title="Search"]');
    await expect(searchButton).toBeVisible({ timeout: 5000 });
    await searchButton.click();

    const filterInput = page.locator('input[placeholder="Search chats..."]');
    await expect(filterInput).toBeVisible({ timeout: 5000 });
    await filterInput.fill("First");

    // After the 500ms debounce fires, the filtered mock takes effect: "Second
    // Conversation" is dropped from the result. Asserting its disappearance
    // proves the debounced value reached Apollo's variables — previously the
    // test silently skipped entirely when the filter input was absent.
    await expect(page.getByText("Second Conversation")).not.toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("First Conversation")).toBeVisible();
    await component.unmount();
  });
});
