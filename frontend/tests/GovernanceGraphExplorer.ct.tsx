/**
 * Component tests for GovernanceGraphExplorer — the full-screen, interactive
 * destination of the reference-web glimpse's "Explore the full graph" link.
 * It fetches GET_GOVERNANCE_GRAPH (corpus-as-gate, capped at 200 nodes),
 * renders the same deterministic bipartite layout as the glimpse, and adds the
 * control rail (search + kind/authority filters), zoom/pan, and a node-detail
 * drawer (jurisdiction, authority type, crawl status, neighbours).
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { GovernanceGraphExplorer } from "../src/components/corpuses/CorpusHome/intelligence/GovernanceGraphExplorer";
import { GET_GOVERNANCE_GRAPH } from "../src/graphql/queries";
import { docScreenshot } from "./utils/docScreenshot";

const CORPUS_ID = "Q29ycHVzVHlwZTox";
const TID = "gov-explorer";

// A small but representative graph: two filing clusters, one in-system statute
// (DGCL § 145, Delaware) and one cited-but-not-ingested ghost (a federal
// Securities Act rule with a frontier crawl state) so the detail drawer's
// jurisdiction / authority-type / discovery-state fields all have something to
// show.
const GRAPH = {
  corpora: [
    { id: CORPUS_ID, title: "Select 2026 IPO S-1 Filings", kind: "filing" },
  ],
  nodes: [
    {
      id: "Doc:primary1",
      documentId: "Doc:primary1",
      title: "Acme Corp. S-1 (2026-01-15)",
      kind: "primary",
      corpusId: CORPUS_ID,
      authority: null,
      jurisdiction: null,
      authorityType: null,
      discoveryState: null,
      degree: 6,
    },
    {
      id: "Doc:exhibit1",
      documentId: "Doc:exhibit1",
      title: "Acme Corp. S-1 (2026-01-15) - Exhibit 1.1: EX-1.1",
      kind: "exhibit",
      corpusId: CORPUS_ID,
      authority: null,
      jurisdiction: null,
      authorityType: null,
      discoveryState: null,
      degree: 1,
    },
    {
      id: "Doc:primary2",
      documentId: "Doc:primary2",
      title: "Beta Energy Inc. S-1 (2026-02-02)",
      kind: "primary",
      corpusId: CORPUS_ID,
      authority: null,
      jurisdiction: null,
      authorityType: null,
      discoveryState: null,
      degree: 3,
    },
    {
      id: "Doc:statute145",
      documentId: "Doc:statute145",
      title: "DGCL § 145 — Indemnification of officers and directors",
      kind: "statute",
      corpusId: CORPUS_ID,
      authority: "dgcl",
      jurisdiction: "us-de",
      authorityType: "statute",
      discoveryState: null,
      degree: 4,
    },
    {
      id: "key:securities-act:4(a)(2)",
      documentId: null,
      title: "securities-act:4(a)(2)",
      kind: "external",
      corpusId: null,
      authority: "securities-act",
      jurisdiction: "us-federal",
      authorityType: "statute",
      discoveryState: "queued",
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
      target: "Doc:statute145",
      edgeType: "LAW",
      weight: 2,
    },
    {
      source: "Doc:primary1",
      target: "key:securities-act:4(a)(2)",
      edgeType: "LAW_EXTERNAL",
      weight: 3,
    },
  ],
  documentCount: 3,
  externalKeyCount: 1,
  edgeCount: 4,
  mentionCount: 9,
  truncated: false,
};

const makeGraphMock = (graph: typeof GRAPH | null) => ({
  request: { query: GET_GOVERNANCE_GRAPH, variables: { corpusId: CORPUS_ID } },
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

const corpus = { id: CORPUS_ID, title: "Select 2026 IPO S-1 Filings" } as any;

const mountExplorer = (
  mount: any,
  graph: typeof GRAPH | null,
  onBack = () => {}
) =>
  mount(
    <MemoryRouter>
      <MockedProvider
        mocks={[makeGraphMock(graph), makeGraphMock(graph)]}
        addTypename={false}
      >
        <GovernanceGraphExplorer corpus={corpus} onBack={onBack} testId={TID} />
      </MockedProvider>
    </MemoryRouter>
  );

test.describe("GovernanceGraphExplorer", () => {
  test("renders the reference web, control rail, and header stats", async ({
    mount,
    page,
  }) => {
    const component = await mountExplorer(mount, GRAPH);

    const svg = page.locator(`[data-testid="${TID}-svg"]`);
    await expect(svg).toBeVisible({ timeout: 10000 });

    // All five nodes render (2 primaries + 1 exhibit + 1 statute + 1 ghost).
    await expect(page.locator(`[data-testid="${TID}-node"]`)).toHaveCount(5);

    // The two layers are captioned and the header reflects the full graph.
    await expect(svg.getByText("THE FILINGS")).toBeVisible();
    await expect(svg.getByText("THE LAW")).toBeVisible();
    await expect(page.locator(`[data-testid="${TID}-meta"]`)).toContainText(
      "3 documents"
    );
    await expect(page.locator(`[data-testid="${TID}-meta"]`)).toContainText(
      "1 statute section"
    );
    await expect(page.locator(`[data-testid="${TID}-meta"]`)).toContainText(
      "1 cited, not ingested"
    );

    // Control rail: kind layers with live counts + a body-of-law chip per
    // authority actually present.
    const rail = page.locator(`[data-testid="${TID}-rail"]`);
    await expect(rail).toBeVisible();
    await expect(
      page.locator(`[data-testid="${TID}-group-filings"]`)
    ).toContainText("Filings & exhibits");
    await expect(
      page.locator(`[data-testid="${TID}-authority-dgcl"]`)
    ).toContainText("Delaware Gen. Corp. Law");
    await expect(
      page.locator(`[data-testid="${TID}-authority-securities-act"]`)
    ).toBeVisible();

    await docScreenshot(page, "graph--governance-explorer--with-data");

    await component.unmount();
  });

  test("clicking a node opens the detail drawer; a ghost shows jurisdiction, type and crawl status", async ({
    mount,
    page,
  }) => {
    const component = await mountExplorer(mount, GRAPH);
    await expect(page.locator(`[data-testid="${TID}-svg"]`)).toBeVisible({
      timeout: 10000,
    });

    // A filing node opens the inspector with an "Open document" affordance.
    await page
      .locator('[data-node-kind="primary"]')
      .first()
      .click({ force: true });
    const drawer = page.locator(`[data-testid="${TID}-detail"]`);
    await expect(drawer).toBeVisible();
    await expect(
      page.locator(`[data-testid="${TID}-detail-title"]`)
    ).toContainText("Acme Corp. S-1");
    await expect(
      page.locator(`[data-testid="${TID}-detail-open"]`)
    ).toBeVisible();

    // Dismiss the open drawer (it overlays the right edge of the canvas, where
    // a shelf ghost may sit) before selecting the next node.
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();

    // The ghost node surfaces the enriched fields the glimpse can't: body of
    // law, jurisdiction, authority type, and the frontier crawl state.
    await page
      .locator('[data-node-kind="external"]')
      .first()
      .click({ force: true });
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("Cited authority — not yet ingested");
    await expect(drawer).toContainText("Securities Act of 1933");
    await expect(drawer).toContainText("U.S. Federal");
    await expect(drawer).toContainText("Statute");
    await expect(
      page.locator(`[data-testid="${TID}-detail-status"]`)
    ).toContainText("Queued for discovery");

    // Escape dismisses the drawer again.
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();

    await component.unmount();
  });

  test("kind and authority filters toggle their pressed state", async ({
    mount,
    page,
  }) => {
    const component = await mountExplorer(mount, GRAPH);
    await expect(page.locator(`[data-testid="${TID}-svg"]`)).toBeVisible({
      timeout: 10000,
    });

    const statutes = page.locator(`[data-testid="${TID}-group-statutes"]`);
    await expect(statutes).toHaveAttribute("aria-pressed", "true");
    await statutes.click();
    await expect(statutes).toHaveAttribute("aria-pressed", "false");

    const dgcl = page.locator(`[data-testid="${TID}-authority-dgcl"]`);
    await expect(dgcl).toHaveAttribute("aria-pressed", "true");
    await dgcl.click();
    await expect(dgcl).toHaveAttribute("aria-pressed", "false");

    await component.unmount();
  });

  test("the back button invokes onBack", async ({ mount, page }) => {
    let backed = false;
    const component = await mountExplorer(mount, GRAPH, () => {
      backed = true;
    });
    await expect(page.locator(`[data-testid="${TID}-svg"]`)).toBeVisible({
      timeout: 10000,
    });
    await page.locator(`[data-testid="${TID}-back"]`).click();
    await expect.poll(() => backed).toBe(true);
    await component.unmount();
  });

  test("an empty graph shows a guidance state, not a broken canvas", async ({
    mount,
    page,
  }) => {
    const component = await mountExplorer(mount, null);
    await expect(page.locator(`[data-testid="${TID}-empty"]`)).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator(`[data-testid="${TID}-empty"]`)).toContainText(
      "No reference web yet"
    );
    // No canvas rail/zoom when there's nothing to explore.
    await expect(page.locator(`[data-testid="${TID}-rail"]`)).toHaveCount(0);
    await component.unmount();
  });
});
