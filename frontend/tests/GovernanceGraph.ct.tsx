/**
 * Component tests for GovernanceGraphLive — the Apollo-wired shell that
 * fetches GET_GOVERNANCE_GRAPH and renders the presentational
 * GovernanceGraphGlimpse (the reference web: filings above, law shelf below),
 * including the empty-state "Map the reference web" bootstrap CTA.
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { GovernanceGraphLive } from "../src/components/corpuses/CorpusHome/intelligence/GovernanceGraphLive";
import { docScreenshot } from "./utils/docScreenshot";
import { GET_GOVERNANCE_GRAPH } from "../src/graphql/queries";

const CORPUS_ID = "Q29ycHVzVHlwZTox";
const AUTH_CORPUS_ID = "Q29ycHVzVHlwZToy";

const GRAPH = {
  corpora: [
    { id: CORPUS_ID, title: "Select 2026 IPO S-1 Filings", kind: "filing" },
    {
      id: AUTH_CORPUS_ID,
      title: "Delaware General Corporation Law",
      kind: "authority",
    },
  ],
  nodes: [
    {
      id: "Doc:primary1",
      documentId: "Doc:primary1",
      title: "Acme Corp. S-1 (2026-01-15)",
      kind: "primary",
      corpusId: CORPUS_ID,
      authority: null,
      degree: 6,
    },
    {
      id: "Doc:exhibit1",
      documentId: "Doc:exhibit1",
      title: "Acme Corp. S-1 (2026-01-15) - Exhibit 1.1: EX-1.1",
      kind: "exhibit",
      corpusId: CORPUS_ID,
      authority: null,
      degree: 1,
    },
    {
      id: "Doc:primary2",
      documentId: "Doc:primary2",
      title: "Beta Energy Inc. S-1 (2026-02-02)",
      kind: "primary",
      corpusId: CORPUS_ID,
      authority: null,
      degree: 3,
    },
    {
      id: "Doc:statute145",
      documentId: "Doc:statute145",
      title: "DGCL § 145 — Indemnification of officers and directors",
      kind: "statute",
      corpusId: AUTH_CORPUS_ID,
      authority: "dgcl",
      degree: 4,
    },
    {
      id: "Doc:statute203",
      documentId: "Doc:statute203",
      title: "DGCL § 203 — Business combinations",
      kind: "statute",
      corpusId: AUTH_CORPUS_ID,
      authority: "dgcl",
      degree: 2,
    },
    {
      id: "key:securities-act:4(a)(2)",
      documentId: null,
      title: "securities-act:4(a)(2)",
      kind: "external",
      corpusId: null,
      authority: "securities-act",
      degree: 3,
    },
  ],
  edges: [
    {
      source: "Doc:primary1",
      target: "Doc:exhibit1",
      edgeType: "DOCUMENT",
      weight: 1,
    },
    {
      source: "Doc:primary1",
      target: "Doc:statute145",
      edgeType: "LAW",
      weight: 3,
    },
    {
      source: "Doc:primary2",
      target: "Doc:statute203",
      edgeType: "LAW",
      weight: 2,
    },
    {
      source: "Doc:primary1",
      target: "key:securities-act:4(a)(2)",
      edgeType: "LAW_EXTERNAL",
      weight: 2,
    },
    {
      source: "Doc:primary2",
      target: "key:securities-act:4(a)(2)",
      edgeType: "LAW_EXTERNAL",
      weight: 1,
    },
  ],
  documentCount: 5,
  externalKeyCount: 1,
  edgeCount: 5,
  mentionCount: 9,
  truncated: false,
};

const makeGraphMock = (graph: typeof GRAPH | null, delay?: number) => ({
  request: {
    query: GET_GOVERNANCE_GRAPH,
    variables: { corpusId: CORPUS_ID },
  },
  ...(delay ? { delay } : {}),
  result: {
    data: {
      governanceGraph: graph ?? {
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
});

test.describe("GovernanceGraphLive", () => {
  test("renders the reference web with shelf captions, legend, and stats", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[makeGraphMock(GRAPH), makeGraphMock(GRAPH)]}
          addTypename={false}
        >
          <GovernanceGraphLive corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const svg = page.locator('[data-testid="governance-graph-live-svg"]');
    await expect(svg).toBeVisible({ timeout: 10000 });

    // All six nodes render (2 primaries + 1 exhibit + 2 statutes + 1 ghost).
    await expect(
      page.locator('[data-testid="governance-graph-live-node"]')
    ).toHaveCount(6);

    // The two layers are captioned.
    await expect(svg.getByText("THE FILINGS")).toBeVisible();
    await expect(svg.getByText("THE LAW")).toBeVisible();

    // Authority captions appear under the shelf — both the registered DGCL
    // caption and the Securities Act group from the ghost node.
    await expect(svg.getByText("DELAWARE GEN. CORP. LAW")).toBeVisible();
    await expect(svg.getByText("SECURITIES ACT OF 1933")).toBeVisible();

    // Statute labels render their citation heads (scoped to the labels group
    // — the node <title> tooltips also contain the citation text).
    await expect(
      svg
        .locator('[data-testid="governance-graph-live-labels"] text')
        .filter({ hasText: "DGCL § 145" })
    ).toBeVisible();

    // Header stats reflect the full graph.
    await expect(
      page.locator('[data-testid="governance-graph-live-meta"]')
    ).toContainText("5 documents · 2 statute sections · 9 references resolved");

    // Legend explains the vocabulary actually present.
    const legend = page.locator('[data-testid="governance-graph-live-legend"]');
    await expect(legend).toContainText("Statute section");
    await expect(legend).toContainText("Cited, not yet ingested");

    await docScreenshot(page, "corpus--governance-graph--with-data");

    await component.unmount();
  });

  test("empty graph shows the map-the-reference-web bootstrap CTA", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[makeGraphMock(null), makeGraphMock(null)]}
          addTypename={false}
        >
          <GovernanceGraphLive corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="governance-graph-live-empty"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="governance-graph-live-bootstrap"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="governance-graph-live-bootstrap"]')
    ).toContainText("Map the reference web");

    await docScreenshot(page, "corpus--governance-graph--empty-cta");

    await component.unmount();
  });

  test("shows a skeleton while the query is in flight", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[makeGraphMock(GRAPH, 2000)]}
          addTypename={false}
        >
          <GovernanceGraphLive corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="governance-graph-live-skeleton"]')
    ).toBeVisible({ timeout: 5000 });

    // ...and resolves into the graph.
    await expect(
      page.locator('[data-testid="governance-graph-live-svg"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
