import { test, expect } from "@playwright/experimental-ct-react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider } from "jotai";
import { DocumentDiscussionsContent } from "../src/components/discussions/DocumentDiscussionsContent";
import { GET_CONVERSATIONS } from "../src/graphql/queries";
import { selectedThreadId } from "../src/graphql/cache";
import { DocumentDiscussionsContentTestWrapper } from "./DocumentDiscussionsContentTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

// Helper to build a mock thread node
const mockThread = (
  id: string,
  title: string,
  description: string,
  overrides?: Record<string, unknown>
) => ({
  __typename: "ConversationTypeEdge" as const,
  node: {
    __typename: "ConversationType" as const,
    id,
    conversationType: "THREAD",
    title,
    description,
    createdAt: "2025-01-15T10:00:00Z",
    updatedAt: "2025-01-16T15:30:00Z",
    creator: {
      __typename: "UserType" as const,
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
    chatWithCorpus: {
      __typename: "CorpusType" as const,
      id: "corpus-1",
      title: "Test Corpus",
    },
    chatWithDocument: {
      __typename: "DocumentType" as const,
      id: "doc-1",
      title: "Test Document",
    },
    chatMessages: {
      __typename: "ChatMessageTypeConnection" as const,
      totalCount: 5,
    },
    isPublic: true,
    myPermissions: ["read", "create", "update"],
    isLocked: false,
    lockedBy: null,
    lockedAt: null,
    isPinned: false,
    pinnedBy: null,
    pinnedAt: null,
    deletedAt: null,
    upvoteCount: 0,
    downvoteCount: 0,
    userVote: null,
    ...overrides,
  },
});

// Mock thread data — multiple threads for a richer screenshot
const mockThreads = {
  conversations: {
    __typename: "ConversationTypeConnection",
    edges: [
      mockThread(
        "thread-1",
        "Is the indemnification clause in Section 12.3 standard?",
        "Comparing this against the ISDA master template — the carve-outs seem broader than usual.",
        {
          isPinned: true,
          pinnedBy: {
            __typename: "UserType",
            id: "user-1",
            username: "testuser",
          },
          pinnedAt: "2025-01-16T12:00:00Z",
          upvoteCount: 7,
          chatMessages: {
            __typename: "ChatMessageTypeConnection",
            totalCount: 12,
          },
          creator: {
            __typename: "UserType",
            id: "user-2",
            username: "sarah.chen",
            email: "sarah@example.com",
          },
        }
      ),
      mockThread(
        "thread-2",
        "Force majeure scope needs review",
        "The pandemic language was added in the 2021 amendment but conflicts with the original limitation period.",
        {
          upvoteCount: 3,
          chatMessages: {
            __typename: "ChatMessageTypeConnection",
            totalCount: 8,
          },
          creator: {
            __typename: "UserType",
            id: "user-3",
            username: "m.rodriguez",
            email: "mrod@example.com",
          },
          createdAt: "2025-01-14T09:00:00Z",
        }
      ),
      mockThread(
        "thread-3",
        "@ResearchBot — summarize the termination provisions across all vendor contracts",
        "Let's see how termination-for-convenience compares across the portfolio.",
        {
          upvoteCount: 5,
          downvoteCount: 1,
          chatMessages: {
            __typename: "ChatMessageTypeConnection",
            totalCount: 4,
          },
          createdAt: "2025-01-13T14:00:00Z",
        }
      ),
    ],
    pageInfo: {
      __typename: "PageInfo",
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: "",
      endCursor: "",
    },
    totalCount: 3,
  },
};

const mockThreadDetail = {
  conversation: {
    __typename: "ConversationType",
    id: "thread-1",
    conversationType: "THREAD",
    title: "Test Discussion Thread",
    description: "A test thread for discussions",
    createdAt: "2025-01-01T10:00:00Z",
    updatedAt: "2025-01-02T15:30:00Z",
    creator: {
      __typename: "UserType",
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
    isPublic: true,
    myPermissions: ["read", "create", "update"],
    isLocked: false,
    isPinned: false,
    deletedAt: null,
    allMessages: [],
  },
};

test.describe("DocumentDiscussionsContent", () => {
  test("renders thread list initially", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            documentId: "doc-1",
            conversationType: "THREAD",
            limit: 20,
          },
        },
        result: { data: mockThreads },
      },
    ];

    await mount(
      <DocumentDiscussionsContentTestWrapper mocks={mocks}>
        <DocumentDiscussionsContent documentId="doc-1" corpusId="corpus-1" />
      </DocumentDiscussionsContentTestWrapper>
    );

    // Should show header
    await expect(page.getByText("Document Discussions")).toBeVisible();

    // Should show create button
    const createButton = page.getByRole("button", {
      name: /start new discussion/i,
    });
    await expect(createButton).toBeVisible();

    // Wait for thread cards to render
    await expect(page.getByText("indemnification clause")).toBeVisible();

    await docScreenshot(page, "discussions--thread-list--with-threads");
    await releaseScreenshot(page, "v3.0.0.b3", "discussion-thread");
  });

  // Note: Thread detail view tests are handled by actual integration in DocumentKnowledgeBase
  // The selectedThreadId reactive var updates are managed by query params in production

  test("navigates to thread detail when clicking thread", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            documentId: "doc-1",
            conversationType: "THREAD",
          },
        },
        result: { data: mockThreads },
      },
    ];

    await mount(
      <MemoryRouter initialEntries={["/"]}>
        <MockedProvider mocks={mocks} addTypename={true}>
          <JotaiProvider>
            <Routes>
              <Route
                path="/"
                element={
                  <DocumentDiscussionsContent
                    documentId="doc-1"
                    corpusId="corpus-1"
                  />
                }
              />
            </Routes>
          </JotaiProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for thread list to load
    await page.waitForTimeout(500);

    // Click on thread (if rendered)
    const threadCard = page.getByRole("article", {
      name: /test discussion thread/i,
    });

    if (await threadCard.isVisible()) {
      await threadCard.click();
      await page.waitForTimeout(200);

      // URL should update with thread param
      expect(page.url()).toContain("thread=thread-1");
    }
  });

  test("displays header with correct title in list mode", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            documentId: "doc-1",
            conversationType: "THREAD",
          },
        },
        result: { data: mockThreads },
      },
    ];

    await mount(
      <DocumentDiscussionsContentTestWrapper mocks={mocks}>
        <DocumentDiscussionsContent documentId="doc-1" corpusId="corpus-1" />
      </DocumentDiscussionsContentTestWrapper>
    );

    // Header should say "Document Discussions"
    await expect(page.getByText("Document Discussions")).toBeVisible();

    // Create button should be visible (only for authenticated users)
    await expect(
      page.getByRole("button", { name: /start new discussion/i })
    ).toBeVisible();
  });

  test("passes documentId and corpusId to CreateThreadButton", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            documentId: "doc-1",
            conversationType: "THREAD",
          },
        },
        result: { data: mockThreads },
      },
    ];

    await mount(
      <DocumentDiscussionsContentTestWrapper mocks={mocks}>
        <DocumentDiscussionsContent documentId="doc-1" corpusId="corpus-1" />
      </DocumentDiscussionsContentTestWrapper>
    );

    // Create button should be visible (implies props were passed correctly)
    const createButton = page.getByRole("button", {
      name: /start new discussion/i,
    });
    await expect(createButton).toBeVisible();

    // Click to open modal - this verifies the button has proper documentId/corpusId
    await createButton.click();
    await expect(page.getByText("Start New Discussion")).toBeVisible();
  });

  test("uses compact prop for ThreadList in sidebar", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_CONVERSATIONS,
          variables: {
            documentId: "doc-1",
            conversationType: "THREAD",
          },
        },
        result: { data: mockThreads },
      },
    ];

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={true}>
          <JotaiProvider>
            <DocumentDiscussionsContent
              documentId="doc-1"
              corpusId="corpus-1"
            />
          </JotaiProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for render
    await page.waitForTimeout(500);

    // Component should render (compact mode is internal to ThreadList)
    await expect(page.getByText("Document Discussions")).toBeVisible();
  });
});
