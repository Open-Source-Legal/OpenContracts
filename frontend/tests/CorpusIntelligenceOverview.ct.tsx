/**
 * Component tests for CorpusIntelligenceOverview — the composed "God's-eye
 * view" block injected into the corpus landing. It fuses the IntelligencePanel
 * (stats + aggregates queries), the DocumentGraphGlimpse (graph query), and the
 * one-click cross-document question chips, so it mounts under a MockedProvider
 * supplying all three queries.
 *
 * NOTE: each JSX-component import is kept in its own statement (MockedProvider,
 * CorpusIntelligenceOverview) per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { gql } from "@apollo/client";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusIntelligenceOverview } from "../src/components/corpuses/CorpusHome/intelligence/CorpusIntelligenceOverview";
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

test.describe("CorpusIntelligenceOverview", () => {
  test("composes the panel, the document graph, and question chips", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[statsMock, aggMock, graphMock]}
        addTypename={false}
      >
        <CorpusIntelligenceOverview
          corpusId={CORPUS_ID}
          onAskQuestion={() => {}}
          onExploreGraph={() => {}}
        />
      </MockedProvider>
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
      <MockedProvider
        mocks={[statsMock, aggMock, graphMock]}
        addTypename={false}
      >
        <CorpusIntelligenceOverview
          corpusId={CORPUS_ID}
          onAskQuestion={(q) => {
            submitted.push(q);
          }}
        />
      </MockedProvider>
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
