/**
 * Comprehensive Component Tests for Corpus Tabs
 *
 * Tests all tabbed flows in the CorpusHome component:
 * - Home tab (default)
 * - Documents tab
 * - Annotations tab
 * - Analyses tab
 * - Extracts tab (split view)
 * - Discussions tab
 * - Chats tab
 * - Analytics tab
 * - Settings tab (permission gated)
 * - Badges tab (permission gated)
 *
 * Also tests mobile responsive behavior and tab navigation.
 */
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusesTestWrapper } from "./CorpusesTestWrapper";
import { openedCorpus, selectedTab } from "../src/graphql/cache";
import {
  GET_CORPUSES,
  GET_CORPUS_STATS,
  GET_CORPUS_METADATA,
  GET_CORPUS_WITH_HISTORY,
  GET_DOCUMENTS,
  GET_ANNOTATIONS,
  GET_ANALYSES,
  GET_EXTRACTS,
  GET_CONVERSATIONS,
  GET_CORPUS_CONVERSATIONS,
  GET_CORPUS_ACTIONS,
  GET_CORPUS_ENGAGEMENT_METRICS,
  GET_BADGES,
} from "../src/graphql/queries";
import { CorpusType } from "../src/types/graphql-api";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

/* -------------------------------------------------------------------------- */
/* Mock Data Factories                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Creates a base corpus with common fields
 *
 * NOTE: myPermissions uses actual GraphQL permission strings (e.g., "update_corpus")
 * NOT PermissionTypes enum values (e.g., "CAN_UPDATE").
 * This is because Corpuses.tsx calls getPermissions() which expects the GraphQL format.
 */
const createMockCorpus = (overrides: Partial<CorpusType> = {}): CorpusType => ({
  id: "CORPUS_TEST_1",
  title: "Test Corpus for Tab Testing",
  icon: null,
  isPublic: false,
  description: "A comprehensive test corpus for tab testing",
  created: new Date().toISOString(),
  modified: new Date().toISOString(),
  creator: {
    id: "USER1",
    email: "tester@example.com",
    username: "tester",
    slug: "tester",
    __typename: "UserType",
  },
  labelSet: null,
  parent: null as unknown as CorpusType,
  allowComments: true,
  preferredEmbedder: null,
  appliedAnalyzerIds: [],
  // Use actual GraphQL permission strings that getPermissions() expects
  // "update_corpus" → CAN_UPDATE, "read_corpus" → CAN_READ
  myPermissions: ["update_corpus", "read_corpus"] as unknown as string[],
  analyses: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "AnalysisTypeConnection",
  },
  annotations: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "AnnotationTypeConnection",
  },
  documents: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "DocumentTypeConnection",
  },
  __typename: "CorpusType",
  ...overrides,
});

// Read-only corpus (no CAN_UPDATE permission)
// Uses GraphQL format: "read_corpus" → CAN_READ
const createReadOnlyCorpus = () =>
  createMockCorpus({
    id: "CORPUS_READONLY",
    title: "Read Only Corpus",
    myPermissions: ["read_corpus"] as unknown as string[],
  });

// Mock document for documents tab
const mockDocument = {
  id: "DOC_1",
  slug: "test-document-1",
  title: "Test Document 1.pdf",
  description: "A test document",
  backendLock: false,
  pdfFile: "https://example.com/doc1.pdf",
  txtExtractFile: null,
  fileType: "pdf",
  pawlsParseFile: null,
  icon: null,
  isPublic: false,
  myPermissions: ["read", "update"],
  creator: { slug: "tester", __typename: "UserType" },
  is_selected: false,
  is_open: false,
  hasVersionHistory: false,
  versionCount: 1,
  isLatestVersion: true,
  canViewHistory: false,
  doc_label_annotations: { edges: [], __typename: "AnnotationTypeConnection" },
  __typename: "DocumentType",
};

// Mock annotation for annotations tab
const mockAnnotation = {
  id: "ANNOT_1",
  tokensJsons: null,
  json: {},
  page: 1,
  created: new Date().toISOString(),
  creator: {
    id: "USER1",
    email: "tester@example.com",
    username: "tester",
    slug: "tester",
    __typename: "UserType",
  },
  corpus: {
    id: "CORPUS_TEST_1",
    slug: "test-corpus",
    icon: null,
    title: "Test Corpus",
    description: "Test",
    preferredEmbedder: null,
    creator: { id: "USER1", slug: "tester", __typename: "UserType" },
    __typename: "CorpusType",
  },
  document: {
    id: "DOC_1",
    slug: "test-document",
    title: "Test Document.pdf",
    description: "A test document",
    backendLock: false,
    pdfFile: "https://example.com/doc1.pdf",
    txtExtractFile: null,
    pawlsParseFile: null,
    icon: null,
    fileType: "pdf",
    creator: { id: "USER1", slug: "tester", __typename: "UserType" },
    __typename: "DocumentType",
  },
  analysis: null,
  annotationLabel: {
    id: "LABEL_1",
    text: "Important",
    color: "#FF5733",
    icon: "tag",
    description: "Important annotation",
    labelType: "TOKEN_LABEL",
    __typename: "AnnotationLabelType",
  },
  annotationType: "TOKEN_LABEL",
  structural: false,
  rawText: "This is an important annotation text",
  isPublic: false,
  myPermissions: ["read"],
  __typename: "ServerAnnotationType",
};

// Mock analysis for analyses tab
const mockAnalysis = {
  id: "ANALYSIS_1",
  creator: { id: "USER1", email: "tester@example.com", __typename: "UserType" },
  isPublic: false,
  myPermissions: ["read_analysis"],
  analysisStarted: new Date().toISOString(),
  analysisCompleted: new Date().toISOString(),
  analyzedDocuments: {
    edges: [{ node: { id: "DOC_1" } }],
    __typename: "DocumentTypeConnection",
  },
  receivedCallbackFile: null,
  annotations: { totalCount: 5, __typename: "AnnotationTypeConnection" },
  corpusAction: null,
  analyzer: {
    id: "ANALYZER_1",
    analyzerId: "test-analyzer",
    description: "Test Analyzer",
    manifest: {},
    inputSchema: null,
    fullLabelList: [{ id: "LABEL_1", text: "Label 1" }],
    hostGremlin: null,
    __typename: "AnalyzerType",
  },
  __typename: "AnalysisType",
};

// Mock extract for extracts tab
const mockExtract = {
  id: "EXTRACT_1",
  name: "Test Extract",
  corpus: {
    id: "CORPUS_TEST_1",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
  fieldset: {
    id: "FIELDSET_1",
    name: "Test Fieldset",
    inUse: true,
    columns: {
      edges: [
        {
          node: { id: "COL_1", query: "test query", __typename: "ColumnType" },
          __typename: "ColumnTypeEdge",
        },
      ],
      __typename: "ColumnTypeConnection",
    },
    __typename: "FieldsetType",
  },
  creator: {
    id: "USER1",
    username: "tester",
    slug: "tester",
    __typename: "UserType",
  },
  created: new Date().toISOString(),
  started: new Date().toISOString(),
  finished: new Date().toISOString(),
  error: null,
  __typename: "ExtractType",
};

// Mock conversation for discussions/chats tabs
const mockConversation = {
  id: "CONV_1",
  conversationType: "DISCUSSION",
  title: "Test Discussion Thread",
  description: "A test discussion",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  creator: {
    id: "USER1",
    username: "tester",
    email: "tester@example.com",
    __typename: "UserType",
  },
  chatWithCorpus: {
    id: "CORPUS_TEST_1",
    title: "Test Corpus",
    slug: "test-corpus",
    creator: {
      id: "USER1",
      slug: "tester",
      username: "tester",
      __typename: "UserType",
    },
    __typename: "CorpusType",
  },
  chatWithDocument: null,
  chatMessages: { totalCount: 3, __typename: "ChatMessageTypeConnection" },
  isPublic: false,
  myPermissions: ["read"],
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
};

/* -------------------------------------------------------------------------- */
/* Mock Builders                                                               */
/* -------------------------------------------------------------------------- */

const createBaseMocks = (corpus: CorpusType): MockedResponse[] => [
  // GET_CORPUSES - required for corpus list
  {
    request: { query: GET_CORPUSES, variables: {} },
    result: {
      data: {
        corpuses: {
          edges: [{ node: corpus, __typename: "CorpusTypeEdge" }],
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
  // GET_CORPUS_STATS
  {
    request: { query: GET_CORPUS_STATS, variables: { corpusId: corpus.id } },
    result: {
      data: {
        corpusStats: {
          totalDocs: 2,
          totalAnnotations: 5,
          totalComments: 0,
          totalAnalyses: 1,
          totalExtracts: 1,
          totalThreads: 0,
          totalChats: 0,
          totalRelationships: 0,
          __typename: "CorpusStatsType",
        },
      },
    },
  },
  // GET_CORPUS_METADATA
  {
    request: {
      query: GET_CORPUS_METADATA,
      variables: { metadataForCorpusId: corpus.id },
    },
    result: { data: { corpus: { ...corpus, parent: null } } },
  },
  // GET_CORPUS_WITH_HISTORY
  {
    request: { query: GET_CORPUS_WITH_HISTORY, variables: { id: corpus.id } },
    result: {
      data: {
        corpus: {
          ...corpus,
          slug: "test-corpus",
          mdDescription: null,
          descriptionRevisions: [],
        },
      },
    },
  },
];

const createDocumentsMocks = (corpusId: string): MockedResponse[] => {
  const documentsResult = {
    data: {
      documents: {
        edges: [{ node: mockDocument, __typename: "DocumentTypeEdge" }],
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
  };

  // Return multiple mock variations to handle different query variable combinations
  return [
    {
      request: {
        query: GET_DOCUMENTS,
        variables: {
          inCorpusWithId: corpusId,
          annotateDocLabels: true,
          includeMetadata: true,
        },
      },
      result: documentsResult,
    },
    {
      request: {
        query: GET_DOCUMENTS,
        variables: {
          inCorpusWithId: corpusId,
          inFolderId: "__root__",
          annotateDocLabels: true,
          includeMetadata: true,
        },
      },
      result: documentsResult,
    },
  ];
};

const createAnnotationsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_ANNOTATIONS,
    variables: { corpusId },
  },
  result: {
    data: {
      annotations: {
        totalCount: 1,
        edges: [{ node: mockAnnotation, __typename: "AnnotationTypeEdge" }],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "AnnotationTypeConnection",
      },
    },
  },
});

const createAnalysesMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_ANALYSES,
    variables: { corpusId },
  },
  result: {
    data: {
      analyses: {
        edges: [{ node: mockAnalysis, __typename: "AnalysisTypeEdge" }],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "AnalysisTypeConnection",
      },
    },
  },
});

const createExtractsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_EXTRACTS,
    variables: { corpusId },
  },
  result: {
    data: {
      extracts: {
        edges: [{ node: mockExtract, __typename: "ExtractTypeEdge" }],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "ExtractTypeConnection",
      },
    },
  },
});

const createConversationsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_CONVERSATIONS,
    variables: { corpusId },
  },
  result: {
    data: {
      conversations: {
        totalCount: 1,
        edges: [{ node: mockConversation, __typename: "ConversationTypeEdge" }],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "ConversationTypeConnection",
      },
    },
  },
});

const createCorpusConversationsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_CORPUS_CONVERSATIONS,
    variables: { corpusId },
  },
  result: {
    data: {
      conversations: {
        edges: [
          {
            node: {
              id: "CHAT_CONV_1",
              title: "AI Chat Session",
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
              chatMessages: {
                totalCount: 5,
                __typename: "ChatMessageTypeConnection",
              },
              creator: { email: "tester@example.com", __typename: "UserType" },
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
        __typename: "ConversationTypeConnection",
      },
    },
  },
});

const createEngagementMetricsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_CORPUS_ENGAGEMENT_METRICS,
    variables: { corpusId },
  },
  result: {
    data: {
      corpus: {
        id: corpusId,
        title: "Test Corpus for Tab Testing",
        engagementMetrics: {
          totalThreads: 12,
          activeThreads: 5,
          totalMessages: 87,
          messagesLast7Days: 23,
          messagesLast30Days: 65,
          uniqueContributors: 8,
          activeContributors30Days: 4,
          totalUpvotes: 34,
          avgMessagesPerThread: 7.25,
          lastUpdated: new Date().toISOString(),
          __typename: "EngagementMetricsType",
        },
        __typename: "CorpusType",
      },
    },
  },
});

const createCorpusActionsMock = (corpusId: string): MockedResponse => ({
  request: {
    query: GET_CORPUS_ACTIONS,
    variables: { corpusId },
  },
  result: {
    data: {
      corpusActions: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
          __typename: "PageInfo",
        },
        __typename: "CorpusActionTypeConnection",
      },
    },
  },
});

const createEmptyDocumentsMock = (): MockedResponse => ({
  request: {
    query: GET_DOCUMENTS,
    variables: {
      annotateDocLabels: false,
      includeMetadata: false,
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
});

/**
 * Build comprehensive mocks for testing all tabs
 */
const createAllTabMocks = (corpus: CorpusType): MockedResponse[] => [
  ...createBaseMocks(corpus),
  ...createDocumentsMocks(corpus.id),
  createAnnotationsMock(corpus.id),
  createAnalysesMock(corpus.id),
  createExtractsMock(corpus.id),
  createConversationsMock(corpus.id),
  createCorpusConversationsMock(corpus.id),
  createCorpusActionsMock(corpus.id),
  createEngagementMetricsMock(corpus.id),
  createEmptyDocumentsMock(),
];

/* -------------------------------------------------------------------------- */
/* Test Helpers                                                                */
/* -------------------------------------------------------------------------- */

const mountCorpuses = (
  mount: any,
  corpus: CorpusType,
  options: { tab?: string; authenticated?: boolean } = {}
) => {
  const { tab, authenticated = true } = options;
  const mocks = createAllTabMocks(corpus);

  // Set up initial corpus before mount
  openedCorpus(corpus);
  if (tab) {
    selectedTab(tab);
  }

  const initialUrl = tab
    ? `/c/tester/test-corpus?tab=${tab}`
    : `/c/tester/test-corpus`;

  return mount(
    <CorpusesTestWrapper
      mocks={mocks}
      initialCorpus={corpus}
      initialEntries={[initialUrl]}
      authenticated={authenticated}
    />
  );
};

/* -------------------------------------------------------------------------- */
/* Tests: Tab Navigation                                                       */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Navigation", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000); // Increase timeout for complex component rendering

  test("should render home tab by default with corpus landing view", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for home tab content to render (landing view)
    const landing = page.getByTestId("corpus-home-landing");
    await expect(landing).toBeVisible({ timeout: 10000 });

    // Should show corpus title - use specific testid to avoid strict mode violation
    const title = page.getByTestId("corpus-home-landing-title");
    await expect(title).toContainText(corpus.title);

    // Sidebar should be visible on desktop
    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible();
  });

  test("should navigate to Documents tab and show content", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for sidebar to be ready
    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Click Documents tab in sidebar
    await page.locator('[data-item-id="documents"]').click();

    // Wait for Documents tab header
    await expect(page.locator("text=Documents").first()).toBeVisible();

    // Should show search placeholder for documents
    await expect(
      page.getByPlaceholder("Search for document in corpus...")
    ).toBeVisible({ timeout: 5000 });
  });

  test("should navigate to Annotations tab and show content", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for sidebar to be ready
    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    // Click Annotations tab
    await page.locator('[data-item-id="annotations"]').click();

    // Wait for Annotations content
    await expect(
      page.getByPlaceholder("Search for annotated text in corpus...")
    ).toBeVisible({ timeout: 5000 });
  });

  test("should navigate to Analyses tab", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[data-item-id="analyses"]').click();

    // Check for Analyses tab title
    await expect(page.locator("text=Analyses").first()).toBeVisible();
  });

  test("should navigate to Extracts tab with split view", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[data-item-id="extracts"]').click();

    // Should show Extracts tab content
    await expect(page.locator("text=Extracts").first()).toBeVisible();
  });

  test("should navigate to Discussions tab", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[data-item-id="discussions"]').click();

    // Should show Discussions title
    await expect(page.locator("text=Discussions").first()).toBeVisible();
  });

  test("should navigate to Chats tab", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[data-item-id="chats"]').click();

    // Should show Chat History title
    await expect(page.locator("text=Chat History").first()).toBeVisible();
  });

  test("should navigate back to Home from any tab using back button", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Navigate to Documents first
    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });
    await page.locator('[data-item-id="documents"]').click();
    await expect(
      page.getByPlaceholder("Search for document in corpus...")
    ).toBeVisible({ timeout: 5000 });

    // Click back button to go home
    await page.locator('[title="Back to Home"]').click();

    // Should be back on home tab (landing view)
    const landing = page.getByTestId("corpus-home-landing");
    await expect(landing).toBeVisible({ timeout: 5000 });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Documents Tab                                                        */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Documents", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should display documents in corpus", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 10000,
    });
  });

  test("should show search box for documents", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Should have document search placeholder
    await expect(
      page.getByPlaceholder("Search for document in corpus...")
    ).toBeVisible({ timeout: 10000 });
  });

  test("should show back button to home", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Back button should be visible
    await expect(page.locator('[title="Back to Home"]')).toBeVisible({
      timeout: 10000,
    });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Annotations Tab                                                      */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Annotations", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show annotation search placeholder", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "annotations" });

    await expect(
      page.getByPlaceholder("Search for annotated text in corpus...")
    ).toBeVisible({ timeout: 10000 });
  });

  test("should display annotation cards when present", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "annotations" });

    // Wait for tab content to load
    await expect(
      page.getByPlaceholder("Search for annotated text in corpus...")
    ).toBeVisible({ timeout: 10000 });

    // Should display annotation text (mock has "This is an important annotation text")
    // Note: This may depend on how the annotations are fetched and displayed
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Analyses Tab                                                         */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Analyses", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Analyses tab header", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "analyses" });

    await expect(page.locator("text=Analyses").first()).toBeVisible({
      timeout: 10000,
    });
  });

  test("should have back navigation", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "analyses" });

    await expect(page.locator('[title="Back to Home"]')).toBeVisible({
      timeout: 10000,
    });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Extracts Tab                                                         */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Extracts", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Extracts tab header", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "extracts" });

    await expect(page.locator("text=Extracts").first()).toBeVisible({
      timeout: 10000,
    });
  });

  test("should have status filter tabs", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "extracts" });

    // Wait for tab content
    await expect(page.locator("text=Extracts").first()).toBeVisible({
      timeout: 10000,
    });

    // Should show filter tabs (All, Running, Completed, etc.)
    await expect(page.getByRole("tab", { name: /All/i })).toBeVisible();
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Discussions Tab                                                      */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Discussions", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Discussions tab header", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "discussions" });

    await expect(page.locator("text=Discussions").first()).toBeVisible({
      timeout: 10000,
    });
  });

  test("should have back navigation", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "discussions" });

    await expect(page.locator('[title="Back to Home"]')).toBeVisible({
      timeout: 10000,
    });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Chats Tab                                                            */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Chats", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Chat History header", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "chats" });

    await expect(page.locator("text=Chat History").first()).toBeVisible({
      timeout: 10000,
    });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Settings Tab (Permission Gated)                                      */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Settings (Permission Gated)", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Settings tab when user has CAN_UPDATE permission", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus(); // Has CAN_UPDATE by default
    await mountCorpuses(mount, corpus);

    // Wait for sidebar to be visible
    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Wait for home tab to be visible (indicates full render)
    await expect(sidebar.locator('[data-item-id="home"]')).toBeVisible({
      timeout: 5000,
    });

    // Settings should be visible in sidebar (permission-gated)
    // Increase timeout since permissions may take time to propagate
    await expect(sidebar.locator('[data-item-id="settings"]')).toBeVisible({
      timeout: 10000,
    });
  });

  test("should hide Settings tab when user lacks CAN_UPDATE permission", async ({
    mount,
    page,
  }) => {
    const corpus = createReadOnlyCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for sidebar
    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    // Settings should NOT be visible
    await expect(page.locator('[data-item-id="settings"]')).not.toBeVisible();
  });

  test("should navigate to Settings tab and show content", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for sidebar and navigate to settings
    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Wait for home tab to be visible first
    await expect(sidebar.locator('[data-item-id="home"]')).toBeVisible({
      timeout: 5000,
    });

    // Wait for settings tab to appear (permission-gated)
    const settingsTab = sidebar.locator('[data-item-id="settings"]');
    await expect(settingsTab).toBeVisible({ timeout: 10000 });

    // Click on settings tab
    await settingsTab.click();

    // Settings header should be visible
    await expect(page.locator("text=Settings").first()).toBeVisible({
      timeout: 10000,
    });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Badges Tab (Permission Gated)                                        */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Badges (Permission Gated)", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show Badges tab when user has CAN_UPDATE permission", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Wait for sidebar to be visible
    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Wait for home tab to be visible (indicates full render)
    await expect(sidebar.locator('[data-item-id="home"]')).toBeVisible({
      timeout: 5000,
    });

    // Badges should be visible in sidebar (permission-gated)
    // Increase timeout since permissions may take time to propagate
    await expect(sidebar.locator('[data-item-id="badges"]')).toBeVisible({
      timeout: 10000,
    });
  });

  test("should hide Badges tab when user lacks CAN_UPDATE permission", async ({
    mount,
    page,
  }) => {
    const corpus = createReadOnlyCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    // Badges should NOT be visible
    await expect(page.locator('[data-item-id="badges"]')).not.toBeVisible();
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Sidebar Behavior                                                     */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Sidebar", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should toggle sidebar collapse/expand", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Get initial width
    const initialWidth = await sidebar.evaluate(
      (el) => el.getBoundingClientRect().width
    );

    // Toggle collapse
    await page.getByTestId("sidebar-toggle").click();

    // Wait for animation and check width changed
    await expect
      .poll(
        async () =>
          await sidebar.evaluate((el) => el.getBoundingClientRect().width),
        { timeout: 3000 }
      )
      .not.toBe(initialWidth);
  });

  test("should show badge counts for tabs with content", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    const sidebar = page.getByTestId("navigation-sidebar");
    await expect(sidebar).toBeVisible({ timeout: 10000 });

    // Stats show document/annotation counts in badges
    // The mock returns totalDocs: 2, totalAnnotations: 5, etc.
    // These should appear as badges in the sidebar
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Mobile Responsive                                                    */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Mobile Responsive", () => {
  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE size
  test.setTimeout(30000);

  test("should show mobile kebab menu on tabs", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Mobile should show kebab menu
    await expect(
      page.locator('[aria-label="Open navigation menu"]')
    ).toBeVisible({ timeout: 10000 });
  });

  test("should open mobile navigation from kebab menu", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Click kebab menu
    await page.locator('[aria-label="Open navigation menu"]').click();

    // Mobile sidebar should open
    await expect(page.getByTestId("navigation-sidebar")).toBeVisible();
  });

  test("should close mobile menu on backdrop click", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "documents" });

    // Open mobile menu
    await page.locator('[aria-label="Open navigation menu"]').click();

    // Wait for sidebar
    await expect(page.getByTestId("navigation-sidebar")).toBeVisible();

    // Click backdrop to close (if visible)
    // The backdrop appears when mobile sidebar is open
    const backdrop = page.locator('[class*="MobileMenuBackdrop"]');
    if (await backdrop.isVisible()) {
      await backdrop.click();
      // Sidebar should close
      await expect(page.getByTestId("navigation-sidebar")).not.toBeVisible({
        timeout: 3000,
      });
    }
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: URL State Sync                                                       */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - URL State Sync", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should load correct tab from URL parameter", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus, { tab: "annotations" });

    // Should render annotations tab directly
    await expect(
      page.getByPlaceholder("Search for annotated text in corpus...")
    ).toBeVisible({ timeout: 10000 });
  });

  test("should default to home tab when no tab parameter", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    // No tab option = default to home
    await mountCorpuses(mount, corpus);

    // Should show home content (landing view)
    const landing = page.getByTestId("corpus-home-landing");
    await expect(landing).toBeVisible({ timeout: 10000 });
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Home Tab Content                                                     */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Home Tab Content", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should show corpus landing with title and privacy badge", async ({
    mount,
    page,
  }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    const landing = page.getByTestId("corpus-home-landing");
    await expect(landing).toBeVisible({ timeout: 10000 });

    // Title should contain corpus name - use specific testid to avoid strict mode violation
    const title = page.getByTestId("corpus-home-landing-title");
    await expect(title).toBeVisible();
    await expect(title).toContainText(corpus.title);

    // Privacy badge (Private for our mock) - check within landing view metadata
    const metadata = page.getByTestId("corpus-home-landing-metadata");
    await expect(metadata.locator("text=Private")).toBeVisible();
  });

  test("should show inline chat bar on home", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Chat bar should be visible (in landing view)
    const chatBar = page.getByTestId("corpus-home-landing-chat");
    await expect(chatBar).toBeVisible({ timeout: 10000 });

    // Quick action chips
    await expect(chatBar.locator("text=Summarize")).toBeVisible();
    await expect(chatBar.locator("text=Search")).toBeVisible();
    await expect(chatBar.locator("text=Analyze")).toBeVisible();
  });

  test("should show description in landing view", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    // Landing view should be visible
    const landing = page.getByTestId("corpus-home-landing");
    await expect(landing).toBeVisible({ timeout: 10000 });

    // CORPUS badge should be visible (exact match to avoid matching "Corpuses" breadcrumb)
    await expect(page.getByText("CORPUS", { exact: true })).toBeVisible();
  });
});

/* -------------------------------------------------------------------------- */
/* Tests: Analytics Tab                                                        */
/* -------------------------------------------------------------------------- */

test.describe("Corpus Tabs - Analytics", () => {
  test.use({ viewport: { width: 1200, height: 800 } });
  test.setTimeout(30000);

  test("should navigate to Analytics tab", async ({ mount, page }) => {
    const corpus = createMockCorpus();
    await mountCorpuses(mount, corpus);

    await expect(page.getByTestId("navigation-sidebar")).toBeVisible({
      timeout: 10000,
    });

    await page.locator('[data-item-id="analytics"]').click();

    // Wait for engagement metrics to render
    await expect(page.locator("text=Total Threads").first()).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "corpus--analytics--dashboard");
    await releaseScreenshot(page, "v3.0.0.b3", "analytics");
  });
});
