/**
 * Component tests for AuthoritySourcesMonitor — the global, superuser-only
 * /admin/authorities view over the AuthorityFrontier (crawl/ingestion state of
 * cited law across all corpora). Verifies the superuser gate, the state-count
 * chips + table render, chip-driven filtering, and the empty state.
 *
 * NOTE: the JSX-component import is kept in its own ``import`` statement,
 * separate from helper/query imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthoritySourcesMonitorTestWrapper } from "./AuthoritySourcesMonitorTestWrapper";
import {
  GET_AUTHORITY_FRONTIER,
  GET_AUTHORITY_FRONTIER_STATS,
} from "../src/graphql/queries";
import { AUTHORITY_FRONTIER_PAGE_SIZE } from "../src/assets/configurations/constants";
import { docScreenshot } from "./utils/docScreenshot";

const FACETS = {
  jurisdiction: null,
  authorityType: null,
  provider: null,
  search: null,
};

const STATS = {
  totalCount: 4,
  byState: [
    { state: "ingested", count: 1 },
    { state: "failed", count: 1 },
    { state: "queued", count: 2 },
  ],
};

const node = (over: Record<string, unknown>) => ({
  node: {
    id: `AF:${over.canonicalKey}`,
    canonicalKey: "x",
    authority: null,
    jurisdiction: null,
    authorityType: null,
    discoveryState: "queued",
    provider: null,
    mentionCount: 0,
    distinctCorpusCount: 0,
    depth: 0,
    lastError: null,
    lastAttempt: null,
    ingestedDocument: null,
    ...over,
  },
});

const ALL_ROWS = [
  node({
    canonicalKey: "usc-15:78j",
    authority: "usc-15",
    jurisdiction: "us-federal",
    authorityType: "statute",
    discoveryState: "ingested",
    provider: "USCodeAuthoritySourceProvider",
    mentionCount: 142,
    distinctCorpusCount: 9,
    ingestedDocument: {
      id: "Doc:1",
      title: "15 U.S.C. § 78j",
      slug: "usc-78j",
    },
  }),
  node({
    canonicalKey: "cfr-17:240.10b",
    authority: "cfr-17",
    jurisdiction: "us-federal",
    authorityType: "regulation",
    discoveryState: "failed",
    provider: "CFRAuthoritySourceProvider",
    mentionCount: 88,
    distinctCorpusCount: 6,
    lastError: "No source found for cfr-17:240.10b",
  }),
  node({
    canonicalKey: "dgcl:145",
    authority: "dgcl",
    jurisdiction: "us-de",
    authorityType: "statute",
    discoveryState: "queued",
    mentionCount: 54,
    distinctCorpusCount: 4,
  }),
  node({
    canonicalKey: "dgcl:203",
    authority: "dgcl",
    jurisdiction: "us-de",
    authorityType: "statute",
    discoveryState: "queued",
    mentionCount: 30,
    distinctCorpusCount: 3,
  }),
];

const statsMock = (stats: typeof STATS) => ({
  request: { query: GET_AUTHORITY_FRONTIER_STATS, variables: FACETS },
  result: { data: { authorityFrontierStats: stats } },
});

const frontierMock = (
  rows: ReturnType<typeof node>[],
  discoveryState: string | null = null
) => ({
  request: {
    query: GET_AUTHORITY_FRONTIER,
    variables: {
      ...FACETS,
      discoveryState,
      first: AUTHORITY_FRONTIER_PAGE_SIZE,
      after: null,
    },
  },
  result: {
    data: {
      authorityFrontier: {
        pageInfo: { hasNextPage: false, endCursor: null },
        edges: rows,
      },
    },
  },
});

// Mount via the imported wrapper (Playwright CT can only mount imported
// components; the wrapper sets the superuser reactive var in the browser and
// provides the Apollo mocks + router).
const mountMonitor = (mount: any, mocks: any[], superuser = true) =>
  mount(
    <AuthoritySourcesMonitorTestWrapper mocks={mocks} superuser={superuser} />
  );

test.describe("AuthoritySourcesMonitor", () => {
  test("renders the state chips and frontier rows for a superuser", async ({
    mount,
    page,
  }) => {
    const component = await mountMonitor(mount, [
      statsMock(STATS),
      statsMock(STATS),
      frontierMock(ALL_ROWS),
      frontierMock(ALL_ROWS),
    ]);

    await expect(
      page.locator('[data-testid="authority-sources-monitor"]')
    ).toBeVisible({ timeout: 10000 });

    // Chips: an "All" with the total + one per present state with its count.
    await expect(
      page.locator('[data-testid="authorities-chip-all"]')
    ).toContainText("4");
    await expect(
      page.locator('[data-testid="authorities-chip-failed"]')
    ).toContainText("Failed");
    await expect(
      page.locator('[data-testid="authorities-chip-queued"]')
    ).toContainText("2");

    // All four rows render, with the citation key + a state badge.
    await expect(page.locator('[data-testid="authorities-row"]')).toHaveCount(
      4
    );
    const table = page.locator('[data-testid="authorities-table-scroll"]');
    await expect(table.getByText("usc-15:78j")).toBeVisible();
    await expect(table.getByText("U.S. — DE").first()).toBeVisible();
    await expect(
      table.getByText("No source found for cfr-17:240.10b")
    ).toBeVisible();

    await docScreenshot(page, "authorities--sources-monitor--with-data");

    await component.unmount();
  });

  test("clicking a state chip filters the table server-side", async ({
    mount,
    page,
  }) => {
    const component = await mountMonitor(mount, [
      statsMock(STATS),
      statsMock(STATS),
      frontierMock(ALL_ROWS),
      // Refetch when the "failed" chip is clicked (discoveryState=failed).
      frontierMock([ALL_ROWS[1]], "failed"),
    ]);

    await expect(page.locator('[data-testid="authorities-row"]')).toHaveCount(
      4,
      { timeout: 10000 }
    );

    await page.locator('[data-testid="authorities-chip-failed"]').click();

    await expect(page.locator('[data-testid="authorities-row"]')).toHaveCount(
      1
    );
    await expect(
      page
        .locator('[data-testid="authorities-table-scroll"]')
        .getByText("cfr-17:240.10b", { exact: true })
    ).toBeVisible();

    await component.unmount();
  });

  test("a non-superuser is shown Access Denied, not the table", async ({
    mount,
    page,
  }) => {
    const component = await mountMonitor(mount, [], false);

    await expect(page.getByText("Access Denied")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator('[data-testid="authorities-state-chips"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("shows a guidance empty state when the frontier is empty", async ({
    mount,
    page,
  }) => {
    const component = await mountMonitor(mount, [
      statsMock({ totalCount: 0, byState: [] }),
      statsMock({ totalCount: 0, byState: [] }),
      frontierMock([]),
      frontierMock([]),
    ]);

    await expect(page.getByText("No authority sources")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-testid="authorities-row"]')).toHaveCount(
      0
    );

    await component.unmount();
  });
});
