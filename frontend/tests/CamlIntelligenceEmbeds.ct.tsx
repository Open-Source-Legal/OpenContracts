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
import { CamlEmbedProvider } from "../src/components/corpuses/caml/CamlEmbedContext";
import { docScreenshot } from "./utils/docScreenshot";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

const GET_CORPUS_STATS = gql`
  query corpusStats($corpusId: ID!) {
    corpusStats(corpusId: $corpusId) {
      totalDocs
      totalComments
      totalAnalyses
      totalExtracts
      totalAnnotations
      totalThreads
      totalChats
      totalRelationships
    }
  }
`;

const GET_CORPUS_INTELLIGENCE_AGGREGATES = gql`
  query corpusIntelligenceAggregates($corpusId: ID!) {
    corpusIntelligenceAggregates(corpusId: $corpusId) {
      labelDistribution {
        label
        color
        count
      }
      documentsWithSummary
      totalDocuments
    }
  }
`;

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

const statsMock = {
  request: { query: GET_CORPUS_STATS, variables: { corpusId: CORPUS_ID } },
  result: {
    data: {
      corpusStats: {
        totalDocs: 3,
        totalComments: 0,
        totalAnalyses: 0,
        totalExtracts: 1,
        totalAnnotations: 12,
        totalThreads: 0,
        totalChats: 0,
        totalRelationships: 2,
      },
    },
  },
};

const aggMock = {
  request: {
    query: GET_CORPUS_INTELLIGENCE_AGGREGATES,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusIntelligenceAggregates: {
        labelDistribution: [
          { label: "Risk Factor", color: "#ef4444", count: 8 },
        ],
        documentsWithSummary: 2,
        totalDocuments: 3,
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
      <MockedProvider mocks={[statsMock, aggMock]} addTypename={false}>
        <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
          <InsightPanelEmbed />
        </CamlEmbedProvider>
      </MockedProvider>
    );

    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toContainText("Risk Factor", { timeout: 10000 });

    await docScreenshot(page, "caml--insight-panel-embed--with-data");

    await component.unmount();
  });
});
