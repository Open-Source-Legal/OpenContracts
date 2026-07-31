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
  GET_AUTHORITY_KEY_EQUIVALENCES,
  GET_AUTHORITY_MAPPING_STATS,
  GET_AUTHORITY_FRONTIER,
  GET_AUTHORITY_FRONTIER_STATS,
  GET_AUTHORITY_SOURCE_PROVIDERS,
} from "../src/graphql/queries";
import {
  CREATE_AUTHORITY_KEY_EQUIVALENCE,
  CREATE_AUTHORITY_NAMESPACE,
} from "../src/graphql/mutations";
import { REGISTRY_PAGE_SIZE } from "../src/components/admin/authority/shared/authorityVocab";
import {
  AUTHORITY_MAPPINGS_PAGE_SIZE,
  AUTHORITY_FRONTIER_PAGE_SIZE,
} from "../src/assets/configurations/constants";
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
    // Tab rail includes the server-discovered authority-pack catalog alongside
    // every existing console section.
    await expect(
      page.locator('[data-testid="authority-tab-packs"]')
    ).toBeVisible();
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
    await expect(page.locator('[data-testid="detail-equiv-row"]')).toHaveCount(
      1
    );
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

  test("the Registry create form submits a new authority", async ({
    mount,
    page,
  }) => {
    const createMock = {
      request: {
        query: CREATE_AUTHORITY_NAMESPACE,
        variables: {
          prefix: "ca-corp",
          displayName: "California Corporations Code",
          jurisdiction: "us-ca",
          authorityType: null,
          aliases: ["cal. corp. code"],
          isGlobal: true,
        },
      },
      result: {
        data: {
          createAuthorityNamespace: {
            ok: true,
            message: "SUCCESS",
            obj: nsNode({
              prefix: "ca-corp",
              displayName: "California Corporations Code",
              jurisdiction: "us-ca",
              authorityType: "statute",
              source: "manual",
              aliases: ["cal. corp. code"],
              createdByUsername: "admin",
            }).node,
          },
        },
      },
    };

    const component = await mountConsole(
      mount,
      [
        // mount fires stats + list (network-only) twice; create succeeds, then
        // refetchAll + the navigate-to-detail fire the extra stats/list + detail.
        statsMock(),
        statsMock(),
        statsMock(),
        listMock(),
        listMock(),
        listMock(),
        createMock,
        detailMock("ca-corp"),
      ],
      true,
      "/admin/authority/registry"
    );

    await expect(
      page.locator('[data-testid="authority-registry-tab"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="registry-new-toggle"]').click();
    await page.locator('[data-testid="registry-new-prefix"]').fill("ca-corp");
    await page
      .locator('[data-testid="registry-new-name"]')
      .fill("California Corporations Code");
    await page
      .locator('[data-testid="registry-new-jurisdiction"]')
      .fill("us-ca");
    await page
      .locator('[data-testid="registry-new-aliases"]')
      .fill("cal. corp. code");
    await page.locator('[data-testid="registry-create-submit"]').click();

    await expect(page.getByText("Authority created.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  // ---- Aliases & Relationships tab (absorbed AuthorityMappings) ----------- //

  const MAPPING_STATS = {
    totalCount: 2,
    bySource: [
      { source: "manual", count: 1 },
      { source: "baseline", count: 1 },
    ],
  };

  const equivNode = (over: Record<string, unknown>) => ({
    node: {
      id: `KE:${over.fromKey}`,
      fromKey: "x",
      toKey: "y",
      source: "baseline",
      confidence: null,
      note: null,
      created: "2026-06-01T00:00:00Z",
      modified: "2026-06-01T00:00:00Z",
      editable: false,
      createdByUsername: null,
      ...over,
    },
  });

  const EQUIV_ROWS = [
    equivNode({
      fromKey: "securities-act:5",
      toKey: "usc-15:77e",
      source: "manual",
      editable: true,
      createdByUsername: "admin",
    }),
    equivNode({ fromKey: "irc:501", toKey: "usc-26:501", source: "baseline" }),
  ];

  const mappingStatsMock = () => ({
    request: {
      query: GET_AUTHORITY_MAPPING_STATS,
      variables: { search: null },
    },
    result: { data: { authorityMappingStats: MAPPING_STATS } },
  });

  const equivListMock = () => ({
    request: {
      query: GET_AUTHORITY_KEY_EQUIVALENCES,
      variables: {
        source: null,
        search: null,
        first: AUTHORITY_MAPPINGS_PAGE_SIZE,
        after: null,
      },
    },
    result: {
      data: {
        authorityKeyEquivalences: {
          pageInfo: { hasNextPage: false, endCursor: null },
          edges: EQUIV_ROWS,
        },
      },
    },
  });

  test("the Aliases & Relationships tab renders chips, rows, and manual-only edit", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        mappingStatsMock(),
        mappingStatsMock(),
        equivListMock(),
        equivListMock(),
      ],
      true,
      "/admin/authority/mappings"
    );

    await expect(
      page.locator('[data-testid="authority-mappings-tab"]')
    ).toBeVisible({ timeout: 15000 });
    await expect(
      page.locator('[data-testid="mappings-source-chip-manual"]')
    ).toContainText("Manual");
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(2);
    // Only the manual row exposes edit; the baseline row is read-only.
    await expect(page.locator('[data-testid="mappings-edit"]')).toHaveCount(1);
    await expect(
      page.locator('[data-testid="mappings-create-form"]')
    ).toBeVisible();

    await docScreenshot(page, "authorities--console-mappings--with-data");

    await component.unmount();
  });

  test("the Aliases & Relationships tab create form submits a new bridge", async ({
    mount,
    page,
  }) => {
    const createMock = {
      request: {
        query: CREATE_AUTHORITY_KEY_EQUIVALENCE,
        variables: {
          fromKey: "investment-advisers-act:206",
          toKey: "usc-15:80b-6",
          note: null,
        },
      },
      result: {
        data: {
          createAuthorityKeyEquivalence: {
            ok: true,
            message: "Mapping created.",
            obj: {
              id: "KE:new",
              fromKey: "investment-advisers-act:206",
              toKey: "usc-15:80b-6",
              source: "manual",
              confidence: null,
              note: null,
              editable: true,
              createdByUsername: "admin",
              modified: "2026-06-18T00:00:00Z",
            },
          },
        },
      },
    };

    const component = await mountConsole(
      mount,
      [
        { ...mappingStatsMock(), maxUsageCount: 20 },
        { ...mappingStatsMock(), maxUsageCount: 20 },
        { ...equivListMock(), maxUsageCount: 20 },
        { ...equivListMock(), maxUsageCount: 20 },
        createMock,
      ],
      true,
      "/admin/authority/mappings"
    );

    await expect(
      page.locator('[data-testid="mappings-create-form"]')
    ).toBeVisible({ timeout: 15000 });
    await page
      .locator('[data-testid="mappings-new-from"]')
      .fill("investment-advisers-act:206");
    await page.locator('[data-testid="mappings-new-to"]').fill("usc-15:80b-6");
    await page.locator('[data-testid="mappings-create-submit"]').click();

    await expect(page.getByText("Mapping created.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  // ---- Discovery Queue tab (absorbed AuthoritySourcesMonitor) ------------- //

  const FRONTIER_STATS = {
    totalCount: 2,
    byState: [
      { state: "queued", count: 1 },
      { state: "pending_approval", count: 1 },
    ],
  };

  const frontierNode = (over: Record<string, unknown>) => ({
    node: {
      id: `AF:${over.canonicalKey}`,
      canonicalKey: "x:1",
      authority: "x",
      jurisdiction: null,
      authorityType: null,
      discoveryState: "queued",
      provider: null,
      ingestable: true,
      predictedProvider: null,
      mentionCount: 1,
      distinctCorpusCount: 1,
      depth: 0,
      lastError: null,
      lastAttempt: null,
      ingestedDocument: null,
      ...over,
    },
  });

  const FRONTIER_ROWS = [
    frontierNode({
      canonicalKey: "usc-15:78j",
      authority: "usc-15",
      discoveryState: "queued",
      mentionCount: 9,
    }),
    frontierNode({
      canonicalKey: "dgcl:145",
      authority: "dgcl",
      discoveryState: "pending_approval",
      mentionCount: 4,
    }),
  ];

  const frontierStatsMock = () => ({
    request: {
      query: GET_AUTHORITY_FRONTIER_STATS,
      variables: {
        jurisdiction: null,
        authorityType: null,
        provider: null,
        search: null,
      },
    },
    result: { data: { authorityFrontierStats: FRONTIER_STATS } },
  });

  const frontierListMock = () => ({
    request: {
      query: GET_AUTHORITY_FRONTIER,
      variables: {
        discoveryState: null,
        jurisdiction: null,
        authorityType: null,
        provider: null,
        search: null,
        first: AUTHORITY_FRONTIER_PAGE_SIZE,
        after: null,
      },
    },
    result: {
      data: {
        authorityFrontier: {
          pageInfo: { hasNextPage: false, endCursor: null },
          edges: FRONTIER_ROWS,
        },
      },
    },
  });

  test("the Discovery Queue tab renders state chips, rows, and per-row verbs", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        frontierStatsMock(),
        frontierStatsMock(),
        frontierListMock(),
        frontierListMock(),
        // The tab now fetches the provider registry to seed the filter + validate
        // reroute client-side (so a typo fails without a round-trip).
        providersMock(),
      ],
      true,
      "/admin/authority/queue"
    );

    await expect(
      page.locator('[data-testid="authority-queue-tab"]')
    ).toBeVisible({ timeout: 15000 });
    await expect(
      page.locator('[data-testid="queue-state-chip-queued"]')
    ).toContainText("Queued");
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2);
    // Per-row admin verbs are present; Approve only on the pending_approval row.
    await expect(page.locator('[data-testid="queue-requeue"]')).toHaveCount(2);
    await expect(page.locator('[data-testid="queue-approve"]')).toHaveCount(1);

    // Selecting a row reveals the Run-discovery action bar.
    await page.locator('[data-testid="queue-select-usc-15:78j"]').click();
    await expect(
      page.locator('[data-testid="queue-run-selected"]')
    ).toBeVisible();

    await docScreenshot(page, "authorities--console-queue--with-data");

    await component.unmount();
  });

  // ---- Scrapers tab (the provider registry, net-new visibility) ---------- //

  const providersMock = () => ({
    request: { query: GET_AUTHORITY_SOURCE_PROVIDERS },
    result: {
      data: {
        authoritySourceProviders: [
          {
            name: "USCodeAuthoritySourceProvider",
            className:
              "opencontractserver.pipeline.authority_source_providers.us_code_provider.USCodeAuthoritySourceProvider",
            title: "United States Code",
            supportedPrefixes: ["usc-15", "usc-26"],
            license: "public-domain",
            priority: 100,
            requiresApproval: false,
            enabled: true,
            hasCredentials: false,
          },
          {
            name: "AgenticWebLocatorProvider",
            className: "x.AgenticWebLocatorProvider",
            title: "Agentic Web Locator",
            supportedPrefixes: [],
            license: "public-domain",
            priority: 9999,
            requiresApproval: true,
            enabled: false,
            hasCredentials: false,
          },
        ],
      },
    },
  });

  test("the Scrapers tab lists the registered source providers", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [providersMock(), providersMock()],
      true,
      "/admin/authority/scrapers"
    );

    await expect(
      page.locator('[data-testid="authority-scrapers-tab"]')
    ).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="scrapers-row"]')).toHaveCount(2);
    const table = page.locator('[data-testid="scrapers-table-scroll"]');
    await expect(table.getByText("United States Code")).toBeVisible();
    // The opt-in agentic provider shows Disabled + Needs approval.
    await expect(table.getByText("Disabled")).toBeVisible();
    await expect(table.getByText("Needs approval")).toBeVisible();

    await docScreenshot(page, "authorities--console-scrapers--with-data");

    await component.unmount();
  });

  // ---- Runs tab (absorbed AdminEnrichment) ------------------------------- //

  test("the Runs tab renders the corpus picker", async ({ mount, page }) => {
    const component = await mountConsole(
      mount,
      [],
      true,
      "/admin/authority/runs"
    );

    await expect(
      page.locator('[data-testid="authority-runs-tab"]')
    ).toBeVisible({ timeout: 15000 });
    // The runs tab is the absorbed enrichment runner: a corpus picker gates it
    // (the runner + job list mount once a corpus is chosen).
    await expect(page.getByText("Corpus", { exact: true })).toBeVisible();

    await component.unmount();
  });
});
