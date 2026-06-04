import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { docScreenshot } from "./utils/docScreenshot";

// Wrappers
import { DiscoveryLandingTestWrapper } from "./DiscoveryLandingTestWrapper";
import { CorpusesTestWrapper } from "./CorpusesTestWrapper";
import { CorpusHomeTestWrapper } from "./CorpusHomeTestWrapper";

// GraphQL queries
import {
  GET_DISCOVERY_DATA,
  GetDiscoveryDataOutput,
} from "../src/graphql/landing-queries";
import {
  GET_CORPUSES,
  GET_CORPUS_STATS,
  GET_CORPUS_METADATA,
  GET_DOCUMENTS,
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
import { CorpusType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

/* ==========================================================================
 * Shared mock data
 * ========================================================================== */

/** Corpus used across all navigation steps */
const navCorpus: CorpusType = {
  id: "NAV_CORPUS_1",
  title: "SEC Filings Collection",
  icon: null,
  slug: "sec-filings-collection",
  isPublic: true,
  description:
    "A curated collection of SEC filings including 10-K, 10-Q, and 8-K reports from Fortune 500 companies for regulatory analysis.",
  created: "2025-11-15T10:00:00Z",
  modified: "2026-03-20T14:30:00Z",
  creator: {
    id: "USER_1",
    email: "analyst@opencontracts.org",
    username: "analyst",
    slug: "analyst",
    __typename: "UserType",
  },
  labelSet: null,
  allowComments: true,
  preferredEmbedder: null,
  upvoteCount: 0,
  downvoteCount: 0,
  score: 0,
  myVote: null,
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
    totalCount: 24,
  },
  __typename: "CorpusType",
};

const secondCorpus: CorpusType = {
  ...navCorpus,
  id: "NAV_CORPUS_2",
  title: "Employment Agreements Library",
  slug: "employment-agreements-library",
  description:
    "Standard employment agreements, NDAs, and non-compete clauses from various industries.",
  isPublic: true,
  documents: {
    ...navCorpus.documents,
    totalCount: 156,
  },
};

const thirdCorpus: CorpusType = {
  ...navCorpus,
  id: "NAV_CORPUS_3",
  title: "Real Estate Contracts",
  slug: "real-estate-contracts",
  description:
    "Commercial and residential real estate purchase agreements and lease contracts.",
  isPublic: false,
  documents: {
    ...navCorpus.documents,
    totalCount: 89,
  },
};

/* --------------------------------------------------------------------------
 * Step 1: Discovery Landing mocks
 * -------------------------------------------------------------------------- */

const discoveryMock: MockedResponse<GetDiscoveryDataOutput> = {
  request: {
    query: GET_DISCOVERY_DATA,
    variables: {
      corpusLimit: 6,
      discussionLimit: 5,
      leaderboardLimit: 6,
      conversationType: "THREAD",
    },
  },
  result: {
    data: {
      corpuses: {
        edges: [
          {
            node: {
              id: navCorpus.id,
              slug: "sec-filings-collection",
              title: navCorpus.title,
              description: navCorpus.description,
              descriptionPreview: navCorpus.description,
              icon: null,
              isPublic: true,
              created: navCorpus.created,
              creator: {
                id: "USER_1",
                username: "analyst",
                slug: "analyst",
              },
              documentCount: 24,
              annotationCount: 312,
              categories: [{ id: "cat-1", name: "Regulatory" }],
              engagementMetrics: {
                totalThreads: 8,
                totalMessages: 45,
                uniqueContributors: 6,
              },
            },
            __typename: "CorpusTypeEdge",
          },
          {
            node: {
              id: secondCorpus.id,
              slug: "employment-agreements-library",
              title: secondCorpus.title,
              description: secondCorpus.description,
              descriptionPreview: secondCorpus.description,
              icon: null,
              isPublic: true,
              created: "2025-09-01T08:00:00Z",
              creator: {
                id: "USER_2",
                username: "legalops",
                slug: "legalops",
              },
              documentCount: 156,
              annotationCount: 1023,
              categories: [{ id: "cat-2", name: "Employment" }],
              engagementMetrics: {
                totalThreads: 12,
                totalMessages: 78,
                uniqueContributors: 9,
              },
            },
            __typename: "CorpusTypeEdge",
          },
          {
            node: {
              id: thirdCorpus.id,
              slug: "real-estate-contracts",
              title: thirdCorpus.title,
              description: thirdCorpus.description,
              descriptionPreview: thirdCorpus.description,
              icon: null,
              isPublic: false,
              created: "2026-01-10T12:00:00Z",
              creator: {
                id: "USER_3",
                username: "realestate_team",
                slug: "realestate-team",
              },
              documentCount: 89,
              annotationCount: 456,
              categories: [{ id: "cat-3", name: "Real Estate" }],
              engagementMetrics: {
                totalThreads: 5,
                totalMessages: 30,
                uniqueContributors: 4,
              },
            },
            __typename: "CorpusTypeEdge",
          },
        ],
        pageInfo: {
          hasNextPage: false,
          endCursor: null,
        },
        __typename: "CorpusTypeConnection",
      },
      conversations: {
        edges: [
          {
            node: {
              id: "thread-landing-1",
              title: "Best practices for 10-K annotation?",
              description: "Looking for tips on annotating annual reports",
              createdAt: new Date(
                Date.now() - 3 * 60 * 60 * 1000
              ).toISOString(),
              updatedAt: new Date(
                Date.now() - 1 * 60 * 60 * 1000
              ).toISOString(),
              isPinned: false,
              isLocked: false,
              creator: { id: "USER_2", username: "legalops" },
              chatWithCorpus: {
                id: navCorpus.id,
                title: navCorpus.title,
                slug: "sec-filings-collection",
                creator: { slug: "analyst" },
              },
              __typename: "ConversationType",
            },
            __typename: "ConversationTypeEdge",
          },
          {
            node: {
              id: "thread-landing-2",
              title: "Non-compete clause validity across states",
              description: "Discussion about enforceability",
              createdAt: new Date(
                Date.now() - 24 * 60 * 60 * 1000
              ).toISOString(),
              updatedAt: new Date(
                Date.now() - 6 * 60 * 60 * 1000
              ).toISOString(),
              isPinned: true,
              isLocked: false,
              creator: { id: "USER_3", username: "realestate_team" },
              chatWithCorpus: {
                id: secondCorpus.id,
                title: secondCorpus.title,
                slug: "employment-agreements-library",
                creator: { slug: "legalops" },
              },
              __typename: "ConversationType",
            },
            __typename: "ConversationTypeEdge",
          },
        ],
        pageInfo: {
          hasNextPage: false,
          endCursor: null,
          __typename: "PageInfo",
        },
        totalCount: 2,
        __typename: "ConversationTypeConnection",
      },
      communityStats: {
        totalUsers: 1247,
        totalThreads: 389,
        totalMessages: 4521,
        totalAnnotations: 28934,
        activeUsersThisWeek: 87,
        activeUsersThisMonth: 312,
        __typename: "CommunityStatsType",
      },
      globalLeaderboard: [
        {
          id: "USER_1",
          username: "analyst",
          slug: "analyst",
          reputationGlobal: 2450,
          badges: { edges: [], __typename: "UserBadgeTypeConnection" },
          __typename: "UserType",
        },
        {
          id: "USER_2",
          username: "legalops",
          slug: "legalops",
          reputationGlobal: 1890,
          badges: { edges: [], __typename: "UserBadgeTypeConnection" },
          __typename: "UserType",
        },
        {
          id: "USER_3",
          username: "realestate_team",
          slug: "realestate-team",
          reputationGlobal: 1120,
          badges: { edges: [], __typename: "UserBadgeTypeConnection" },
          __typename: "UserType",
        },
      ],
    },
  },
};

const discoveryMocks: MockedResponse[] = [
  discoveryMock,
  { ...discoveryMock }, // duplicate for cache-and-network
];

/* --------------------------------------------------------------------------
 * Step 2: Corpuses list view mocks
 * -------------------------------------------------------------------------- */

const corpusListMocks: MockedResponse[] = [
  // The Corpuses view memoizes its variables from corpusListSort (default
  // "-created"), so the actual query sent on first render is
  // `{ orderBy: "-created" }`. We also keep the bare-variables and
  // textSearch="" variants because legacy callers/refetches may shed the
  // sort variable.
  {
    request: { query: GET_CORPUSES, variables: { orderBy: "-created" } },
    result: {
      data: {
        corpuses: {
          edges: [
            { node: navCorpus, __typename: "CorpusTypeEdge" },
            { node: secondCorpus, __typename: "CorpusTypeEdge" },
            { node: thirdCorpus, __typename: "CorpusTypeEdge" },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "CorpusTypeConnection",
        },
      },
    },
  },
  {
    request: { query: GET_CORPUSES, variables: {} },
    result: {
      data: {
        corpuses: {
          edges: [
            { node: navCorpus, __typename: "CorpusTypeEdge" },
            { node: secondCorpus, __typename: "CorpusTypeEdge" },
            { node: thirdCorpus, __typename: "CorpusTypeEdge" },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "CorpusTypeConnection",
        },
      },
    },
  },
  {
    request: { query: GET_CORPUSES, variables: { textSearch: "" } },
    result: {
      data: {
        corpuses: {
          edges: [
            { node: navCorpus, __typename: "CorpusTypeEdge" },
            { node: secondCorpus, __typename: "CorpusTypeEdge" },
            { node: thirdCorpus, __typename: "CorpusTypeEdge" },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "CorpusTypeConnection",
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUS_STATS,
      variables: { corpusId: navCorpus.id },
    },
    result: {
      data: {
        corpusStats: {
          totalDocs: 24,
          totalAnnotations: 312,
          totalComments: 15,
          totalAnalyses: 3,
          totalExtracts: 2,
          totalThreads: 8,
          totalChats: 4,
          totalRelationships: 18,
          __typename: "CorpusStatsType",
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUS_METADATA,
      variables: { metadataForCorpusId: navCorpus.id },
    },
    result: { data: { corpus: { ...navCorpus, parent: null } } },
  },
  {
    request: {
      query: GET_DOCUMENTS,
      variables: {
        inCorpusWithId: navCorpus.id,
        annotateDocLabels: true,
        includeMetadata: true,
      },
    },
    result: {
      data: {
        documents: {
          edges: [],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "DocumentTypeConnection",
        },
      },
    },
  },
  {
    request: {
      query: GET_DOCUMENTS,
      variables: { annotateDocLabels: false, includeMetadata: false },
    },
    result: {
      data: {
        documents: {
          edges: [],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "DocumentTypeConnection",
        },
      },
    },
  },
];

/* --------------------------------------------------------------------------
 * Step 3: Corpus home view mocks
 * -------------------------------------------------------------------------- */

const corpusHomeMocks: MockedResponse[] = [
  {
    request: {
      query: GET_CORPUS_STATS,
      variables: { corpusId: navCorpus.id },
    },
    result: {
      data: {
        corpusStats: {
          totalDocs: 24,
          totalAnnotations: 312,
          totalComments: 15,
          totalAnalyses: 3,
          totalExtracts: 2,
          totalThreads: 8,
          totalChats: 4,
          totalRelationships: 18,
          __typename: "CorpusStatsType",
        },
      },
    },
  },
  {
    request: {
      query: GET_DOCUMENT_RELATIONSHIPS,
      variables: {
        corpusId: navCorpus.id,
        first: DOCUMENT_RELATIONSHIP_TOC_LIMIT,
      },
    },
    result: {
      data: {
        documentRelationships: {
          edges: [
            {
              node: {
                id: "rel-nav-1",
                relationshipType: "RELATIONSHIP",
                data: null,
                sourceDocument: {
                  id: "doc-10k-2025",
                  title: "Apple Inc. 10-K (2025)",
                  icon: null,
                  slug: "apple-10k-2025",
                  creator: { slug: "analyst" },
                },
                targetDocument: {
                  id: "doc-10k-parent",
                  title: "Annual Reports",
                  icon: null,
                  slug: "annual-reports",
                  creator: { slug: "analyst" },
                },
                annotationLabel: {
                  id: "label-parent",
                  text: "parent",
                  color: "#3b82f6",
                  icon: null,
                },
                corpus: { id: navCorpus.id },
                creator: { id: "USER_1", username: "analyst" },
                created: "2025-11-15T10:00:00Z",
                modified: "2025-11-15T10:00:00Z",
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
  },
  {
    request: {
      query: GET_CORPUS_DOCUMENTS_FOR_TOC,
      variables: {
        corpusId: navCorpus.id,
        first: CORPUS_DOCUMENTS_TOC_LIMIT,
      },
    },
    result: {
      data: {
        documents: {
          edges: [
            {
              node: {
                id: "doc-10k-parent",
                title: "Annual Reports",
                description: "Collection of annual reports",
                slug: "annual-reports",
                icon: null,
                fileType: "application/pdf",
                creator: { slug: "analyst" },
                __typename: "DocumentType",
              },
              __typename: "DocumentTypeEdge",
            },
            {
              node: {
                id: "doc-10k-2025",
                title: "Apple Inc. 10-K (2025)",
                description: "Apple's annual report for fiscal year 2025",
                slug: "apple-10k-2025",
                icon: null,
                fileType: "application/pdf",
                creator: { slug: "analyst" },
                __typename: "DocumentType",
              },
              __typename: "DocumentTypeEdge",
            },
            {
              node: {
                id: "doc-10q-q3",
                title: "Microsoft 10-Q Q3 2025",
                description: "Microsoft quarterly filing",
                slug: "microsoft-10q-q3-2025",
                icon: null,
                fileType: "application/pdf",
                creator: { slug: "analyst" },
                __typename: "DocumentType",
              },
              __typename: "DocumentTypeEdge",
            },
          ],
          totalCount: 3,
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
  },
  {
    request: {
      query: GET_CORPUS_WITH_HISTORY,
      variables: { id: navCorpus.id },
    },
    result: {
      data: {
        corpus: {
          id: navCorpus.id,
          slug: "sec-filings-collection",
          title: navCorpus.title,
          description: navCorpus.description,
          descriptionPreview: navCorpus.description,
          created: navCorpus.created,
          modified: navCorpus.modified,
          isPublic: navCorpus.isPublic,
          myPermissions: navCorpus.myPermissions,
          creator: navCorpus.creator,
          labelSet: navCorpus.labelSet,
          descriptionRevisions: [],
          __typename: "CorpusType",
        },
      },
    },
  },
  {
    request: {
      query: GET_CONVERSATIONS,
      variables: {
        corpusId: navCorpus.id,
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
                id: "thread-corpus-1",
                conversationType: CONVERSATION_TYPE.THREAD,
                title: "How do I interpret Section 4.2 of the 10-K?",
                description: "Question about disclosure requirements",
                createdAt: new Date(
                  Date.now() - 2 * 60 * 60 * 1000
                ).toISOString(),
                updatedAt: new Date(
                  Date.now() - 1 * 60 * 60 * 1000
                ).toISOString(),
                created: new Date(
                  Date.now() - 2 * 60 * 60 * 1000
                ).toISOString(),
                modified: new Date(
                  Date.now() - 1 * 60 * 60 * 1000
                ).toISOString(),
                creator: {
                  id: "USER_2",
                  username: "legalops",
                  email: "legalops@example.com",
                  __typename: "UserType",
                },
                chatWithCorpus: null,
                chatWithDocument: null,
                chatMessages: {
                  totalCount: 7,
                  __typename: "ChatMessageTypeConnection",
                },
                isPublic: true,
                myPermissions: [],
                upvoteCount: 5,
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
                id: "thread-corpus-2",
                conversationType: CONVERSATION_TYPE.THREAD,
                title: "Cross-referencing risk factors across filings",
                description: "Methodology discussion",
                createdAt: new Date(
                  Date.now() - 48 * 60 * 60 * 1000
                ).toISOString(),
                updatedAt: new Date(
                  Date.now() - 24 * 60 * 60 * 1000
                ).toISOString(),
                created: new Date(
                  Date.now() - 48 * 60 * 60 * 1000
                ).toISOString(),
                modified: new Date(
                  Date.now() - 24 * 60 * 60 * 1000
                ).toISOString(),
                creator: {
                  id: "USER_3",
                  username: "realestate_team",
                  email: "re@example.com",
                  __typename: "UserType",
                },
                chatWithCorpus: null,
                chatWithDocument: null,
                chatMessages: {
                  totalCount: 3,
                  __typename: "ChatMessageTypeConnection",
                },
                isPublic: true,
                myPermissions: [],
                upvoteCount: 2,
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
  },
];

// Duplicate mocks for cache-and-network fetch policy
const corpusHomeAllMocks: MockedResponse[] = [
  ...corpusHomeMocks,
  ...corpusHomeMocks.map((m) => ({ ...m })),
];

/* ==========================================================================
 * DESKTOP NAVIGATION SCREENSHOTS (1280x800)
 * ========================================================================== */

test.describe("Corpus Navigation - Desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Step 1: Discover landing page - desktop", async ({ mount, page }) => {
    await mount(
      <DiscoveryLandingTestWrapper mocks={discoveryMocks} authenticated />
    );

    // Wait for featured collections to load
    await expect(page.locator("text=Featured Collections")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=SEC Filings Collection")).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "nav--discover-landing--desktop", {
      fullPage: true,
    });
  });

  test("Step 2: Corpuses list view - desktop", async ({ mount, page }) => {
    await mount(
      <CorpusesTestWrapper
        mocks={corpusListMocks}
        initialEntries={["/corpuses"]}
      />
    );

    // Wait for corpus cards to render
    await expect(page.locator("text=SEC Filings Collection")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "nav--corpuses-list--desktop");
  });

  test("Step 3: Corpus home (landing) view - desktop", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusHomeTestWrapper mocks={corpusHomeAllMocks} corpus={navCorpus} />
    );

    // Wait for landing view to render with discussions
    const landingView = page.getByTestId("corpus-home-landing");
    await expect(landingView).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("corpus-home-landing-title")).toContainText(
      "SEC Filings Collection"
    );

    // Wait for discussions feed
    await expect(
      page.getByTestId("corpus-home-landing-discussions")
    ).toBeVisible({ timeout: 10000 });

    // Wait for InlineChatBar framer-motion animation to complete (opacity 0→1, 300ms)
    const chatBar = page.getByTestId("corpus-home-landing-chat");
    await expect(chatBar).toBeVisible({ timeout: 5000 });
    // Framer-motion uses CSS opacity which Playwright's toBeVisible doesn't check.
    // Wait for the animation to settle (300ms animation + 200ms delay + buffer).
    await expect
      .poll(
        async () => {
          const opacity = await chatBar.evaluate(
            (el) => window.getComputedStyle(el).opacity
          );
          return parseFloat(opacity);
        },
        { timeout: 3000 }
      )
      .toBeGreaterThan(0.9);

    await docScreenshot(page, "nav--corpus-home--desktop", { fullPage: true });
  });

  test("Step 4: Corpus details view - desktop", async ({ mount, page }) => {
    await mount(
      <CorpusHomeTestWrapper
        mocks={corpusHomeAllMocks}
        corpus={navCorpus}
        initialView="details"
      />
    );

    // Wait for details view
    const detailsView = page.getByTestId("corpus-home-details");
    await expect(detailsView).toBeVisible({ timeout: 10000 });

    // Verify two-column layout elements
    await expect(
      page.locator("span").filter({ hasText: /^Documents$/ })
    ).toBeVisible();
    await expect(
      page.locator("span").filter({ hasText: /^About$/ })
    ).toBeVisible();

    // Wait for CorpusAbout framer-motion animation to complete (opacity 0→1, 400ms)
    const aboutCard = page.getByTestId("corpus-home-details-about");
    await expect
      .poll(
        async () => {
          const opacity = await aboutCard.evaluate(
            (el) => window.getComputedStyle(el).opacity
          );
          return parseFloat(opacity);
        },
        { timeout: 3000 }
      )
      .toBeGreaterThan(0.9);

    await docScreenshot(page, "nav--corpus-details--desktop");
  });
});

/* ==========================================================================
 * MOBILE NAVIGATION SCREENSHOTS (375x812 - iPhone-like)
 * ========================================================================== */

test.describe("Corpus Navigation - Mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("Step 1: Discover landing page - mobile", async ({ mount, page }) => {
    await mount(
      <DiscoveryLandingTestWrapper mocks={discoveryMocks} authenticated />
    );

    // Wait for featured collections to load
    await expect(page.locator("text=Featured Collections")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "nav--discover-landing--mobile", {
      fullPage: true,
    });
  });

  test("Step 2: Corpuses list view - mobile", async ({ mount, page }) => {
    await mount(
      <CorpusesTestWrapper
        mocks={corpusListMocks}
        initialEntries={["/corpuses"]}
      />
    );

    // Wait for corpus cards to render
    await expect(page.locator("text=SEC Filings Collection")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "nav--corpuses-list--mobile");
  });

  test("Step 3: Corpus home (landing) view - mobile", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusHomeTestWrapper mocks={corpusHomeAllMocks} corpus={navCorpus} />
    );

    // Wait for landing view
    const landingView = page.getByTestId("corpus-home-landing");
    await expect(landingView).toBeVisible({ timeout: 10000 });

    // Wait for discussions
    await expect(
      page.getByTestId("corpus-home-landing-discussions")
    ).toBeVisible({ timeout: 10000 });

    // Wait for InlineChatBar framer-motion animation to complete
    const chatBar = page.getByTestId("corpus-home-landing-chat");
    await expect(chatBar).toBeVisible({ timeout: 5000 });
    await expect
      .poll(
        async () => {
          const opacity = await chatBar.evaluate(
            (el) => window.getComputedStyle(el).opacity
          );
          return parseFloat(opacity);
        },
        { timeout: 3000 }
      )
      .toBeGreaterThan(0.9);

    await docScreenshot(page, "nav--corpus-home--mobile", { fullPage: true });
  });

  test("Step 4: Corpus details view - mobile", async ({ mount, page }) => {
    await mount(
      <CorpusHomeTestWrapper
        mocks={corpusHomeAllMocks}
        corpus={navCorpus}
        initialView="details"
      />
    );

    // Wait for details view
    const detailsView = page.getByTestId("corpus-home-details");
    await expect(detailsView).toBeVisible({ timeout: 10000 });

    // Wait for CorpusAbout framer-motion animation to complete
    const aboutCard = page.getByTestId("corpus-home-details-about");
    await expect
      .poll(
        async () => {
          const opacity = await aboutCard.evaluate(
            (el) => window.getComputedStyle(el).opacity
          );
          return parseFloat(opacity);
        },
        { timeout: 3000 }
      )
      .toBeGreaterThan(0.9);

    await docScreenshot(page, "nav--corpus-details--mobile");
  });
});
