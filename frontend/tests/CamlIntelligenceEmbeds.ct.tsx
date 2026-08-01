/**
 * Component tests for the corpus-intelligence CAML embeds — specifically the
 * ambient-context wiring (CamlEmbedContext). The underlying panel/graph/chips
 * are covered by their own component tests; here we verify the embeds read the
 * context and that ask-across-docs routes to the context's chat handler.
 *
 * NOTE: each JSX-component import is kept in its own statement, separate from
 * helper imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { gql } from "@apollo/client";
import { MockedProvider } from "@apollo/client/testing";
import { AskAcrossDocsEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/AskAcrossDocsEmbed";
import { DocumentGraphEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/DocumentGraphEmbed";
import { InsightPanelEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/InsightPanelEmbed";
import { CollectionDataStoryEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/CollectionDataStoryEmbed";
import { CamlEmbedProvider } from "../src/components/corpuses/caml/CamlEmbedContext";
import { MemoryRouter } from "react-router-dom";
import { docScreenshot } from "./utils/docScreenshot";
// Real query documents the rebuilt IntelligencePanel runs, so the insight-panel
// mocks stay in lock-step with the component (no hand-copied gql to drift).
import {
  GET_CORPUS_COLLECTION_DOCS,
  GET_GOVERNANCE_GRAPH,
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
  GET_CORPUS_DATA_STORY,
} from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

const GET_CORPUS_DOCUMENT_GRAPH = gql`
  query corpusDocumentGraph($corpusId: ID!, $limit: Int) {
    corpusDocumentGraph(corpusId: $corpusId, limit: $limit) {
      nodes {
        id
        title
        fileType
        degree
      }
      edges {
        id
        source
        target
        label
        relationshipType
      }
      totalNodeCount
      totalEdgeCount
      truncated
    }
  }
`;

// The rebuilt IntelligencePanel issues the collection-docs query (the documents
// index), the governance-graph query (the references metric), and — via the
// mounted setup banner — the setup-status query. The embed test only verifies
// the panel reads the ambient corpus id and renders, so these stay minimal.
const collectionDocsMock = {
  request: {
    query: GET_CORPUS_COLLECTION_DOCS,
    variables: { corpusId: CORPUS_ID, limit: 100, includeCaml: true },
  },
  result: {
    data: {
      documents: {
        totalCount: 1,
        edges: [
          {
            node: {
              id: "Doc:1",
              slug: "alpha-agreement",
              title: "Alpha Agreement",
              description: "A representative collection document.",
              pageCount: 6,
              fileType: "application/pdf",
            },
          },
        ],
      },
    },
  },
};

const governanceMock = {
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
        mentionCount: 0,
        truncated: false,
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

// The collection-datastory embed mounts the data story, which issues
// GET_CORPUS_DATA_STORY for the ambient corpus id.
const dataStoryMock = () => ({
  request: { query: GET_CORPUS_DATA_STORY, variables: { corpusId: CORPUS_ID } },
  result: {
    data: {
      corpusDataStory: {
        totalDocuments: 2,
        profiles: [
          {
            documentId: "Doc1",
            title: "Grant Agreement",
            slug: "doc1",
            type: "Grant",
            party: "Alpha Corp",
            effectiveDate: "2021-01-15",
            value: 12_000_000,
          },
          {
            documentId: "Doc2",
            title: "Renewal",
            slug: "doc2",
            type: "Renewal",
            party: "Beta LLC",
            effectiveDate: "2022-06-01",
            value: 1_500_000,
          },
        ],
      },
    },
  },
});

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

test.describe("CAML intelligence embeds", () => {
  test("ask-across-docs renders chips and routes to the context chat handler", async ({
    mount,
    page,
  }) => {
    const submitted: string[] = [];

    const component = await mount(
      <CamlEmbedProvider
        value={{
          corpusId: CORPUS_ID,
          onAskQuestion: (q) => {
            submitted.push(q);
          },
        }}
      >
        <AskAcrossDocsEmbed />
      </CamlEmbedProvider>
    );

    const chip = page
      .locator('[data-testid="ask-across-docs-suggestion"]')
      .first();
    await expect(chip).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "caml--ask-across-docs-embed--chips");

    await chip.click();
    await expect.poll(() => submitted.length).toBeGreaterThan(0);

    await component.unmount();
  });

  test("ask-across-docs renders nothing without a chat handler", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
        <AskAcrossDocsEmbed />
      </CamlEmbedProvider>
    );

    await expect(
      page.locator('[data-testid="ask-across-docs-suggestions"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("document-graph embed renders the live graph from the ambient corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[graphMock]} addTypename={false}>
        <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
          <DocumentGraphEmbed />
        </CamlEmbedProvider>
      </MockedProvider>
    );

    await expect(
      page.locator('[data-testid="document-graph-glimpse-node"]')
    ).toHaveCount(3, { timeout: 10000 });

    await docScreenshot(page, "caml--document-graph-embed--with-data");

    await component.unmount();
  });

  test("insight-panel embed renders the panel from the ambient corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      // MemoryRouter: the panel's index entries navigate via useNavigate.
      <MemoryRouter>
        <MockedProvider
          mocks={[collectionDocsMock, governanceMock, setupStatusSilentMock]}
          addTypename={false}
        >
          <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
            <InsightPanelEmbed />
          </CamlEmbedProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toBeVisible({ timeout: 10000 });
    // The embed wired the ambient corpus id through to the panel, which renders
    // the collection's documents index from that corpus's data.
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toContainText("Alpha Agreement", { timeout: 10000 });

    await docScreenshot(page, "caml--insight-panel-embed--with-data");

    await component.unmount();
  });

  test("collection-datastory embed renders the data story from the ambient corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[dataStoryMock()]} addTypename={false}>
        <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
          <CollectionDataStoryEmbed />
        </CamlEmbedProvider>
      </MockedProvider>
    );

    // The embed wires the ambient corpus id through to the data story. The
    // beeswarm is intentionally NOT mounted here (Phase-0 scaffolding removed
    // — it lives at its own /a/<slug> poster route instead) to avoid showing
    // the same artifact twice on the CAML article.
    await expect(
      page.locator('[data-testid="collection-data-story"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="spending-beeswarm"]')).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("collection-datastory embed renders nothing without an ambient corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <CamlEmbedProvider value={{}}>
          <CollectionDataStoryEmbed />
        </CamlEmbedProvider>
      </MockedProvider>
    );

    // No corpus id (neither prop nor context) -> the embed short-circuits to null.
    await expect(
      page.locator('[data-testid="collection-data-story"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
