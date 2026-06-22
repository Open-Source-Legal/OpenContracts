/**
 * Interaction tests for the Authority Console tabs the happy-path
 * AuthorityConsole.ct.tsx only RENDERS: the Registry facets / search / load-more
 * / create-error, the Aliases & Relationships (mappings) edit / delete / filter /
 * load-more, the Scrapers empty + error states, and the console shell's tab
 * navigation + back link + detail close. These drive the filter setters, the
 * relay ``loadMore`` merge, and the mutation handlers that were otherwise
 * uncovered.
 *
 * Repeating list/stats queries carry a finite ``maxUsageCount`` so mount + each
 * ``refetchAll`` reuses one mock; filter-changed queries are keyed to their new
 * variables.
 *
 * NOTE: the JSX-component (wrapper) import is kept in its OWN import statement,
 * per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityConsoleTestWrapper } from "./AuthorityConsoleTestWrapper";
import {
  GET_AUTHORITY_KEY_EQUIVALENCES,
  GET_AUTHORITY_MAPPING_STATS,
  GET_AUTHORITY_NAMESPACES,
  GET_AUTHORITY_NAMESPACE_STATS,
  GET_AUTHORITY_NAMESPACE_DETAIL,
  GET_AUTHORITY_SOURCE_PROVIDERS,
} from "../src/graphql/queries";
import {
  CREATE_AUTHORITY_NAMESPACE,
  DELETE_AUTHORITY_KEY_EQUIVALENCE,
  UPDATE_AUTHORITY_KEY_EQUIVALENCE,
} from "../src/graphql/mutations";
import { REGISTRY_PAGE_SIZE } from "../src/components/admin/authority/shared/authorityVocab";
import { AUTHORITY_MAPPINGS_PAGE_SIZE } from "../src/assets/configurations/constants";

/* -------------------------------------------------------------- registry ---- */

const NS_STATS = {
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

const NS_ROWS = [
  nsNode({
    prefix: "usc-15",
    displayName: "United States Code, Title 15",
    jurisdiction: "us-federal",
    authorityType: "statute",
    aliases: ["15 u.s.c."],
    referenceCount: 42,
  }),
  nsNode({
    prefix: "dgcl",
    displayName: "Delaware General Corporation Law",
    jurisdiction: "us-de",
    authorityType: "statute",
    source: "manual",
  }),
];

const nsStatsMock = (search: string | null = null) => ({
  request: { query: GET_AUTHORITY_NAMESPACE_STATS, variables: { search } },
  result: { data: { authorityNamespaceStats: NS_STATS } },
  maxUsageCount: 20,
});

const nsListMock = (
  over: Record<string, unknown> = {},
  edges = NS_ROWS,
  hasNextPage = false,
  endCursor: string | null = null
) => ({
  request: {
    query: GET_AUTHORITY_NAMESPACES,
    variables: {
      jurisdiction: null,
      authorityType: null,
      scope: null,
      search: null,
      first: REGISTRY_PAGE_SIZE,
      after: null,
      ...over,
    },
  },
  result: {
    data: {
      authorityNamespaces: { pageInfo: { hasNextPage, endCursor }, edges },
    },
  },
  maxUsageCount: 20,
});

const mountConsole = (mount: any, mocks: any[], initialPath: string) =>
  mount(
    <AuthorityConsoleTestWrapper
      mocks={mocks}
      superuser={true}
      initialPath={initialPath}
    />
  );

const allowDialogs = (page: any) =>
  page.evaluate(() => {
    (window as any).confirm = () => true;
  });

test.describe("Registry tab interactions", () => {
  test("filters by scope chip, jurisdiction, type and search", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        nsStatsMock(),
        nsListMock(),
        // scope chip -> list re-queries with scope=global.
        nsListMock({ scope: "global" }, [NS_ROWS[0]]),
        // jurisdiction select (scope still applied).
        nsListMock({ scope: "global", jurisdiction: "us-federal" }, [
          NS_ROWS[0],
        ]),
        // type select.
        nsListMock(
          {
            scope: "global",
            jurisdiction: "us-federal",
            authorityType: "statute",
          },
          [NS_ROWS[0]]
        ),
        // search -> stats + list re-query.
        nsStatsMock("usc"),
        nsListMock(
          {
            scope: "global",
            jurisdiction: "us-federal",
            authorityType: "statute",
            search: "usc",
          },
          [NS_ROWS[0]]
        ),
      ],
      "/admin/authority/registry"
    );

    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(2, {
      timeout: 15000,
    });

    await page.locator('[data-testid="registry-scope-chip-global"]').click();
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1);

    await page
      .locator('[data-testid="registry-filter-jurisdiction"]')
      .selectOption("us-federal");
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1);

    await page
      .locator('[data-testid="registry-filter-type"]')
      .selectOption("statute");
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1);

    await page.locator('[data-testid="registry-search"]').fill("usc");
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1);
    // Clear the search (the X button) -> back to the broader result.
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1);

    await component.unmount();
  });

  test("paginates the registry with load more", async ({ mount, page }) => {
    const component = await mountConsole(
      mount,
      [
        nsStatsMock(),
        nsListMock({}, [NS_ROWS[0]], true, "RCUR"),
        nsListMock({ after: "RCUR" }, [NS_ROWS[1]], false, null),
      ],
      "/admin/authority/registry"
    );
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(1, {
      timeout: 15000,
    });
    await page.locator('[data-testid="registry-load-more"]').click();
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(2);

    await component.unmount();
  });

  test("surfaces a create error from the registry form", async ({
    mount,
    page,
  }) => {
    const createErrMock = {
      request: {
        query: CREATE_AUTHORITY_NAMESPACE,
        variables: {
          prefix: "bad-prefix",
          displayName: "Bad",
          jurisdiction: null,
          authorityType: null,
          aliases: [],
          isGlobal: true,
        },
      },
      result: {
        data: {
          createAuthorityNamespace: {
            ok: false,
            message: "Invalid prefix.",
            obj: null,
          },
        },
      },
    };
    const component = await mountConsole(
      mount,
      [nsStatsMock(), nsListMock(), createErrMock],
      "/admin/authority/registry"
    );
    await expect(
      page.locator('[data-testid="registry-new-toggle"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="registry-new-toggle"]').click();
    await page
      .locator('[data-testid="registry-new-prefix"]')
      .fill("bad-prefix");
    await page.locator('[data-testid="registry-new-name"]').fill("Bad");
    await page.locator('[data-testid="registry-create-submit"]').click();
    await expect(page.getByText("Invalid prefix.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});

/* -------------------------------------------------------------- mappings ---- */

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
  equivNode({ fromKey: "irc:501", toKey: "usc-26:501" }),
];

const mappingStatsMock = (search: string | null = null) => ({
  request: { query: GET_AUTHORITY_MAPPING_STATS, variables: { search } },
  result: { data: { authorityMappingStats: MAPPING_STATS } },
  maxUsageCount: 20,
});

const equivListMock = (
  over: Record<string, unknown> = {},
  edges = EQUIV_ROWS,
  hasNextPage = false,
  endCursor: string | null = null
) => ({
  request: {
    query: GET_AUTHORITY_KEY_EQUIVALENCES,
    variables: {
      source: null,
      search: null,
      first: AUTHORITY_MAPPINGS_PAGE_SIZE,
      after: null,
      ...over,
    },
  },
  result: {
    data: {
      authorityKeyEquivalences: { pageInfo: { hasNextPage, endCursor }, edges },
    },
  },
  maxUsageCount: 20,
});

test.describe("Mappings tab interactions", () => {
  test("edits a manual mapping and saves it", async ({ mount, page }) => {
    const updateMock = {
      request: {
        query: UPDATE_AUTHORITY_KEY_EQUIVALENCE,
        variables: {
          id: "KE:securities-act:5",
          fromKey: "securities-act:5",
          toKey: "usc-15:77e-1",
          note: null,
        },
      },
      result: {
        data: {
          updateAuthorityKeyEquivalence: {
            ok: true,
            message: "Mapping updated.",
            obj: null,
          },
        },
      },
    };
    const component = await mountConsole(
      mount,
      [mappingStatsMock(), equivListMock(), updateMock],
      "/admin/authority/mappings"
    );
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    // Only the manual row exposes edit.
    await page.locator('[data-testid="mappings-edit"]').click();
    await page.locator('[data-testid="mappings-edit-to"]').fill("usc-15:77e-1");
    await page.locator('[data-testid="mappings-save"]').click();
    await expect(page.getByText("Mapping updated.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("deletes a manual mapping after confirmation", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_AUTHORITY_KEY_EQUIVALENCE,
        variables: { id: "KE:securities-act:5" },
      },
      result: {
        data: {
          deleteAuthorityKeyEquivalence: {
            ok: true,
            message: "Mapping deleted.",
          },
        },
      },
    };
    const component = await mountConsole(
      mount,
      [mappingStatsMock(), equivListMock(), deleteMock],
      "/admin/authority/mappings"
    );
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await allowDialogs(page);
    await page.locator('[data-testid="mappings-delete"]').click();
    await expect(page.getByText("Mapping deleted.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("filters mappings by source chip, source select and search", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        mappingStatsMock(),
        equivListMock(),
        equivListMock({ source: "manual" }, [EQUIV_ROWS[0]]),
        equivListMock({ source: "baseline" }, [EQUIV_ROWS[1]]),
        mappingStatsMock("usc"),
        equivListMock({ source: "baseline", search: "usc" }, [EQUIV_ROWS[1]]),
      ],
      "/admin/authority/mappings"
    );
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    // Source chip "manual".
    await page.locator('[data-testid="mappings-source-chip-manual"]').click();
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(1);
    // Source select -> baseline.
    await page
      .locator('[data-testid="mappings-filter-source"]')
      .selectOption("baseline");
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(1);
    // Search.
    await page.locator('[data-testid="mappings-search"]').fill("usc");
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(1);

    await component.unmount();
  });

  test("paginates mappings with load more", async ({ mount, page }) => {
    const component = await mountConsole(
      mount,
      [
        mappingStatsMock(),
        equivListMock({}, [EQUIV_ROWS[0]], true, "MCUR"),
        equivListMock({ after: "MCUR" }, [EQUIV_ROWS[1]], false, null),
      ],
      "/admin/authority/mappings"
    );
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(1, {
      timeout: 15000,
    });
    await page.locator('[data-testid="mappings-load-more"]').click();
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(2);

    await component.unmount();
  });
});

/* -------------------------------------------------------------- scrapers ---- */

test.describe("Scrapers tab states", () => {
  test("renders the empty state when no providers are registered", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        {
          request: { query: GET_AUTHORITY_SOURCE_PROVIDERS },
          result: { data: { authoritySourceProviders: [] } },
          maxUsageCount: 20,
        },
      ],
      "/admin/authority/scrapers"
    );
    await expect(page.getByText("No source providers")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });

  test("renders an error state when the providers query fails", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        {
          request: { query: GET_AUTHORITY_SOURCE_PROVIDERS },
          error: new Error("providers boom"),
          maxUsageCount: 20,
        },
      ],
      "/admin/authority/scrapers"
    );
    await expect(page.getByText("Error loading source providers")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });
});

/* ------------------------------------------------------- console shell nav -- */

const DETAIL = {
  namespace: NS_ROWS[0].node,
  equivalencesOut: [],
  equivalencesIn: [],
  frontierRows: [],
  frontierStateCounts: [],
  referenceTotal: 0,
  referenceStatusCounts: [],
  referenceSample: [],
  effectiveProvider: null,
};

test.describe("Console shell navigation", () => {
  test("navigates between tabs and via the back link", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        nsStatsMock(),
        nsListMock(),
        mappingStatsMock(),
        equivListMock(),
        // Clicking "Back to Admin Settings" navigates to /admin/settings. In the
        // real app that is a *different route* that unmounts the console; the
        // isolated test wrapper keeps the console mounted, so it harmlessly
        // re-parses to the registry tab — this null detail keeps that quiet.
        {
          request: {
            query: GET_AUTHORITY_NAMESPACE_DETAIL,
            variables: { prefix: "settings" },
          },
          result: { data: { authorityNamespaceDetail: null } },
          maxUsageCount: 20,
        },
      ],
      "/admin/authority/registry"
    );
    await expect(page.locator('[data-testid="authority-console"]')).toBeVisible(
      {
        timeout: 15000,
      }
    );
    // Click the Aliases & Relationships tab -> MappingsTab renders.
    await page.locator('[data-testid="authority-tab-mappings"]').click();
    await expect(
      page.locator('[data-testid="authority-mappings-tab"]')
    ).toBeVisible({ timeout: 15000 });
    // Click back to the Authorities tab -> RegistryTab renders again.
    await page.locator('[data-testid="authority-tab-registry"]').click();
    await expect(
      page.locator('[data-testid="authority-registry-tab"]')
    ).toBeVisible({ timeout: 15000 });
    // The shell's single Back link fires navigate("/admin/settings"); the console
    // shell stays mounted in the harness, so just assert it did not crash.
    await page.locator('[data-testid="authority-console-back"]').click();
    await expect(
      page.locator('[data-testid="authority-console"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("closes an open authority detail back to the list", async ({
    mount,
    page,
  }) => {
    const component = await mountConsole(
      mount,
      [
        nsStatsMock(),
        nsListMock(),
        {
          request: {
            query: GET_AUTHORITY_NAMESPACE_DETAIL,
            variables: { prefix: "usc-15" },
          },
          result: { data: { authorityNamespaceDetail: DETAIL } },
          maxUsageCount: 20,
        },
      ],
      "/admin/authority/registry/usc-15"
    );
    await expect(page.locator('[data-testid="authority-detail"]')).toBeVisible({
      timeout: 15000,
    });
    await page.locator('[data-testid="detail-back"]').click();
    await expect(page.locator('[data-testid="registry-row"]')).toHaveCount(2, {
      timeout: 15000,
    });

    await component.unmount();
  });
});
