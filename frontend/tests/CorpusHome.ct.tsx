import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusType } from "../src/types/graphql-api";
import { CorpusHomeTestWrapper } from "./CorpusHomeTestWrapper";
import {
  GET_CORPUS_STATS,
  GET_CORPUS_WITH_HISTORY,
  GET_DOCUMENT_RELATIONSHIPS,
  GET_CORPUS_DOCUMENTS_FOR_TOC,
} from "../src/graphql/queries";
import {
  DOCUMENT_RELATIONSHIP_TOC_LIMIT,
  CORPUS_DOCUMENTS_TOC_LIMIT,
} from "../src/assets/configurations/constants";
import { PermissionTypes } from "../src/components/types";
import { docScreenshot } from "./utils/docScreenshot";

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
        mdDescription: null,
        created: dummyCorpus.created,
        modified: dummyCorpus.modified,
        isPublic: dummyCorpus.isPublic,
        myPermissions: dummyCorpus.myPermissions,
        creator: dummyCorpus.creator,
        labelSet: dummyCorpus.labelSet,
        descriptionRevisions: [],
        __typename: "CorpusType",
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

test("renders View Details button in landing view", async ({ mount, page }) => {
  await mountCorpusHome(mount);

  // View Details button should be visible
  const viewDetailsBtn = page.getByTestId(
    "corpus-home-landing-view-details-btn"
  );
  await expect(viewDetailsBtn).toBeVisible();
  await expect(viewDetailsBtn).toContainText("View Details");
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
