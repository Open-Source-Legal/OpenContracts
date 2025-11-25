import { test, expect } from "@playwright/experimental-ct-react";
import { ThreadDetail } from "../../src/components/threads/ThreadDetail";
import { ThreadTestWrapper } from "./utils/ThreadTestWrapper";
import {
  createMockThreadWithMessages,
  createMockThread,
} from "./utils/mockThreadData";
import { GET_THREAD_DETAIL } from "../../src/graphql/queries";

test.describe("ThreadDetail", () => {
  test("renders thread detail with messages", async ({ mount }) => {
    const mockThread = createMockThreadWithMessages();

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: mockThread.id },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId={mockThread.id} corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Check thread title
    await expect(component.getByText(mockThread.title!)).toBeVisible({
      timeout: 5000,
    });

    // Check that messages are rendered
    await expect(component.getByText("First message")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Reply to first message")).toBeVisible({
      timeout: 5000,
    });
  });

  test("displays nested replies with correct indentation", async ({
    mount,
  }) => {
    const mockThread = createMockThreadWithMessages();

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: mockThread.id },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId={mockThread.id} corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Check nested reply is visible
    await expect(component.getByText("Nested reply")).toBeVisible({
      timeout: 5000,
    });

    // Check that reply count is shown
    await expect(
      component.getByText("2 replies", { exact: false })
    ).toBeVisible({
      timeout: 5000,
    });
  });

  test("shows pinned and locked badges", async ({ mount }) => {
    const mockThread = createMockThread({
      id: "thread-1",
      title: "Pinned and Locked Thread",
      isPinned: true,
      isLocked: true,
      allMessages: [],
    });

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId="thread-1" corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    await expect(component.getByText("Pinned")).toBeVisible({ timeout: 5000 });
    await expect(component.getByText("Locked")).toBeVisible({ timeout: 5000 });
  });

  test("shows empty state when no messages", async ({ mount }) => {
    const mockThread = createMockThread({
      id: "thread-1",
      title: "Empty Thread",
      allMessages: [],
    });

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId="thread-1" corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    await expect(
      component.getByText("No messages yet", { exact: false })
    ).toBeVisible({
      timeout: 5000,
    });
  });

  test("back button navigates correctly", async ({ mount, page }) => {
    const mockThread = createMockThread({
      id: "thread-1",
      allMessages: [],
    });

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper
        mocks={mocks}
        initialRoute="/corpus/corpus-1/discussions/thread-1"
      >
        <ThreadDetail conversationId="thread-1" corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Find and click back button
    const backButton = component.getByRole("button", {
      name: /back to discussions/i,
    });
    await expect(backButton).toBeVisible({ timeout: 5000 });
  });

  test("handles loading state", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        delay: 100000, // Long delay to test loading
        result: {
          data: {
            conversation: null,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId="thread-1" corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await expect(component.getByText("Loading discussion...")).toBeVisible({
      timeout: 2000,
    });
  });
});
