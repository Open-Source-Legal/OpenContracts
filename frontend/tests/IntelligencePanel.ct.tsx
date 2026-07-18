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
import { CorpusType } from "../src/types/graphql-api";
import { IntelligencePanelCorpusContextTestWrapper } from "./IntelligencePanelCorpusContextTestWrapper";
// Import the real query documents the component runs, so the mocks below stay
// in lock-step with any future field additions (no hand-copied gql to drift).
import {
  GET_CORPUS_COLLECTION_DOCS,
  GET_GOVERNANCE_GRAPH,
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
} from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

interface DocSeed {
  id: string;
  title: string | null;
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

const corpusNavigationContext = {
  id: CORPUS_ID,
  slug: "cross-doc100",
  creator: { id: "UserType:owner", slug: "corpus-owner" },
} as unknown as CorpusType;

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

  test("uses singular labels, an untitled fallback, and navigates an entry by keyboard", async ({
    mount,
    page,
  }) => {
    // A single, untitled, one-page document with exactly one law reference
    // exercises every singular metric label ("Document" / "Page" /
    // "Law reference"), the "Untitled document" title fallback, and the
    // singular "page" meta — none of which the multi-document cases reach.
    const docs: DocSeed[] = [{ id: "Doc1", title: "", pageCount: 1 }];

    // Activating an entry (click or keyboard) resolves its canonical path via
    // the redirect query, so mock it to keep navigation a clean no-op. Two
    // copies — one for the click, one for the Enter press (mocks are single-use).
    const redirectMock = () => ({
      request: {
        query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
        variables: { id: "Doc1" },
      },
      result: {
        data: {
          document: {
            id: "Doc1",
            slug: "doc1",
            title: "Untitled document",
            creator: {
              id: "User:1",
              slug: "tester",
              username: "tester",
              email: "tester@example.com",
            },
          },
        },
      },
    });

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            docsMock(docs, 1),
            governanceMock(1),
            setupStatusSilentMock,
            redirectMock(),
            redirectMock(),
          ]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const metrics = page.locator(METRICS);
    await expect(metrics).toContainText("Document", { timeout: 10000 });
    // Singular forms, not "Documents" / "Pages" / "Law references".
    await expect(metrics).toContainText("Page");
    await expect(metrics).toContainText("Law reference");

    // The untitled document falls back to a placeholder title, and its single
    // page reads in the singular.
    const entry = page.locator(ENTRY).first();
    await expect(entry).toContainText("Untitled document");
    await expect(entry).toContainText("1 page");

    // The entry is activable by click and by keyboard (role=link, tabIndex=0);
    // both resolve+navigate without crashing the panel.
    await entry.click();
    await expect(page.locator(PANEL)).toBeVisible();
    await entry.focus();
    await entry.press("Enter");
    await expect(page.locator(PANEL)).toBeVisible();

    await component.unmount();
  });

  test("keeps corpus context when opening a collection entry", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <IntelligencePanelCorpusContextTestWrapper
        corpusId={CORPUS_ID}
        corpus={corpusNavigationContext}
        mocks={[
          docsMock([{ id: "Doc1", title: "Classification ruling" }]),
          governanceMock(0),
          setupStatusSilentMock,
        ]}
      />
    );

    await page.locator(ENTRY).first().click();
    await expect(page.getByTestId("router-location")).toHaveText(
      "/d/corpus-owner/cross-doc100/doc1"
    );

    await component.unmount();
  });

  test("sorts and renders documents with a null title without crashing", async ({
    mount,
    page,
  }) => {
    // Document.title is nullable on the backend (CharField(null=True)), so the
    // GraphQL field can come back null — e.g. mid-ingest, or a parser that
    // never set one. The client-side sort comparator must not call
    // .localeCompare() directly on a null title, or it throws and takes down
    // the whole panel for the corpus.
    const docs: DocSeed[] = [
      { id: "Doc1", title: "Zeta Agreement", pageCount: 5 },
      { id: "Doc2", title: null, pageCount: 2 },
      { id: "Doc3", title: "Alpha Agreement", pageCount: 1 },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[docsMock(docs, 3), governanceMock(0), setupStatusSilentMock]}
          addTypename={false}
        >
          <IntelligencePanel corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // The panel must render (not crash) and show all three entries, with the
    // null-title document falling back to the same placeholder used for
    // empty-string titles.
    await expect(page.locator(PANEL)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(ENTRY)).toHaveCount(3);
    await expect(page.locator(PANEL)).toContainText("Untitled document");
    await expect(page.locator(PANEL)).toContainText("Zeta Agreement");
    await expect(page.locator(PANEL)).toContainText("Alpha Agreement");

    await component.unmount();
  });

  test("toggles a large index back to 'Show fewer' after expanding", async ({
    mount,
    page,
  }) => {
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

    const showMore = page.locator(
      '[data-testid="corpus-intelligence-panel-show-more"]'
    );
    await expect(showMore).toBeVisible({ timeout: 10000 });

    // Expand, then collapse — the collapse path renders the "Show fewer" label
    // and restores the six-entry preview.
    await showMore.click();
    await expect(page.locator(ENTRY)).toHaveCount(8);
    await expect(showMore).toContainText("Show fewer");

    await showMore.click();
    await expect(page.locator(ENTRY)).toHaveCount(6);
    await expect(showMore).toContainText("Show all 8 documents");

    await component.unmount();
  });
});
