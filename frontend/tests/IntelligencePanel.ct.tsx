/**
 * Component tests for IntelligencePanel — the corpus-home "collection overview",
 * rebuilt as an editorial metric band (documents / pages / law references) plus
 * a magazine-style **documents index** (numbered entries with one-line
 * descriptions and page-weight bars). The earlier stats/label-distribution panel
 * is gone, so these tests exercise the new shape.
 *
 * It issues the collection-docs query and the governance-graph query (the
 * references metric), and mounts the IntelligenceSetupBanner (setup-status
 * query), so it mounts under a MockedProvider supplying all three — and a
 * Router, since each index entry navigates to its document on click.
 *
 * NOTE: each JSX-component import is kept in its own statement (MockedProvider,
 * MemoryRouter, IntelligencePanel) per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { IntelligencePanel } from "../src/components/corpuses/CorpusHome/intelligence/IntelligencePanel";
import { docScreenshot } from "./utils/docScreenshot";
// Import the real query documents the component runs, so the mocks below stay
// in lock-step with any future field additions (no hand-copied gql to drift).
import {
  GET_CORPUS_COLLECTION_DOCS,
  GET_GOVERNANCE_GRAPH,
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
} from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

interface DocSeed {
  id: string;
  title: string;
  description?: string;
  pageCount?: number;
}

// The panel asks for up to 100 documents (corpusId + limit: 100). MockedProvider
// matches variables exactly, so the limit must be present.
const docsMock = (
  docs: DocSeed[],
  totalCount: number = docs.length,
  delay?: number
) => ({
  request: {
    query: GET_CORPUS_COLLECTION_DOCS,
    variables: { corpusId: CORPUS_ID, limit: 100 },
  },
  ...(delay ? { delay } : {}),
  result: {
    data: {
      documents: {
        totalCount,
        edges: docs.map((d) => ({
          node: {
            id: d.id,
            slug: d.id.toLowerCase(),
            title: d.title,
            description: d.description ?? "",
            pageCount: d.pageCount ?? 0,
            fileType: "application/pdf",
          },
        })),
      },
    },
  },
});

const docsErrorMock = {
  request: {
    query: GET_CORPUS_COLLECTION_DOCS,
    variables: { corpusId: CORPUS_ID, limit: 100 },
  },
  error: new Error("collection boom"),
};

// The references metric reads governanceGraph.mentionCount only; the rest of the
// payload is irrelevant here. mentionCount === 0 suppresses the metric entirely.
const governanceMock = (mentionCount: number) => ({
  request: { query: GET_GOVERNANCE_GRAPH, variables: { corpusId: CORPUS_ID } },
  result: {
    data: {
      governanceGraph: {
        corpora: [],
        nodes: [],
        edges: [],
        documentCount: 0,
        externalKeyCount: 0,
        edgeCount: 0,
        mentionCount,
        truncated: false,
      },
    },
  },
});

// The mounted setup banner queries status; a fully-set-up corpus keeps it
// silent (banner returns null) so these tests focus on the panel body.
const setupStatusSilentMock = {
  request: {
    query: GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusIntelligenceSetupStatus: {
        referenceAvailable: true,
        referenceActionInstalled: true,
        installedTemplateNames: [],
        missingTemplateNames: [],
        isFullySetUp: true,
        canSetup: false,
      },
    },
  },
};

const PANEL = '[data-testid="corpus-intelligence-panel"]';
const METRICS = '[data-testid="corpus-intelligence-panel-metrics"]';
const INDEX = '[data-testid="corpus-intelligence-panel-index"]';
const ENTRY = '[data-testid="corpus-intelligence-panel-entry"]';

test.describe("IntelligencePanel", () => {
  test("renders the metric band and the documents index", async ({
    mount,
    page,
  }) => {
    const docs: DocSeed[] = [
      {
        id: "Doc1",
        title: "Master Services Agreement",
        description: "A services agreement between Acme and Globex.",
        pageCount: 12,
      },
      { id: "Doc2", title: "Statement of Work", pageCount: 4 },
      { id: "Doc3", title: "Order Form", pageCount: 2 },
    ];

    const component = await mount(
      // MemoryRouter: each index entry navigates via useNavigateToDocumentById
      // (useNavigate), which requires a Router context.
      <MemoryRouter>
        <MockedProvider
          mocks={[docsMock(docs), governanceMock(5), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.locator(PANEL)).toBeVisible({ timeout: 10000 });

    // Metric band: documents, the summed page count (12 + 4 + 2 = 18), and the
    // law-references metric (mentionCount === 5 > 0).
    const metrics = page.locator(METRICS);
    await expect(metrics).toContainText("Documents", { timeout: 10000 });
    await expect(metrics).toContainText("Pages");
    await expect(metrics).toContainText("18");
    await expect(metrics).toContainText("Law references");

    // Documents index: one numbered entry per document, with the first doc's
    // one-line description surfaced inline.
    await expect(page.locator(INDEX)).toBeVisible();
    await expect(page.locator(ENTRY)).toHaveCount(3);
    await expect(page.locator(PANEL)).toContainText(
      "Master Services Agreement"
    );
    await expect(page.locator(PANEL)).toContainText(
      "A services agreement between Acme and Globex."
    );

    await docScreenshot(page, "corpus--intelligence-panel--with-data");

    await component.unmount();
  });

  test("omits the law-references metric when the collection cites no authorities", async ({
    mount,
    page,
  }) => {
    const docs: DocSeed[] = [
      { id: "Doc1", title: "Alpha", pageCount: 3 },
      { id: "Doc2", title: "Beta", pageCount: 1 },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[docsMock(docs), governanceMock(0), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const metrics = page.locator(METRICS);
    await expect(metrics).toContainText("Documents", { timeout: 10000 });
    // With no law references, the metric self-hides — neither singular nor
    // plural label appears.
    await expect(metrics).not.toContainText("Law reference");

    await component.unmount();
  });

  test("collapses a large index and expands it on demand", async ({
    mount,
    page,
  }) => {
    // Eight documents — above the six-entry preview cap, so the index previews
    // the first six and reveals the rest behind "Show all".
    const docs: DocSeed[] = Array.from({ length: 8 }, (_, i) => ({
      id: `Doc${i + 1}`,
      title: `Document ${i + 1}`,
      pageCount: i + 1,
    }));

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[docsMock(docs, 8), governanceMock(0), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.locator(INDEX)).toBeVisible({ timeout: 10000 });
    // Only the first six entries render before expansion.
    await expect(page.locator(ENTRY)).toHaveCount(6);

    const showMore = page.locator(
      '[data-testid="corpus-intelligence-panel-show-more"]'
    );
    await expect(showMore).toBeVisible();
    await expect(showMore).toContainText("Show all 8 documents");

    await showMore.click();
    await expect(page.locator(ENTRY)).toHaveCount(8);

    await component.unmount();
  });

  test("shows skeleton rows while the collection loads", async ({
    mount,
    page,
  }) => {
    // Delay the collection query so the first-load skeleton state is observable
    // before the documents arrive.
    const docs: DocSeed[] = [
      { id: "Doc1", title: "Alpha", pageCount: 3 },
      { id: "Doc2", title: "Beta", pageCount: 1 },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            docsMock(docs, docs.length, 600),
            governanceMock(0),
            setupStatusSilentMock,
          ]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Before the query resolves the index shows shimmer skeletons rather than a
    // misleading empty state.
    await expect(
      page.locator('[data-testid^="corpus-intelligence-panel-skeleton-"]')
    ).toHaveCount(4);

    // Once the documents resolve the real index replaces the skeletons.
    await expect(page.locator(ENTRY)).toHaveCount(2, { timeout: 10000 });

    await component.unmount();
  });

  test("surfaces an error hint instead of a misleading empty state on fetch failure", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[docsErrorMock, governanceMock(0), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // A failed fetch must not masquerade as an empty collection.
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel-error"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("renders an empty hint when the collection has no documents", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[docsMock([], 0), governanceMock(0), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.locator(PANEL)).toContainText(
      "No documents in this collection yet.",
      { timeout: 10000 }
    );

    await component.unmount();
  });
});
