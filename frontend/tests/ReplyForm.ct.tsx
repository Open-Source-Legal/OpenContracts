import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { ReplyForm } from "../src/components/threads/ReplyForm";
import { MockedProvider } from "@apollo/client/testing";
import {
  CREATE_THREAD_MESSAGE,
  REPLY_TO_MESSAGE,
  CreateThreadMessageOutput,
  ReplyToMessageOutput,
} from "../src/graphql/mutations";
import { GET_THREAD_DETAIL } from "../src/graphql/queries";

test.describe("ReplyForm - Top-level Message", () => {
  test("renders for top-level message", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm conversationId="conv-1" onCancel={() => {}} />
      </MockedProvider>
    );

    // Should have the composer
    await expect(page.locator(".ProseMirror")).toBeVisible();
  });

  test("shows placeholder for top-level message", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm conversationId="conv-1" onCancel={() => {}} />
      </MockedProvider>
    );

    // Check editor is visible with empty state (TipTap renders placeholders as CSS pseudo-elements)
    await expect(page.locator(".ProseMirror p.is-editor-empty")).toBeVisible();
  });

  test("submits top-level message", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: CREATE_THREAD_MESSAGE,
          variables: {
            conversationId: "conv-1",
            content: "Test message content",
          },
        },
        result: {
          data: {
            createThreadMessage: {
              ok: true,
              message: "Message created successfully",
              obj: {
                id: "msg-1",
                content: "<p>Test message</p>",
                created: "2025-01-01T00:00:00Z",
                modified: "2025-01-01T00:00:00Z",
                creator: {
                  id: "user-1",
                  username: "testuser",
                  email: "test@example.com",
                },
                conversation: {
                  id: "conv-1",
                  title: "Test Thread",
                },
                upvoteCount: 0,
                downvoteCount: 0,
                userVote: null,
              },
            },
          } as CreateThreadMessageOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "conv-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "conv-1",
              allMessages: [],
            },
          },
        },
      },
    ];

    let successCalled = false;

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          onSuccess={() => {
            successCalled = true;
          }}
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    // Type the message content into the editor
    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Test message content");

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // Wait for mutation and Apollo cache updates
    await page.waitForTimeout(1000);

    expect(successCalled).toBe(true);
  });

  test("calls onCancel when cancel button clicked", async ({ mount, page }) => {
    let cancelCalled = false;

    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          replyingToUsername="testuser"
          onCancel={() => {
            cancelCalled = true;
          }}
        />
      </MockedProvider>
    );

    const cancelButton = page.getByRole("button", { name: /cancel/i });
    await cancelButton.click();

    expect(cancelCalled).toBe(true);
  });
});

test.describe("ReplyForm - Nested Reply", () => {
  test("renders for nested reply", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    await expect(page.locator(".ProseMirror")).toBeVisible();
    await expect(page.getByText(/replying to/i)).toBeVisible();
    await expect(page.getByText("@testuser")).toBeVisible();
  });

  test("shows username in placeholder for nested reply", async ({
    mount,
    page,
  }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    // Check editor is visible with empty state (TipTap renders placeholders as CSS pseudo-elements)
    await expect(page.locator(".ProseMirror p.is-editor-empty")).toBeVisible();
    // Check the "Replying to" label is visible
    await expect(page.getByText("@testuser")).toBeVisible();
  });

  test("submits nested reply", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: REPLY_TO_MESSAGE,
          variables: {
            parentMessageId: "msg-1",
            content: "Test reply content",
          },
        },
        result: {
          data: {
            replyToMessage: {
              ok: true,
              message: "Reply created successfully",
              obj: {
                id: "msg-2",
                content: "<p>Test reply</p>",
                created: "2025-01-01T00:00:00Z",
                modified: "2025-01-01T00:00:00Z",
                creator: {
                  id: "user-2",
                  username: "replier",
                  email: "replier@example.com",
                },
                parentMessage: {
                  id: "msg-1",
                  content: "<p>Original message</p>",
                  creator: {
                    id: "user-1",
                    username: "testuser",
                  },
                },
                conversation: {
                  id: "conv-1",
                  title: "Test Thread",
                },
                upvoteCount: 0,
                downvoteCount: 0,
                userVote: null,
              },
            },
          } as ReplyToMessageOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "conv-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "conv-1",
              allMessages: [],
            },
          },
        },
      },
    ];

    let successCalled = false;

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onSuccess={() => {
            successCalled = true;
          }}
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    // Type the reply content into the editor
    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Test reply content");

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // Wait for mutation and Apollo cache updates
    await page.waitForTimeout(1000);

    expect(successCalled).toBe(true);
  });

  test("displays error on mutation failure", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: REPLY_TO_MESSAGE,
          variables: {
            parentMessageId: "msg-1",
            content: "Test reply content",
          },
        },
        result: {
          data: {
            replyToMessage: {
              ok: false,
              message: "Parent message not found",
              obj: null,
            },
          } as ReplyToMessageOutput,
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onSuccess={() => {}}
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    // Type the reply content into the editor
    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Test reply content");

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // Wait for mutation and error handling
    await page.waitForTimeout(1000);

    // Error message appears (use .first() since it may appear in multiple places)
    await expect(
      page.getByText(/parent message not found/i).first()
    ).toBeVisible();
  });

  test("validates required content before submit", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onCancel={() => {}}
        />
      </MockedProvider>
    );

    // Send button should be disabled when content is empty
    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();
  });

  test("disables form while submitting", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: REPLY_TO_MESSAGE,
          variables: {
            parentMessageId: "msg-1",
            content: "Test reply content",
          },
        },
        // Delay response to test loading state
        delay: 1000,
        result: {
          data: {
            replyToMessage: {
              ok: true,
              message: "Reply created successfully",
              obj: {
                id: "msg-2",
                content: "<p>Test reply</p>",
                created: "2025-01-01T00:00:00Z",
                modified: "2025-01-01T00:00:00Z",
                creator: {
                  id: "user-2",
                  username: "replier",
                  email: "replier@example.com",
                },
                parentMessage: {
                  id: "msg-1",
                  content: "<p>Original message</p>",
                  creator: {
                    id: "user-1",
                    username: "testuser",
                  },
                },
                conversation: {
                  id: "conv-1",
                  title: "Test Thread",
                },
                upvoteCount: 0,
                downvoteCount: 0,
                userVote: null,
              },
            },
          } as ReplyToMessageOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "conv-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "conv-1",
              allMessages: [],
            },
          },
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onCancel={() => {}}
          initialContent="<p>Test reply content</p>"
        />
      </MockedProvider>
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await sendButton.click();

    // While loading, button should be disabled
    await page.waitForTimeout(200);
    await expect(sendButton).toBeDisabled();
  });

  test("auto-focuses editor when autoFocus is true", async ({
    mount,
    page,
  }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ReplyForm
          conversationId="conv-1"
          parentMessageId="msg-1"
          replyingToUsername="testuser"
          onCancel={() => {}}
          autoFocus={true}
        />
      </MockedProvider>
    );

    const editor = page.locator(".ProseMirror");

    // Wait for editor to be focused
    await expect(editor).toHaveClass(/ProseMirror-focused/);
    await page.waitForTimeout(100);

    // Should be able to type without clicking
    await page.keyboard.type("Auto-focused!");

    await expect(editor).toContainText("Auto-focused!");
  });
});
