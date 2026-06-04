import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusType } from "../src/types/graphql-api";
import { CorpusHomeTestWrapper } from "./CorpusHomeTestWrapper";
import {
  GET_CORPUS_STATS,
  GET_CORPUS_WITH_HISTORY,
  GET_DOCUMENT_RELATIONSHIPS,
  GET_CORPUS_DOCUMENTS_FOR_TOC,
  GET_CONVERSATIONS,
} from "../src/graphql/queries";
import {
  DOCUMENT_RELATIONSHIP_TOC_LIMIT,
  CORPUS_DOCUMENTS_TOC_LIMIT,
  CONVERSATION_TYPE,
  RECENT_THREAD_LIMIT,
} from "../src/assets/configurations/constants";
import { PermissionTypes } from "../src/components/types";
import { docScreenshot } from "./utils/docScreenshot";
import { buildMentionSearchMocks } from "./utils/mentionSearchMocks";

/* --------------------------------------------------------------------------
 * Mock data & helpers
 * -------------------------------------------------------------------------- */
const dummyCorpus: CorpusType = {
  id: "CORPUS_1",
  title: "Playwright Test Corpus",
  isPublic: false,
  description: "Dummy corpus for component-testing CorpusHome.",
  created: new Date().toISOString(),
  modified: new Date().toISOString(),
  creator: {
    id: "USER_1",
    slug: "tester",
    email: "tester@example.com",
    __typename: "UserType",
  },
  labelSet: null,
  allowComments: true,
  preferredEmbedder: null,
  myPermissions: [
    "update_corpus",
    "read_corpus",
  ] as unknown as PermissionTypes[],
  analyses: {
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
    },
    edges: [],
  },
  annotations: {
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
    },
    edges: [],
  },
  documents: {
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
    },
    edges: [],
    totalCount: 2,
  },
  __typename: "CorpusType",
};

// Document relationships mock - used for DocumentTableOfContents
// Must include parent relationships for TOC to render content
const documentRelationshipsMock: MockedResponse = {
  request: {
    query: GET_DOCUMENT_RELATIONSHIPS,
    variables: {
      corpusId: dummyCorpus.id,
      first: DOCUMENT_RELATIONSHIP_TOC_LIMIT,
    },
  },
  result: {
    data: {
      documentRelationships: {
        edges: [
          {
            node: {
              id: "rel-1",
              relationshipType: "RELATIONSHIP",
              data: null,
              sourceDocument: {
                id: "doc-child",
                title: "Child Document",
                icon: null,
                slug: "child-document",
                creator: { slug: "test-user" },
              },
              targetDocument: {
                id: "doc-parent",
                title: "Parent Document",
                icon: null,
                slug: "parent-document",
                creator: { slug: "test-user" },
              },
              annotationLabel: {
                id: "label-1",
                text: "parent",
                color: "#3b82f6",
                icon: null,
              },
              corpus: { id: dummyCorpus.id },
              creator: { id: "USER_1", username: "testuser" },
              created: "2025-01-01T00:00:00Z",
              modified: "2025-01-01T00:00:00Z",
              myPermissions: ["read"],
              __typename: "DocumentRelationshipType",
            },
            __typename: "DocumentRelationshipTypeEdge",
          },
        ],
        totalCount: 1,
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        __typename: "DocumentRelationshipTypeConnection",
      },
    },
  },
};

// Documents mock for TOC - corresponds to the relationship mock documents
const corpusDocumentsMock: MockedResponse = {
  request: {
    query: GET_CORPUS_DOCUMENTS_FOR_TOC,
    variables: {
      corpusId: dummyCorpus.id,
      first: CORPUS_DOCUMENTS_TOC_LIMIT,
    },
  },
  result: {
    data: {
      documents: {
        edges: [
          {
            node: {
              id: "doc-parent",
              title: "Parent Document",
              description: "A parent document for testing",
              slug: "parent-document",
              icon: null,
              fileType: "application/pdf",
              creator: { slug: "test-user" },
              __typename: "DocumentType",
            },
            __typename: "DocumentTypeEdge",
          },
          {
            node: {
              id: "doc-child",
              title: "Child Document",
              description: "A child document for testing",
              slug: "child-document",
              icon: null,
              fileType: "application/pdf",
              creator: { slug: "test-user" },
              __typename: "DocumentType",
            },
            __typename: "DocumentTypeEdge",
          },
        ],
        totalCount: 2,
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        __typename: "DocumentTypeConnection",
      },
    },
  },
};

const corpusHistoryMock: MockedResponse = {
  request: {
    query: GET_CORPUS_WITH_HISTORY,
    variables: { id: dummyCorpus.id },
  },
  result: {
    data: {
      corpus: {
        id: dummyCorpus.id,
        slug: "test-corpus",
        title: dummyCorpus.title,
        description: dummyCorpus.description,
        descriptionPreview: dummyCorpus.description,
        created: dummyCorpus.created,
        modified: dummyCorpus.modified,
        isPublic: dummyCorpus.isPublic,
        isPersonal: dummyCorpus.isPersonal ?? false,
        myPermissions: dummyCorpus.myPermissions,
        creator: dummyCorpus.creator,
        labelSet: dummyCorpus.labelSet,
        descriptionRevisions: [],
        __typename: "CorpusType",
      },
    },
  },
};

// Conversations mock for RecentDiscussions component
const conversationsMock: MockedResponse = {
  request: {
    query: GET_CONVERSATIONS,
    variables: {
      corpusId: dummyCorpus.id,
      conversationType: CONVERSATION_TYPE.THREAD,
      limit: RECENT_THREAD_LIMIT,
    },
  },
  result: {
    data: {
      conversations: {
        edges: [
          {
            node: {
              id: "thread-1",
              conversationType: CONVERSATION_TYPE.THREAD,
              title: "How do I interpret Section 4.2?",
              description: "Question about the interpretation",
              createdAt: new Date(
                Date.now() - 2 * 60 * 60 * 1000
              ).toISOString(),
              updatedAt: new Date(
                Date.now() - 1 * 60 * 60 * 1000
              ).toISOString(),
              created: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
              modified: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
              creator: {
                id: "USER_2",
                username: "alice",
                email: "alice@example.com",
                __typename: "UserType",
              },
              chatWithCorpus: null,
              chatWithDocument: null,
              chatMessages: {
                totalCount: 5,
                __typename: "ChatMessageTypeConnection",
              },
              isPublic: true,
              myPermissions: [],
              upvoteCount: 3,
              downvoteCount: 0,
              userVote: null,
              isLocked: false,
              lockedBy: null,
              lockedAt: null,
              isPinned: false,
              pinnedBy: null,
              pinnedAt: null,
              deletedAt: null,
              __typename: "ConversationType",
            },
            __typename: "ConversationTypeEdge",
          },
          {
            node: {
              id: "thread-2",
              conversationType: CONVERSATION_TYPE.THREAD,
              title: "Suggestion: Add cross-reference annotations",
              description: "Idea for improvement",
              createdAt: new Date(
                Date.now() - 24 * 60 * 60 * 1000
              ).toISOString(),
              updatedAt: new Date(
                Date.now() - 12 * 60 * 60 * 1000
              ).toISOString(),
              created: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
              modified: new Date(
                Date.now() - 12 * 60 * 60 * 1000
              ).toISOString(),
              creator: {
                id: "USER_3",
                username: "bob",
                email: "bob@example.com",
                __typename: "UserType",
              },
              chatWithCorpus: null,
              chatWithDocument: null,
              chatMessages: {
                totalCount: 2,
                __typename: "ChatMessageTypeConnection",
              },
              isPublic: true,
              myPermissions: [],
              upvoteCount: 1,
              downvoteCount: 0,
              userVote: null,
              isLocked: false,
              lockedBy: null,
              lockedAt: null,
              isPinned: false,
              pinnedBy: null,
              pinnedAt: null,
              deletedAt: null,
              __typename: "ConversationType",
            },
            __typename: "ConversationTypeEdge",
          },
        ],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        totalCount: 2,
        __typename: "ConversationTypeConnection",
      },
    },
  },
};

// Empty conversations mock (no discussions yet)
const emptyConversationsMock: MockedResponse = {
  request: {
    query: GET_CONVERSATIONS,
    variables: {
      corpusId: dummyCorpus.id,
      conversationType: CONVERSATION_TYPE.THREAD,
      limit: RECENT_THREAD_LIMIT,
    },
  },
  result: {
    data: {
      conversations: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        totalCount: 0,
        __typename: "ConversationTypeConnection",
      },
    },
  },
};

const mocks: MockedResponse[] = [
  {
    request: {
      query: GET_CORPUS_STATS,
      variables: { corpusId: dummyCorpus.id },
    },
    result: {
      data: {
        corpusStats: {
          totalDocs: 3,
          totalAnnotations: 5,
          totalComments: 0,
          totalAnalyses: 0,
          totalExtracts: 0,
          totalThreads: 0,
          totalChats: 0,
          totalRelationships: 0,
          __typename: "CorpusStatsType",
        },
      },
    },
  },
  // Duplicate mocks for cache-and-network fetch policy
  documentRelationshipsMock,
  { ...documentRelationshipsMock },
  // Documents mock for TOC
  corpusDocumentsMock,
  { ...corpusDocumentsMock },
  // Corpus history mock
  corpusHistoryMock,
  { ...corpusHistoryMock },
  // Conversations mock for RecentDiscussions
  conversationsMock,
  { ...conversationsMock },
  // ``InlineChatBar`` now plumbs ``corpusId`` into ``useChatMentionPicker``
  // → ``useUnifiedMentionSearch``, which fires ``searchAgentsForMention``
  // with the empty fragment on mount (agents are special-cased to ignore
  // the ``minChars`` gate so the picker is reachable on a bare ``@``).
  // Without these mocks, MockedProvider logs "no more mocked responses"
  // for every CorpusHome test that mounts the landing view. The other
  // four category mocks in ``buildMentionSearchMocks`` are still gated by
  // ``minChars`` and won't fire on the empty fragment, but bundling them
  // here keeps the test setup symmetric with ChatTray/CorpusChat.
  ...buildMentionSearchMocks("", dummyCorpus.id, []),
];

/**
 * Mount helper – wraps CorpusHome in MockedProvider with minimal cache.
 */
function mountCorpusHome(mount: any) {
  return mount(<CorpusHomeTestWrapper mocks={mocks} corpus={dummyCorpus} />);
}

/* --------------------------------------------------------------------------
 * Tests for Landing View
 * -------------------------------------------------------------------------- */

test.use({ viewport: { width: 1200, height: 800 } });

test("defaults to landing view when no view URL param", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Landing view should be visible
  const landingView = page.getByTestId("corpus-home-landing");
  await expect(landingView).toBeVisible();

  // Details view should not be visible
  const detailsView = page.getByTestId("corpus-home-details");
  await expect(detailsView).toBeHidden();
});

test("renders landing view with corpus title and badge", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // CORPUS badge should be visible (exact match to avoid matching "Corpuses" breadcrumb)
  await expect(page.getByText("CORPUS", { exact: true })).toBeVisible();

  // Title should be visible
  const title = page.getByTestId("corpus-home-landing-title");
  await expect(title).toBeVisible();
  await expect(title).toContainText(dummyCorpus.title);
});

test("renders landing view with metadata and access badge", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Metadata row should be visible
  const metadata = page.getByTestId("corpus-home-landing-metadata");
  await expect(metadata).toBeVisible();

  // Privacy badge reflects corpus.isPublic
  const privacyText = dummyCorpus.isPublic ? "Public" : "Private";
  await expect(metadata.locator(`text=${privacyText}`)).toBeVisible();

  // Creator name
  await expect(metadata.locator("text=tester")).toBeVisible();
});

test("renders landing view with chat bar and quick actions", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Chat bar should be visible
  const chatBar = page.getByTestId("corpus-home-landing-chat");
  await expect(chatBar).toBeVisible();

  // Chat input placeholder
  await expect(
    chatBar.locator('textarea[placeholder*="Ask a question"]')
  ).toBeVisible();

  // Quick action chips
  await expect(chatBar.locator("text=Summarize")).toBeVisible();
  await expect(chatBar.locator("text=Search")).toBeVisible();
  await expect(chatBar.locator("text=Analyze")).toBeVisible();

  await docScreenshot(page, "readme--corpus-home--with-chat");
});

test("typing @ in landing chat input opens the agent picker", async ({
  mount,
  page,
}) => {
  // The landing chat input has data-testid="corpus-home-landing-chat-input"
  // (testId composition: parent "corpus-home-landing-chat" + "-input").
  // It uses the shared ``useChatMentionPicker`` hook with ``corpusId`` set
  // to the landing corpus, so the rich-mention agent picker should work
  // here exactly the same as it does in ChatTray and CorpusChat.
  await mount(
    <CorpusHomeTestWrapper
      mocks={[
        ...mocks.filter((m) => {
          // Replace the default empty-fragment agent mock with one that
          // surfaces a real agent so the popover has something to render.
          const q = (m.request as any)?.query;
          // Drop the empty-fragment ``searchAgentsForMention`` mock added
          // above so we can re-add a populated one below.
          if (
            q &&
            q.definitions?.[0]?.name?.value === "SearchAgentsForMention"
          ) {
            const vars = (m.request as any)?.variables || {};
            return !(
              vars.textSearch === "" && vars.corpusId === dummyCorpus.id
            );
          }
          return true;
        }),
        ...buildMentionSearchMocks("", dummyCorpus.id, [
          {
            id: "agent-landing-1",
            name: "Landing Research Bot",
            slug: "landing-research-bot",
            description: "Research from the landing bar",
            scope: "GLOBAL",
            mentionFormat: null,
            corpus: null,
          },
        ]),
      ]}
      corpus={dummyCorpus}
    />
  );

  const chatInput = page.getByTestId("corpus-home-landing-chat-input");
  await expect(chatInput).toBeVisible();
  await chatInput.focus();
  await chatInput.pressSequentially("@", { delay: 30 });

  await expect(page.getByTestId("agent-mention-popover")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("Landing Research Bot")).toBeVisible();
});

test("renders landing view with description as subtitle", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Description should be visible as subtitle in hero section
  const description = page.getByTestId("corpus-home-landing-description");
  await expect(description).toBeVisible();

  // Description text (first line of the description)
  await expect(description).toContainText("Dummy corpus for component-testing");
});

test("renders Browse documents link in landing view", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Browse documents link should be visible
  const viewDetailsBtn = page.getByTestId(
    "corpus-home-landing-view-details-btn"
  );
  await expect(viewDetailsBtn).toBeVisible();
  await expect(viewDetailsBtn).toContainText("Browse documents");
});

test.describe("mobile corpus landing return navigation", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows a mobile return control for the Documents collection", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusHomeTestWrapper
        mocks={mocks}
        corpus={{ ...dummyCorpus, isPersonal: true }}
        onNavigateToCorpuses={() => {}}
        navigateBackLabel="Documents"
      />
    );

    const returnButton = page.getByTestId(
      "corpus-home-landing-mobile-return-btn"
    );
    await expect(returnButton).toBeVisible();
    await expect(returnButton).toHaveText(/Documents/);

    await expect(page.getByTestId("corpus-home-landing-title")).toBeVisible();
    await expect(page.getByTestId("corpus-home-landing-chat")).toBeVisible();

    const returnBox = await returnButton.boundingBox();
    const titleBox = await page
      .getByTestId("corpus-home-landing-title")
      .boundingBox();
    const chatBox = await page
      .getByTestId("corpus-home-landing-chat")
      .boundingBox();

    expect(returnBox).not.toBeNull();
    expect(titleBox).not.toBeNull();
    expect(chatBox).not.toBeNull();
    expect(returnBox!.y + returnBox!.height).toBeLessThan(titleBox!.y);
    expect(titleBox!.y + titleBox!.height).toBeLessThan(chatBox!.y);
  });
});

test("clicking View Details switches to details view", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Initially in landing view
  await expect(page.getByTestId("corpus-home-landing")).toBeVisible();

  // Click View Details button
  const viewDetailsBtn = page.getByTestId(
    "corpus-home-landing-view-details-btn"
  );
  await viewDetailsBtn.click();

  // Should now show details view
  await expect(page.getByTestId("corpus-home-details")).toBeVisible();
  await expect(page.getByTestId("corpus-home-landing")).toBeHidden();
});

/* --------------------------------------------------------------------------
 * Tests for Details View
 * -------------------------------------------------------------------------- */

test("shows details view when view=details URL param is set", async ({
  mount,
  page,
}) => {
  // Mount with initialView="details"
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      initialView="details"
    />
  );

  // Details view should be visible
  const detailsView = page.getByTestId("corpus-home-details");
  await expect(detailsView).toBeVisible();

  // Landing view should not be visible
  const landingView = page.getByTestId("corpus-home-landing");
  await expect(landingView).toBeHidden();
});

test("details view shows back button", async ({ mount, page }) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      initialView="details"
    />
  );

  // Back button should be visible
  const backBtn = page.getByTestId("corpus-home-details-back-btn");
  await expect(backBtn).toBeVisible();
  await expect(backBtn).toContainText("Overview");
});

test("details view shows corpus title", async ({ mount, page }) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      initialView="details"
    />
  );

  // Title should be visible
  const title = page.getByTestId("corpus-home-details-title");
  await expect(title).toBeVisible();
  await expect(title).toContainText(dummyCorpus.title);
});

test("clicking back button in details view returns to landing", async ({
  mount,
  page,
}) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      initialView="details"
    />
  );

  // Initially in details view
  await expect(page.getByTestId("corpus-home-details")).toBeVisible({
    timeout: 10000,
  });

  // Click back button
  const backBtn = page.getByTestId("corpus-home-details-back-btn");
  await backBtn.click();

  // Wait for URL change to propagate to reactive var and re-render
  // Should now show landing view
  await expect(page.getByTestId("corpus-home-landing")).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByTestId("corpus-home-details")).toBeHidden();
});

test("details view shows two-column layout on desktop", async ({
  mount,
  page,
}) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      initialView="details"
    />
  );

  // Both Documents and About sections should be visible (minimalist labels)
  // Use specific selector to avoid matching metadata and mobile tabs
  await expect(
    page.locator("span").filter({ hasText: /^Documents$/ })
  ).toBeVisible();
  await expect(
    page.locator("span").filter({ hasText: /^About$/ })
  ).toBeVisible();
});

/* --------------------------------------------------------------------------
 * Tests for Breadcrumbs
 * -------------------------------------------------------------------------- */

test("landing view has centered breadcrumbs", async ({ mount, page }) => {
  await mountCorpusHome(mount);

  // Breadcrumbs should be visible
  const breadcrumbs = page.getByTestId("corpus-home-landing-breadcrumbs");
  await expect(breadcrumbs).toBeVisible();

  // Should have Corpuses link
  await expect(breadcrumbs.locator("text=Corpuses")).toBeVisible();

  // Should have current corpus name
  await expect(breadcrumbs.locator(".current")).toContainText(
    dummyCorpus.title
  );
});

/* --------------------------------------------------------------------------
 * Tests for Recent Discussions Feed
 * -------------------------------------------------------------------------- */

test("landing view shows recent discussions feed with threads", async ({
  mount,
  page,
}) => {
  await mountCorpusHome(mount);

  // Wait for discussions feed to render
  const feed = page.getByTestId("corpus-home-landing-discussions");
  await expect(feed).toBeVisible({ timeout: 10000 });

  // Header should show "Discussions" label and "View all" link
  await expect(feed.locator("text=Discussions")).toBeVisible();
  await expect(feed.locator("text=View all")).toBeVisible();

  // Thread items should be visible
  await expect(
    page.getByTestId("corpus-home-landing-discussions-thread-thread-1")
  ).toBeVisible();
  await expect(
    page.getByTestId("corpus-home-landing-discussions-thread-thread-2")
  ).toBeVisible();

  // Thread titles should display
  await expect(
    page.locator("text=How do I interpret Section 4.2?")
  ).toBeVisible();
  await expect(
    page.locator("text=Suggestion: Add cross-reference annotations")
  ).toBeVisible();

  // Screenshot of the full landing view with discussion feed
  await docScreenshot(page, "corpus--landing--with-discussions", {
    fullPage: true,
  });
});

test("landing view shows empty state when no discussions exist", async ({
  mount,
  page,
}) => {
  // Mount with empty conversations mock
  const emptyMocks: MockedResponse[] = [
    ...mocks.filter((m) => m.request.query !== GET_CONVERSATIONS),
    emptyConversationsMock,
    { ...emptyConversationsMock },
  ];

  await mount(
    <CorpusHomeTestWrapper mocks={emptyMocks} corpus={dummyCorpus} />
  );

  // Wait for empty state to render
  const emptyState = page.getByTestId("corpus-home-landing-discussions-empty");
  await expect(emptyState).toBeVisible({ timeout: 10000 });
  await expect(emptyState).toContainText("No discussions yet");

  await docScreenshot(page, "corpus--landing--no-discussions", {
    fullPage: true,
  });
});

/* --------------------------------------------------------------------------
 * Tests for Focus / Power Mode Toggle
 * -------------------------------------------------------------------------- */

test("does not render mode toggle when onModeToggle is not provided", async ({
  mount,
  page,
}) => {
  // Default mountCorpusHome does not pass onModeToggle
  await mountCorpusHome(mount);

  // Landing view should render
  await expect(page.getByTestId("corpus-home-landing")).toBeVisible();

  // Mode toggle should NOT be in the DOM (not just CSS-hidden)
  await expect(page.getByTestId("landing-mode-toggle")).toHaveCount(0);
});

test("renders Explore/Manage pill toggle when onModeToggle is provided", async ({
  mount,
  page,
}) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      onModeToggle={() => {}}
      isPowerUserMode={false}
    />
  );

  // Toggle should be visible as floating element
  const toggle = page.getByTestId("landing-mode-toggle");
  await expect(toggle).toBeVisible({ timeout: 10000 });

  // "Explore" label should be active (non-power-user mode)
  // "Manage" label should be present but inactive
  await expect(toggle.locator("text=Explore")).toBeVisible();
  await expect(toggle.locator("text=Manage")).toBeVisible();

  // Title should reflect explore-mode state
  await expect(toggle).toHaveAttribute(
    "title",
    "Switch to corpus management view"
  );

  await docScreenshot(page, "corpus--mode-toggle--explore-mode");
});

test("pill toggle reflects isPowerUserMode=true state", async ({
  mount,
  page,
}) => {
  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      onModeToggle={() => {}}
      isPowerUserMode={true}
    />
  );

  const toggle = page.getByTestId("landing-mode-toggle");
  await expect(toggle).toBeVisible({ timeout: 10000 });

  // In manage mode the toggle title should reflect "Switch to explore view"
  await expect(toggle).toHaveAttribute("title", "Switch to explore view");
});

test("clicking mode toggle fires onModeToggle callback", async ({
  mount,
  page,
}) => {
  let toggled = false;

  await mount(
    <CorpusHomeTestWrapper
      mocks={mocks}
      corpus={dummyCorpus}
      onModeToggle={() => {
        toggled = true;
      }}
      isPowerUserMode={false}
    />
  );

  const toggle = page.getByTestId("landing-mode-toggle");
  await expect(toggle).toBeVisible({ timeout: 10000 });
  await toggle.click();

  // Use poll to account for async proxy callback across Playwright CT boundary
  await expect.poll(() => toggled, { timeout: 5000 }).toBe(true);
});

/* --------------------------------------------------------------------------
 * Tests for Discussions Inline View
 * -------------------------------------------------------------------------- */

test("discussions view shows when view=discussions URL param is set", async ({
  mount,
  page,
}) => {
  // Need additional mocks for the full CorpusDiscussionsView
  // (it queries with limit: 100 for stats)
  const discussionViewMocks: MockedResponse[] = [
    ...mocks,
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: {
          corpusId: dummyCorpus.id,
          conversationType: CONVERSATION_TYPE.THREAD,
          limit: 100,
        },
      },
      result: conversationsMock.result,
    },
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: {
          corpusId: dummyCorpus.id,
          conversationType: CONVERSATION_TYPE.THREAD,
          limit: 100,
        },
      },
      result: conversationsMock.result,
    },
  ];

  await mount(
    <CorpusHomeTestWrapper
      mocks={discussionViewMocks}
      corpus={dummyCorpus}
      initialView="discussions"
    />
  );

  // Discussions inline view should be visible
  const discussionsView = page.getByTestId("corpus-home-discussions");
  await expect(discussionsView).toBeVisible({ timeout: 10000 });

  // Back button should show "Overview"
  const backBtn = page.getByTestId("corpus-home-discussions-back-btn");
  await expect(backBtn).toBeVisible();
  await expect(backBtn).toContainText("Overview");

  // Landing view should not be visible
  await expect(page.getByTestId("corpus-home-landing")).toBeHidden();

  await docScreenshot(page, "corpus--discussions-inline--thread-list");
});
