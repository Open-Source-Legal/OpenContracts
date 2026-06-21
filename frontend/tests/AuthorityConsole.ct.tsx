/**
 * Component tests for the unified Authority Console — the superuser-only
 * /admin/authority front door. Verifies the authority-admin gate, the Registry
 * tab (scope chips + namespace table), navigation into the single-authority
 * detail view (header + aliases + joined relationships/discovery/references),
 * and the tab rail.
 *
 * NOTE: the JSX-component import is kept in its own ``import`` statement,
 * separate from helper/query imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityConsoleTestWrapper } from "./AuthorityConsoleTestWrapper";
import {
  GET_AUTHORITY_NAMESPACES,
  GET_AUTHORITY_NAMESPACE_STATS,
  GET_AUTHORITY_NAMESPACE_DETAIL,
} from "../src/graphql/queries";
import { REGISTRY_PAGE_SIZE } from "../src/components/admin/authority/shared/authorityVocab";
import { docScreenshot } from "./utils/docScreenshot";

const STATS = {
  totalCount: 3,
  byJurisdiction: [
    { value: "us-federal", count: 2 },
    { value: "us-de", count: 1 },
  ],
  byAuthorityType: [
    { value: "statute", count: 2 },
    { value: "regulation", count: 1 },
  ],
  byScope: [
    { value: "global", count: 3 },
    { value: "corpus", count: 0 },
  ],
};

const nsNode = (over: Record<string, unknown>) => ({
  node: {
    id: `NS:${over.prefix}`,
    prefix: "x",
    displayName: "X",
    jurisdiction: null,
    authorityType: null,
    scope: "global",
    source: "baseline",
    aliases: [],
    provider: null,
    sourceRootUrl: null,
    license: null,
    isGlobal: true,
    effectiveProvider: null,
    equivalenceCount: 0,
    frontierCount: 0,
    referenceCount: 0,
    createdByUsername: null,
    created: "2026-06-01T00:00:00Z",
    modified: "2026-06-01T00:00:00Z",
    authorityCorpus: null,
    ...over,
  },
});

const ROWS = [
  nsNode({
    prefix: "usc-15",
    displayName: "United States Code, Title 15",
    jurisdiction: "us-federal",
    authorityType: "statute",
    aliases: ["15 u.s.c.", "securities act"],
    referenceCount: 42,
  }),
  nsNode({
    prefix: "dgcl",
    displayName: "Delaware General Corporation Law",
    jurisdiction: "us-de",
    authorityType: "statute",
    aliases: ["dgcl"],
    source: "manual",
    referenceCount: 7,
  }),
  nsNode({
    prefix: "cfr-17",
    displayName: "Code of Federal Regulations, Title 17",
    jurisdiction: "us-federal",
    authorityType: "regulation",
    referenceCount: 3,
  }),
];

const statsMock = () => ({
  request: {
    query: GET_AUTHORITY_NAMESPACE_STATS,
    variables: { search: null },
  },
  result: { data: { authorityNamespaceStats: STATS } },
});

const listMock = (scope: string | null = null) => ({
  request: {
    query: GET_AUTHORITY_NAMESPACES,
    variables: {
      jurisdiction: null,
      authorityType: null,
      scope,
      search: null,
      first: REGISTRY_PAGE_SIZE,
      after: null,
    },
  },
  result: {
    data: {
      authorityNamespaces: {
        pageInfo: { hasNextPage: false, endCursor: null },
        edges: ROWS,
      },
    },
  },
});

const DETAIL = {
  namespace: ROWS[0].node,
  equivalencesOut: [
    {
      id: "KE:1",
      fromKey: "usc-15:78j",
      toKey: "exchange-act:10",
      source: "baseline",
      note: null,
      editable: false,
      createdByUsername: null,
      modified: "2026-06-01T00:00:00Z",
    },
  ],
  equivalencesIn: [],
  frontierRows: [
    {
      id: "AF:1",
      canonicalKey: "usc-15:78j",
      discoveryState: "ingested",
      mentionCount: 12,
      depth: 0,
      provider: "USCodeAuthoritySourceProvider",
      lastError: null,
      ingestedDocument: { id: "D:1", title: "15 USC 78j" },
    },
  ],
  frontierStateCounts: [{ state: "ingested", count: 1 }],
  referenceTotal: 42,
  referenceStatusCounts: [
    { status: "RESOLVED", count: 30 },
    { status: "EXTERNAL", count: 12 },
  ],
  referenceSample: [],
  effectiveProvider: "USCodeAuthoritySourceProvider",
};

const detailMock = (prefix: string) => ({
  request: {
    query: GET_AUTHORITY_NAMESPACE_DETAIL,
    variables: { prefix },
  },
  result: { data: { authorityNamespaceDetail: DETAIL } },
});

const mountConsole = (
  mount: any,
  mocks: any[],
  superuser = true,
  initialPath = "/admin/authority/registry"
) =>
  mount(
    <AuthorityConsoleTestWrapper
      mocks={mocks}
      superuser={superuser}
      initialPath={initialPath}
    />
  );

test.describe("AuthorityConsole", () => {
  test("renders the registry tab with scope chips and namespace rows", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(mount, [
      statsMock(),
      statsMock(),
      listMock(),
      listMock(),
    ]);

    await expect(page.locator('[data-testid="authority-console"]')).toBeVisible(
      {
        timeout: 15000,
      }
    );
    // Tab rail present with the five sections.
    await expect(
      page.locator('[data-testid="authority-tab-registry"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="authority-tab-mappings"]')
    ).toBeVisible();

    // Scope chips + all three namespace rows.
    await expect(
      page.locator('[data-testid="registry-scope-chip-all"]')
    ).toContainText("3");
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(3);
    const table = page.locator('[data-testid="registry-table-scroll"]');
    await expect(
      table.getByText("Delaware General Corporation Law")
    ).toBeVisible();

    await docScreenshot(page, "authorities--console-registry--with-data");

    await component.unmount();
  });

  test("clicking an authority opens its detail view", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(mount, [
      statsMock(),
      statsMock(),
      listMock(),
      listMock(),
      detailMock("usc-15"),
      detailMock("usc-15"),
    ]);

    await expect(
      page.locator('[data-testid="registry-open-usc-15"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="registry-open-usc-15"]').click();

    // Detail view takes over the tab.
    await expect(page.locator('[data-testid="authority-detail"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="detail-title"]')).toContainText(
      "United States Code, Title 15"
    );
    // Aliases joined onto the namespace render as editable chips.
    await expect(
      page.locator('[data-testid="detail-alias-securities act"]')
    ).toBeVisible();
    // Relationships + discovery sections render their joined rows.
    await expect(
      page.locator('[data-testid="detail-equivalence-row"]')
    ).toHaveCount(1);
    await expect(
      page.locator('[data-testid="detail-frontier-row"]')
    ).toHaveCount(1);
    // Effective routing provider surfaced next to the advisory column.
    await expect(
      page.locator('[data-testid="detail-effective-provider"]')
    ).toContainText("USCodeAuthoritySourceProvider");

    await docScreenshot(page, "authorities--console-detail--with-data");

    await component.unmount();
  });

  test("a non-admin is shown Access Denied, not the console", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(mount, [], false);

    await expect(page.getByText("Access Denied")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.locator('[data-testid="authority-registry-tab"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
