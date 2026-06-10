/**
 * Component tests for IntelligencePanel — the insight-framed metrics panel on
 * the Corpus Intelligence home. It issues two queries (corpus stats + corpus
 * intelligence aggregates), so it mounts under a MockedProvider.
 *
 * NOTE: each JSX-component import is kept in its own statement (MockedProvider,
 * IntelligencePanel) per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { IntelligencePanel } from "../src/components/corpuses/CorpusHome/intelligence/IntelligencePanel";
import { docScreenshot } from "./utils/docScreenshot";
// Import the real query documents the component runs, so the mocks below stay
// in lock-step with any future field additions (no hand-copied gql to drift).
import {
  GET_CORPUS_STATS,
  GET_CORPUS_INTELLIGENCE_AGGREGATES,
} from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

const statsMock = {
  request: { query: GET_CORPUS_STATS, variables: { corpusId: CORPUS_ID } },
  result: {
    data: {
      corpusStats: {
        totalDocs: 12,
        totalComments: 0,
        totalAnalyses: 0,
        totalExtracts: 4,
        totalAnnotations: 87,
        totalThreads: 0,
        totalChats: 0,
        totalRelationships: 9,
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
          { label: "Risk Factor", color: "#ef4444", count: 40 },
          // A deliberately unsafe color must not break rendering (sanitized).
          { label: "Obligation", color: "red; } body { x:y", count: 25 },
        ],
        documentsWithSummary: 6,
        totalDocuments: 12,
      },
    },
  },
};

test.describe("IntelligencePanel", () => {
  test("renders stats, summary coverage, and the label distribution", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[statsMock, aggMock]} addTypename={false}>
        <IntelligencePanel corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    await expect(
      page.locator('[data-testid="corpus-intelligence-panel"]')
    ).toBeVisible({ timeout: 10000 });

    // Stat-card labels render once the stats query resolves. ``exact`` avoids
    // colliding with the coverage caption ("…documents summarized").
    await expect(page.getByText("Documents", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Connections", { exact: true })).toBeVisible();

    // Summary-coverage caption reflects the aggregates (6 of 12).
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel-coverage"]')
    ).toContainText("6 of 12");

    // Label distribution lists the dominant labels.
    const labelsCard = page.locator(
      '[data-testid="corpus-intelligence-panel-labels"]'
    );
    await expect(labelsCard).toContainText("Risk Factor");
    await expect(labelsCard).toContainText("Obligation");

    await docScreenshot(page, "corpus--intelligence-panel--with-data");

    await component.unmount();
  });

  test("hides zero-value stat cards and humanizes machine label names", async ({
    mount,
    page,
  }) => {
    const zeroExtractsStats = {
      request: { query: GET_CORPUS_STATS, variables: { corpusId: CORPUS_ID } },
      result: {
        data: {
          corpusStats: {
            totalDocs: 12,
            totalComments: 0,
            totalAnalyses: 0,
            totalExtracts: 0, // → the Extracts card must be suppressed
            totalAnnotations: 87,
            totalThreads: 0,
            totalChats: 0,
            totalRelationships: 9,
          },
        },
      },
    };
    const jargonAgg = {
      request: {
        query: GET_CORPUS_INTELLIGENCE_AGGREGATES,
        variables: { corpusId: CORPUS_ID },
      },
      result: {
        data: {
          corpusIntelligenceAggregates: {
            labelDistribution: [
              { label: "SEC_HEADER", color: "#0ea5e9", count: 19 },
              { label: "Exhibit", color: "#16a34a", count: 18 },
            ],
            documentsWithSummary: 6,
            totalDocuments: 12,
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider
        mocks={[zeroExtractsStats, jargonAgg]}
        addTypename={false}
      >
        <IntelligencePanel corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // Non-zero stats render; the zero-valued Extracts card is dropped entirely.
    await expect(page.getByText("Documents", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Extracts", { exact: true })).toHaveCount(0);

    // The machine label name is humanized for display.
    const labelsCard = page.locator(
      '[data-testid="corpus-intelligence-panel-labels"]'
    );
    await expect(labelsCard).toContainText("SEC Header");
    await expect(labelsCard).not.toContainText("SEC_HEADER");

    await component.unmount();
  });

  test("shows skeletons while loading and an empty hint with no labels", async ({
    mount,
    page,
  }) => {
    // Delay resolution so the first-load skeleton state is observable before
    // the data arrives (otherwise MockedProvider resolves near-instantly).
    const delayedStats = { ...statsMock, delay: 600 };
    const emptyAgg = {
      request: {
        query: GET_CORPUS_INTELLIGENCE_AGGREGATES,
        variables: { corpusId: CORPUS_ID },
      },
      delay: 600,
      result: {
        data: {
          corpusIntelligenceAggregates: {
            labelDistribution: [],
            documentsWithSummary: 0,
            totalDocuments: 0,
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[delayedStats, emptyAgg]} addTypename={false}>
        <IntelligencePanel corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // Before the queries resolve the stat row shows shimmer skeletons rather
    // than a misleading row of zeros.
    await expect(
      page.locator('[data-testid^="corpus-intelligence-panel-stat-skeleton-"]')
    ).toHaveCount(4);

    // Once the empty aggregates resolve, the labels card shows the empty hint.
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel-labels"]')
    ).toContainText("No labeled annotations yet", { timeout: 10000 });

    await component.unmount();
  });

  test("surfaces error hints instead of a misleading empty state on fetch failure", async ({
    mount,
    page,
  }) => {
    const statsError = {
      request: { query: GET_CORPUS_STATS, variables: { corpusId: CORPUS_ID } },
      error: new Error("stats boom"),
    };
    const aggError = {
      request: {
        query: GET_CORPUS_INTELLIGENCE_AGGREGATES,
        variables: { corpusId: CORPUS_ID },
      },
      error: new Error("agg boom"),
    };

    const component = await mount(
      <MockedProvider mocks={[statsError, aggError]} addTypename={false}>
        <IntelligencePanel corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    // A failed fetch must not masquerade as an empty collection (all-zero
    // stats / "no labels") — each card shows a distinct error hint.
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel-stats-error"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="corpus-intelligence-panel-labels-error"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
