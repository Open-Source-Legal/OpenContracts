/**
 * Component tests for CorpusIntelligenceOverview — the composed "God's-eye
 * view" block injected into the corpus landing. It fuses the IntelligencePanel
 * (collection-docs + setup-status queries), the DocumentGraphGlimpse (graph
 * query), and the one-click cross-document question chips, so it mounts under a
 * MockedProvider supplying all of them.
 *
 * NOTE: each JSX-component import is kept in its own statement (MockedProvider,
 * CorpusIntelligenceOverview) per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { CorpusIntelligenceOverview } from "../src/components/corpuses/CorpusHome/intelligence/CorpusIntelligenceOverview";
import { docScreenshot } from "./utils/docScreenshot";
// Import the real query documents the component runs, so the mocks below stay
// in lock-step with any future field additions (no hand-copied gql to drift).
import {
  GET_CORPUS_COLLECTION_DOCS,
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
  GET_CORPUS_DOCUMENT_GRAPH,
  GET_GOVERNANCE_GRAPH,
  GET_WANTED_AUTHORITIES,
} from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

// The composed IntelligencePanel issues the collection-docs query (its documents
// index) and — via the mounted setup banner — the setup-status query. It shares
// the governance-graph query with GovernanceGraphLive (mocked below).
const collectionDocsMock = {
  request: {
    query: GET_CORPUS_COLLECTION_DOCS,
    variables: { corpusId: CORPUS_ID, limit: 100, includeCaml: true },
  },
  result: {
    data: {
      documents: {
        totalCount: 3,
        edges: [
          {
            node: {
              id: "Doc:1",
              slug: "alpha",
              title: "Alpha",
              description: "First collection document.",
              pageCount: 6,
              fileType: "application/pdf",
            },
          },
          {
            node: {
              id: "Doc:2",
              slug: "beta",
              title: "Beta",
              description: "",
              pageCount: 3,
              fileType: "application/pdf",
            },
          },
          {
            node: {
              id: "Doc:3",
              slug: "gamma",
              title: "Gamma",
              description: "",
              pageCount: 2,
              fileType: "application/pdf",
            },
          },
        ],
      },
    },
  },
};

// A fully-set-up corpus keeps the mounted setup banner silent.
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

const graphMock = {
  request: {
    query: GET_CORPUS_DOCUMENT_GRAPH,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusDocumentGraph: {
        nodes: [
          {
            id: "Doc:1",
            title: "Alpha",
            fileType: "application/pdf",
            degree: 2,
          },
          {
            id: "Doc:2",
            title: "Beta",
            fileType: "application/pdf",
            degree: 1,
          },
          {
            id: "Doc:3",
            title: "Gamma",
            fileType: "application/pdf",
            degree: 1,
          },
        ],
        edges: [
          {
            id: "e1",
            source: "Doc:1",
            target: "Doc:2",
            label: "Cites",
            relationshipType: "RELATIONSHIP",
          },
          {
            id: "e2",
            source: "Doc:1",
            target: "Doc:3",
            label: null,
            relationshipType: "NOTES",
          },
        ],
        totalNodeCount: 3,
        totalEdgeCount: 2,
        truncated: false,
      },
    },
  },
};

// The overview also mounts GovernanceGraphLive (GET_GOVERNANCE_GRAPH); an
// empty graph keeps these tests focused on the document graph + chips.
// Mocked twice per mount to absorb refetches.
const governanceMock = {
  request: {
    query: GET_GOVERNANCE_GRAPH,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      governanceGraph: {
        corpora: [],
        nodes: [],
        edges: [],
        documentCount: 0,
        externalKeyCount: 0,
        edgeCount: 0,
        mentionCount: 0,
        truncated: false,
      },
    },
  },
};

// Empty backlog → WantedAuthoritiesLive renders nothing (by design).
const wantedMock = {
  request: {
    query: GET_WANTED_AUTHORITIES,
    variables: { corpusId: CORPUS_ID },
  },
  result: { data: { wantedAuthorities: [] } },
};

test.describe("CorpusIntelligenceOverview", () => {
  test("composes the panel, the document graph, and question chips", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      // MemoryRouter: GovernanceGraphLive's node click-through hook calls
      // useNavigate, which requires a Router context.
      <MemoryRouter>
        <MockedProvider
          mocks={[
            collectionDocsMock,
            setupStatusSilentMock,
            graphMock,
            governanceMock,
            governanceMock,
            governanceMock,
            wantedMock,
            wantedMock,
          ]}
          addTypename={false}
        >
          <CorpusIntelligenceOverview
            corpusId={CORPUS_ID}
            onAskQuestion={() => {}}
            onExploreGraph={() => {}}
          />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="corpus-intelligence-overview"]')
    ).toBeVisible({ timeout: 10000 });

    // The composed panel renders.
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toBeVisible({ timeout: 10000 });

    // The document graph resolves to three nodes / two edges.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-node"]')
    ).toHaveCount(3);
    await expect(
      page.locator('[data-testid="document-graph-glimpse-edges"] line')
    ).toHaveCount(2);

    // Cross-document question chips appear when onAskQuestion is provided.
    await expect(
      page.locator('[data-testid="corpus-intelligence-overview-suggestion"]')
    ).not.toHaveCount(0);

    // The explore escape hatch renders when onExploreGraph is provided.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-explore"]')
    ).toBeVisible();

    await docScreenshot(page, "corpus--intelligence-overview--with-data");

    await component.unmount();
  });

  test("ask-a-question chip invokes the onAskQuestion callback", async ({
    mount,
    page,
  }) => {
    const submitted: string[] = [];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            collectionDocsMock,
            setupStatusSilentMock,
            graphMock,
            governanceMock,
            governanceMock,
            governanceMock,
            wantedMock,
            wantedMock,
          ]}
          addTypename={false}
        >
          <CorpusIntelligenceOverview
            corpusId={CORPUS_ID}
            onAskQuestion={(q) => {
              submitted.push(q);
            }}
          />
        </MockedProvider>
      </MemoryRouter>
    );

    const chip = page
      .locator('[data-testid="corpus-intelligence-overview-suggestion"]')
      .first();
    await expect(chip).toBeVisible({ timeout: 10000 });
    await chip.click();

    await expect.poll(() => submitted.length).toBeGreaterThan(0);

    // No onExploreGraph prop on this mount → no explore escape hatch.
    await expect(
      page.locator('[data-testid="document-graph-glimpse-explore"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
