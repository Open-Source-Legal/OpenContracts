import { test, expect } from "@playwright/experimental-ct-react";
import { ThreadList } from "../../src/components/threads/ThreadList";
import { ThreadTestWrapper } from "./utils/ThreadTestWrapper";
import { createMockThread } from "./utils/mockThreadData";
import { GET_CONVERSATIONS } from "../../src/graphql/queries";

test.describe("ThreadList", () => {
  test("renders thread list with mocked data", async ({ mount }) => {
    const mockThreads = [
      createMockThread({ id: "1", title: "First Thread", isPinned: true }),
      createMockThread({ id: "2", title: "Second Thread" }),
    ];

    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            corpusId: "corpus-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        result: {
          data: {
            conversations: {
              edges: mockThreads.map((thread) => ({
                node: thread,
                cursor: thread.id,
              })),
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "1",
                endCursor: "2",
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
    await component.waitFor({ timeout: 3000 });

    // Check that threads are rendered
    await expect(component.getByText("First Thread")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Second Thread")).toBeVisible({
      timeout: 5000,
    });

    // Check that pinned badge shows
    await expect(component.getByText("Pinned")).toBeVisible();
  });

  test("shows empty state when no threads", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            corpusId: "corpus-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        result: {
          data: {
            conversations: {
              edges: [],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "",
                endCursor: "",
              },
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

    await component.waitFor({ timeout: 3000 });

    await expect(
      component.getByText("No Discussions Yet", { exact: false })
    ).toBeVisible({ timeout: 5000 });
  });

  test("displays locked and deleted badges correctly", async ({ mount }) => {
    const mockThreads = [
      createMockThread({
        id: "1",
        title: "Locked Thread",
        isLocked: true,
      }),
      createMockThread({
        id: "2",
        title: "Deleted Thread",
        deletedAt: new Date().toISOString(),
      }),
    ];

    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            corpusId: "corpus-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        result: {
          data: {
            conversations: {
              edges: mockThreads.map((thread) => ({
                node: thread,
                cursor: thread.id,
              })),
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

    await component.waitFor({ timeout: 3000 });

    // Check badges
    const lockedBadges = component.getByText("Locked");
    await expect(lockedBadges).toBeVisible({ timeout: 5000 });

    const deletedBadges = component.getByText("Deleted");
    await expect(deletedBadges).toBeVisible({ timeout: 5000 });
  });

  test("displays message counts correctly", async ({ mount }) => {
    const mockThread = createMockThread({
      id: "1",
      title: "Thread with Messages",
      chatMessages: {
        totalCount: 15,
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: "",
          endCursor: "",
        },
        edges: [],
      },
    });

    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            corpusId: "corpus-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        result: {
          data: {
            conversations: {
              edges: [{ node: mockThread, cursor: "1" }],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "1",
                endCursor: "1",
              },
              totalCount: 1,
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

    await component.waitFor({ timeout: 3000 });

    await expect(component.getByText("15 replies")).toBeVisible({
      timeout: 5000,
    });
  });

  test("handles loading state", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            corpusId: "corpus-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        delay: 100000, // Long delay to test loading state
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

    // Check loading indicator appears
    await expect(component.getByText("Loading discussions...")).toBeVisible({
      timeout: 2000,
    });
  });
});
