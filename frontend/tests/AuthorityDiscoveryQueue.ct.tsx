/**
 * Interaction tests for the Discovery Queue tab — the per-row admin verbs
 * (requeue / reset / approve / reroute / delete), the multi-select Run-discovery
 * and bulk-delete action bar, the provider/search/state filters, "load more"
 * pagination, and the empty / error states. The existing AuthorityConsole.ct.tsx
 * only asserts the tab RENDERS; this drives the mutation handlers (runVerb and
 * friends) that were otherwise uncovered.
 *
 * The repeating stats / list / providers queries carry a finite ``maxUsageCount``
 * so mount + every post-verb ``refetchAll`` reuses one mock (a function
 * ``variableMatcher`` cannot cross the CT Node↔browser boundary, so we key on the
 * explicit variables instead).
 *
 * NOTE: the JSX-component (wrapper) import is kept in its OWN import statement,
 * per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityConsoleTestWrapper } from "./AuthorityConsoleTestWrapper";
import {
  GET_AUTHORITY_FRONTIER,
  GET_AUTHORITY_FRONTIER_STATS,
  GET_AUTHORITY_SOURCE_PROVIDERS,
} from "../src/graphql/queries";
import {
  APPROVE_AUTHORITY_FRONTIER,
  DELETE_AUTHORITY_FRONTIER,
  REQUEUE_AUTHORITY_FRONTIER,
  RESET_AUTHORITY_FRONTIER,
  REROUTE_AUTHORITY_FRONTIER,
  RUN_AUTHORITY_DISCOVERY,
} from "../src/graphql/mutations";
import { AUTHORITY_FRONTIER_PAGE_SIZE } from "../src/assets/configurations/constants";

const QUEUE_PATH = "/admin/authority/queue";

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

const ROWS = [
  frontierNode({
    canonicalKey: "usc-15:78j",
    authority: "usc-15",
    discoveryState: "queued",
    mentionCount: 9,
    lastError:
      "boom: a long error message that should be truncated in the cell",
  }),
  frontierNode({
    canonicalKey: "dgcl:145",
    authority: "dgcl",
    discoveryState: "pending_approval",
    mentionCount: 4,
  }),
];

const statsMock = (
  over: Record<string, unknown> = {},
  stats = FRONTIER_STATS
) => ({
  request: {
    query: GET_AUTHORITY_FRONTIER_STATS,
    variables: {
      jurisdiction: null,
      authorityType: null,
      provider: null,
      search: null,
      ...over,
    },
  },
  result: { data: { authorityFrontierStats: stats } },
  maxUsageCount: 20,
});

const listMock = (
  over: Record<string, unknown> = {},
  edges = ROWS,
  hasNextPage = false,
  endCursor: string | null = null
) => ({
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
      ...over,
    },
  },
  result: {
    data: {
      authorityFrontier: {
        pageInfo: { hasNextPage, endCursor },
        edges,
      },
    },
  },
  maxUsageCount: 20,
});

const PROVIDERS = [
  {
    name: "USCodeAuthoritySourceProvider",
    className: "x.USCodeAuthoritySourceProvider",
    title: "United States Code",
    supportedPrefixes: ["usc-15", "usc-26"],
    license: "public-domain",
    priority: 100,
    requiresApproval: false,
    enabled: true,
    hasCredentials: false,
  },
];
const providersMock = () => ({
  request: { query: GET_AUTHORITY_SOURCE_PROVIDERS },
  result: { data: { authoritySourceProviders: PROVIDERS } },
  maxUsageCount: 20,
});

const verbMock = (mutation: any, field: string, variables: any, ok = true) => ({
  request: { query: mutation, variables },
  result: {
    data: { [field]: { ok, message: ok ? "SUCCESS" : "nope", obj: null } },
  },
});

const mount_ = (mount: any, mocks: any[]) =>
  mount(
    <AuthorityConsoleTestWrapper
      mocks={mocks}
      superuser={true}
      initialPath={QUEUE_PATH}
    />
  );

const allowDialogs = (page: any, promptValue = "") =>
  page.evaluate((v: string) => {
    (window as any).confirm = () => true;
    (window as any).prompt = () => v;
  }, promptValue);

const base = () => [statsMock(), listMock(), providersMock()];

test.describe("DiscoveryQueueTab interactions", () => {
  test("runs the requeue / reset / approve / reroute per-row verbs", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      ...base(),
      verbMock(REQUEUE_AUTHORITY_FRONTIER, "requeueAuthorityFrontier", {
        id: "AF:usc-15:78j",
      }),
      verbMock(RESET_AUTHORITY_FRONTIER, "resetAuthorityFrontier", {
        id: "AF:usc-15:78j",
      }),
      verbMock(APPROVE_AUTHORITY_FRONTIER, "approveAuthorityFrontier", {
        id: "AF:dgcl:145",
      }),
      verbMock(REROUTE_AUTHORITY_FRONTIER, "rerouteAuthorityFrontier", {
        id: "AF:usc-15:78j",
        provider: "USCodeAuthoritySourceProvider",
      }),
    ]);

    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await allowDialogs(page, "USCodeAuthoritySourceProvider");

    await page.locator('[data-testid="queue-requeue"]').first().click();
    await expect(page.getByText("Requeued")).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="queue-reset"]').first().click();
    await expect(page.getByText("Reset", { exact: true })).toBeVisible({
      timeout: 10000,
    });

    // Approve is only on the pending_approval row.
    await page.locator('[data-testid="queue-approve"]').first().click();
    await expect(page.getByText("Approved")).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="queue-reroute"]').first().click();
    await expect(page.getByText("Rerouted")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("reroute validates the provider against the registry (cancel + typo)", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, base());
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });

    // Cancel: prompt returns "" -> handler returns early, no mutation/toast.
    await allowDialogs(page, "");
    await page.locator('[data-testid="queue-reroute"]').first().click();

    // Typo: prompt returns an unknown provider -> client-side rejection toast.
    await allowDialogs(page, "NotAProvider");
    await page.locator('[data-testid="queue-reroute"]').first().click();
    await expect(page.getByText(/Unknown provider/)).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("deletes a single row after confirmation", async ({ mount, page }) => {
    const component = await mount_(mount, [
      ...base(),
      verbMock(DELETE_AUTHORITY_FRONTIER, "deleteAuthorityFrontier", {
        ids: ["AF:usc-15:78j"],
      }),
    ]);
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await allowDialogs(page);
    await page.locator('[data-testid="queue-delete"]').first().click();
    await expect(page.getByText("Deleted")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("surfaces a verb error when the mutation returns ok:false", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      ...base(),
      verbMock(
        REQUEUE_AUTHORITY_FRONTIER,
        "requeueAuthorityFrontier",
        { id: "AF:usc-15:78j" },
        false
      ),
    ]);
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await page.locator('[data-testid="queue-requeue"]').first().click();
    await expect(page.getByText("nope")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("selects rows and runs discovery, then bulk-deletes", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      ...base(),
      {
        request: {
          query: RUN_AUTHORITY_DISCOVERY,
          variables: { frontierIds: ["AF:usc-15:78j", "AF:dgcl:145"] },
        },
        result: {
          data: {
            runAuthorityDiscovery: {
              ok: true,
              message: "Discovery started on 2.",
              count: 2,
            },
          },
        },
      },
      {
        request: {
          query: DELETE_AUTHORITY_FRONTIER,
          variables: { ids: ["AF:usc-15:78j"] },
        },
        result: {
          data: {
            deleteAuthorityFrontier: { ok: true, message: "Deleted", count: 1 },
          },
        },
      },
    ]);

    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await allowDialogs(page);

    await page.locator('[data-testid="queue-select-usc-15:78j"]').click();
    await page.locator('[data-testid="queue-select-dgcl:145"]').click();
    await expect(
      page.locator('[data-testid="queue-selected-count"]')
    ).toContainText("2");
    await page.locator('[data-testid="queue-run-selected"]').click();
    await expect(page.getByText("Discovery started on 2.")).toBeVisible({
      timeout: 10000,
    });

    // Selection cleared after a run; pick one row and bulk-delete it.
    await page.locator('[data-testid="queue-select-usc-15:78j"]').click();
    await page.locator('[data-testid="queue-delete-selected"]').click();
    await expect(page.getByText("Deleted")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("clears a selection without acting", async ({ mount, page }) => {
    const component = await mount_(mount, base());
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });
    await page.locator('[data-testid="queue-select-usc-15:78j"]').click();
    await expect(
      page.locator('[data-testid="queue-action-bar"]')
    ).toBeVisible();
    await page.locator('[data-testid="queue-clear-selection"]').click();
    await expect(page.locator('[data-testid="queue-action-bar"]')).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("filters by state chip, provider, and search", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      ...base(),
      // state chip -> list re-queries with discoveryState (stats unchanged).
      listMock({ discoveryState: "queued" }, [ROWS[0]]),
      // provider select -> both stats + list re-query with provider.
      statsMock({ provider: "USCodeAuthoritySourceProvider" }),
      listMock({ provider: "USCodeAuthoritySourceProvider" }, [ROWS[0]]),
      // search -> both re-query with the trimmed term (provider stays applied).
      statsMock({ provider: "USCodeAuthoritySourceProvider", search: "78j" }),
      listMock({ provider: "USCodeAuthoritySourceProvider", search: "78j" }, [
        ROWS[0],
      ]),
    ]);

    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2, {
      timeout: 15000,
    });

    // Toggle the "queued" state chip on (covers FacetedStatsChips onSelect).
    await page.locator('[data-testid="queue-state-chip-queued"]').click();
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(1);

    // Toggle it back off (active === value -> null).
    await page.locator('[data-testid="queue-state-chip-queued"]').click();
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2);

    await page
      .locator('[data-testid="queue-filter-provider"]')
      .selectOption("USCodeAuthoritySourceProvider");
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(1);

    await page.locator('[data-testid="queue-search"]').fill("78j");
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(1);

    await component.unmount();
  });

  test("paginates with load more", async ({ mount, page }) => {
    const component = await mount_(mount, [
      statsMock(),
      listMock({}, [ROWS[0]], true, "CURSOR1"),
      providersMock(),
      // fetchMore page 2 (after the first cursor).
      listMock({ after: "CURSOR1" }, [ROWS[1]], false, null),
    ]);

    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(1, {
      timeout: 15000,
    });
    await page.locator('[data-testid="queue-load-more"]').click();
    await expect(page.locator('[data-testid="queue-row"]')).toHaveCount(2);

    await component.unmount();
  });

  test("renders the empty state when no rows match", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      statsMock({}, { totalCount: 0, byState: [] }),
      listMock({}, []),
      providersMock(),
    ]);
    await expect(page.getByText("No frontier rows")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });

  test("renders an error state when the list query fails", async ({
    mount,
    page,
  }) => {
    const component = await mount_(mount, [
      statsMock(),
      {
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
        error: new Error("frontier boom"),
        maxUsageCount: 20,
      },
      providersMock(),
    ]);
    await expect(page.getByText("Error loading discovery queue")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });
});
