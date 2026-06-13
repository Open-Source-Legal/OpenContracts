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
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { GovernanceGraphLive } from "../src/components/corpuses/CorpusHome/intelligence/GovernanceGraphLive";
import { GovernanceGraphEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/GovernanceGraphEmbed";
import { CamlEmbedProvider } from "../src/components/corpuses/caml/CamlEmbedContext";
import { docScreenshot } from "./utils/docScreenshot";
import { ToastContainer } from "react-toastify";
import {
  GET_GOVERNANCE_GRAPH,
  GET_WANTED_AUTHORITIES,
  GET_ANALYZERS_FOR_ENRICHMENT,
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
} from "../src/graphql/queries";
import { START_ANALYSIS, CREATE_CORPUS_ACTION } from "../src/graphql/mutations";
import { ENRICHMENT_ANALYZER_TASK_NAME } from "../src/assets/configurations/constants";

const CORPUS_ID = "Q29ycHVzVHlwZTox";
const AUTH_CORPUS_ID = "Q29ycHVzVHlwZToy";
const ENRICH_ANALYZER_ID = "QW5hbHl6ZXJUeXBlOjE=";

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

// Once the graph has nodes, GovernanceGraphLive also fires the
// wanted-authorities backlog query; an empty backlog keeps these tests
// focused on the graph itself (the card has its own tests in
// WantedAuthorities.ct.tsx).
const emptyWantedMock = {
  request: {
    query: GET_WANTED_AUTHORITIES,
    variables: { corpusId: CORPUS_ID },
  },
  result: { data: { wantedAuthorities: [] } },
};

// --- Bootstrap-flow mocks (empty graph → "Map the reference web") -----------

const analyzersMock = (taskName: string | null) => ({
  request: { query: GET_ANALYZERS_FOR_ENRICHMENT },
  result: {
    data: {
      analyzers: {
        edges: taskName ? [{ node: { id: ENRICH_ANALYZER_ID, taskName } }] : [],
      },
    },
  },
});

const startAnalysisMock = {
  request: {
    query: START_ANALYSIS,
    variables: { analyzerId: ENRICH_ANALYZER_ID, corpusId: CORPUS_ID },
  },
  result: {
    data: {
      startAnalysisOnDoc: {
        ok: true,
        message: "Started",
        obj: {
          id: "QW5hbHlzaXNUeXBlOjE=",
          analysisStarted: "2026-01-01T00:00:00Z",
          analysisCompleted: null,
          analyzedDocuments: { edges: [] },
          receivedCallbackFile: null,
          annotations: { totalCount: 0 },
          analyzer: {
            id: ENRICH_ANALYZER_ID,
            analyzerId: "reference-enrichment",
            description: "",
            manifest: null,
            labelsetSet: { totalCount: 0 },
            hostGremlin: null,
          },
        },
      },
    },
  },
};

const createCorpusActionMock = {
  request: {
    query: CREATE_CORPUS_ACTION,
    variables: {
      corpusId: CORPUS_ID,
      trigger: "add_document",
      analyzerId: ENRICH_ANALYZER_ID,
      name: "Reference enrichment (auto)",
    },
  },
  result: { data: { createCorpusAction: { ok: true, message: "ok" } } },
};

// The bootstrap consults the intelligence-setup status before installing the
// add_document action, so a row installed elsewhere (one-click setup) isn't
// duplicated.
const setupStatusMock = (referenceActionInstalled: boolean) => ({
  request: {
    query: GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusIntelligenceSetupStatus: {
        referenceAvailable: true,
        referenceActionInstalled,
        installedTemplateNames: [],
        missingTemplateNames: [],
        isFullySetUp: false,
        canSetup: true,
      },
    },
  },
});

// Node click-through resolves the document's slugs via the redirect query,
// then navigates to its standalone canonical path (the redirect query
// carries no corpus context). Beta Energy's primary node is the
// unambiguous target (no exhibit shares its title).
const redirectMock = {
  request: {
    query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
    variables: { id: "Doc:primary2" },
  },
  result: {
    data: {
      document: {
        id: "Doc:primary2",
        slug: "beta-energy-s1",
        title: "Beta Energy Inc. S-1 (2026-02-02)",
        creator: {
          id: "VXNlcjox",
          slug: "acme",
          username: "acme",
          email: "acme@example.com",
        },
      },
    },
  },
};

test.describe("GovernanceGraphLive", () => {
  test("renders the reference web with shelf captions, legend, and stats", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            makeGraphMock(GRAPH),
            makeGraphMock(GRAPH),
            emptyWantedMock,
            emptyWantedMock,
          ]}
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
          mocks={[makeGraphMock(GRAPH, 2000), emptyWantedMock, emptyWantedMock]}
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

  test("bootstrap CTA starts enrichment and enters the weaving state", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            // initial query (empty → CTA) plus a few extra for the weave poll
            makeGraphMock(null),
            makeGraphMock(null),
            makeGraphMock(null),
            makeGraphMock(null),
            analyzersMock(ENRICHMENT_ANALYZER_TASK_NAME),
            startAnalysisMock,
            setupStatusMock(false),
            createCorpusActionMock,
          ]}
          addTypename={false}
        >
          <GovernanceGraphLive corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const bootstrap = page.locator(
      '[data-testid="governance-graph-live-bootstrap"]'
    );
    await expect(bootstrap).toBeVisible({ timeout: 10000 });
    await bootstrap.click();

    // Analyzer fetch → startAnalysis → add_document action → weaving state.
    await expect(
      page.locator('[data-testid="governance-graph-live-weaving"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("bootstrap skips installing the action when one is already installed", async ({
    mount,
    page,
  }) => {
    // No createCorpusActionMock on purpose: with the reference action already
    // installed (e.g. by one-click intelligence setup) the bootstrap must not
    // fire CREATE_CORPUS_ACTION at all — an unexpected call would error and
    // surface the "couldn't be installed" info toast.
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            makeGraphMock(null),
            makeGraphMock(null),
            makeGraphMock(null),
            makeGraphMock(null),
            analyzersMock(ENRICHMENT_ANALYZER_TASK_NAME),
            startAnalysisMock,
            setupStatusMock(true),
          ]}
          addTypename={false}
        >
          <>
            <ToastContainer />
            <GovernanceGraphLive corpusId={CORPUS_ID} />
          </>
        </MockedProvider>
      </MemoryRouter>
    );

    const bootstrap = page.locator(
      '[data-testid="governance-graph-live-bootstrap"]'
    );
    await expect(bootstrap).toBeVisible({ timeout: 10000 });
    await bootstrap.click();

    await expect(
      page.locator('[data-testid="governance-graph-live-weaving"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText(/keep-it-updated action couldn't be installed/i)
    ).toHaveCount(0);

    await component.unmount();
  });

  test("bootstrap surfaces an error when enrichment is unavailable", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            makeGraphMock(null),
            makeGraphMock(null),
            analyzersMock(null),
          ]}
          addTypename={false}
        >
          <GovernanceGraphLive corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    const bootstrap = page.locator(
      '[data-testid="governance-graph-live-bootstrap"]'
    );
    await expect(bootstrap).toBeVisible({ timeout: 10000 });
    await bootstrap.click();

    // No analyzer → no weave; the CTA stays available for a retry.
    await expect(bootstrap).toContainText("Map the reference web");
    await expect(
      page.locator('[data-testid="governance-graph-live-weaving"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("clicking a document node navigates to its canonical path", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter initialEntries={["/"]}>
        <MockedProvider
          mocks={[
            makeGraphMock(GRAPH),
            makeGraphMock(GRAPH),
            emptyWantedMock,
            emptyWantedMock,
            redirectMock,
          ]}
          addTypename={false}
        >
          <Routes>
            <Route
              path="/d/acme/beta-energy-s1"
              element={<div data-testid="node-nav-arrived">arrived</div>}
            />
            <Route
              path="*"
              element={<GovernanceGraphLive corpusId={CORPUS_ID} />}
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    const betaNode = page
      .locator('[data-testid="governance-graph-live-node"]')
      .filter({ hasText: "Beta Energy" });
    await expect(betaNode).toBeVisible({ timeout: 10000 });
    await betaNode.click();

    await expect(page.locator('[data-testid="node-nav-arrived"]')).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});

// The CAML embed is a thin wrapper: it resolves the corpus id from
// CamlEmbedContext (marker prop overriding ambient) and delegates rendering to
// GovernanceGraphLive. These tests pin the context->corpusId->Live wiring and
// the no-corpus null guard.
test.describe("GovernanceGraphEmbed", () => {
  test("renders the live graph from the ambient CAML corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider
          mocks={[
            makeGraphMock(GRAPH),
            makeGraphMock(GRAPH),
            emptyWantedMock,
            emptyWantedMock,
          ]}
          addTypename={false}
        >
          <CamlEmbedProvider value={{ corpusId: CORPUS_ID }}>
            <GovernanceGraphEmbed />
          </CamlEmbedProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="governance-graph-live-svg"]')
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="governance-graph-live-node"]')
    ).toHaveCount(6);

    await docScreenshot(page, "caml--governance-graph-embed--with-data");

    await component.unmount();
  });

  test("renders nothing without an ambient corpus id", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={[]} addTypename={false}>
          <CamlEmbedProvider value={{}}>
            <GovernanceGraphEmbed />
          </CamlEmbedProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.locator('[data-testid="governance-graph-live-svg"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
