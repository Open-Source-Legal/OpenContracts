/**
 * Component tests for AuthorityMappings — the global, superuser-only
 * /admin/authority-mappings view over the authority key-equivalence table
 * (act-section ↔ USC/CFR canonical-key bridges). Verifies the superuser gate,
 * the per-source count chips + table render, the inline create form, chip-driven
 * source filtering, and the create mutation flow.
 *
 * NOTE: the JSX-component import is kept in its own ``import`` statement,
 * separate from helper/query imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityMappingsTestWrapper } from "./AuthorityMappingsTestWrapper";
import {
  GET_AUTHORITY_KEY_EQUIVALENCES,
  GET_AUTHORITY_MAPPING_STATS,
} from "../src/graphql/queries";
import { AUTHORITY_MAPPINGS_PAGE_SIZE } from "../src/assets/configurations/constants";
import { CREATE_AUTHORITY_KEY_EQUIVALENCE } from "../src/graphql/mutations";
import { docScreenshot } from "./utils/docScreenshot";

const STATS = {
  totalCount: 4,
  bySource: [
    { source: "manual", count: 1 },
    { source: "popular_name", count: 2 },
    { source: "baseline", count: 1 },
  ],
};

const node = (over: Record<string, unknown>) => ({
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

const ALL_ROWS = [
  node({
    fromKey: "securities-act:5",
    toKey: "usc-15:77e",
    source: "manual",
    note: "Securities Act § 5 → 15 U.S.C. § 77e",
    editable: true,
    createdByUsername: "admin",
  }),
  node({
    fromKey: "securities-exchange-act:10b",
    toKey: "usc-15:78j",
    source: "popular_name",
    note: "Popular-name table bridge",
  }),
  node({
    fromKey: "securities-exchange-act:14a",
    toKey: "usc-15:78n",
    source: "popular_name",
  }),
  node({
    fromKey: "investment-company-act:8",
    toKey: "usc-15:80a-8",
    source: "baseline",
  }),
];

const MANUAL_ROW = ALL_ROWS[0];

const statsMock = (stats: typeof STATS) => ({
  request: {
    query: GET_AUTHORITY_MAPPING_STATS,
    variables: { search: null },
  },
  result: { data: { authorityMappingStats: stats } },
});

const listMock = (
  rows: ReturnType<typeof node>[],
  source: string | null = null
) => ({
  request: {
    query: GET_AUTHORITY_KEY_EQUIVALENCES,
    variables: {
      source,
      search: null,
      first: AUTHORITY_MAPPINGS_PAGE_SIZE,
      after: null,
    },
  },
  result: {
    data: {
      authorityKeyEquivalences: {
        pageInfo: { hasNextPage: false, endCursor: null },
        edges: rows,
      },
    },
  },
});

// Mount via the imported wrapper (Playwright CT can only mount imported
// components; the wrapper sets the superuser reactive var in the browser and
// provides the Apollo mocks + router).
const mountPanel = (mount: any, mocks: any[], superuser = true) =>
  mount(<AuthorityMappingsTestWrapper mocks={mocks} superuser={superuser} />);

test.describe("AuthorityMappings", () => {
  test("renders the source chips and mapping rows for a superuser", async ({
    mount,
    page,
  }) => {
    const component = await mountPanel(mount, [
      statsMock(STATS),
      statsMock(STATS),
      listMock(ALL_ROWS),
      listMock(ALL_ROWS),
    ]);

    await expect(
      page.locator('[data-testid="authority-mappings-panel"]')
    ).toBeVisible({ timeout: 10000 });

    // Chips: an "All" with the total + one per present source with its count.
    await expect(
      page.locator('[data-testid="mappings-chip-all"]')
    ).toContainText("4");
    await expect(
      page.locator('[data-testid="mappings-chip-manual"]')
    ).toContainText("Manual");
    await expect(
      page.locator('[data-testid="mappings-chip-popular_name"]')
    ).toContainText("2");

    // All four rows render, with the from/to keys + a source badge.
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(4);
    const table = page.locator('[data-testid="mappings-table-scroll"]');
    await expect(table.getByText("securities-act:5")).toBeVisible();
    await expect(table.getByText("usc-15:77e")).toBeVisible();

    // The create form is present above the table.
    await expect(
      page.locator('[data-testid="mappings-create-form"]')
    ).toBeVisible();

    // Only the manual row exposes edit/delete; bundled rows say "read-only".
    await expect(page.locator('[data-testid="mappings-edit"]')).toHaveCount(1);
    await expect(table.getByText("read-only").first()).toBeVisible();

    await docScreenshot(page, "authorities--mappings-panel--with-data");

    await component.unmount();
  });

  test("clicking a source chip filters the table server-side", async ({
    mount,
    page,
  }) => {
    const component = await mountPanel(mount, [
      statsMock(STATS),
      statsMock(STATS),
      listMock(ALL_ROWS),
      // Refetch when the "manual" chip is clicked (source=manual).
      listMock([MANUAL_ROW], "manual"),
    ]);

    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(4, {
      timeout: 10000,
    });

    await page.locator('[data-testid="mappings-chip-manual"]').click();

    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(1);
    await expect(
      page
        .locator('[data-testid="mappings-table-scroll"]')
        .getByText("securities-act:5", { exact: true })
    ).toBeVisible();

    await component.unmount();
  });

  test("a non-superuser is shown Access Denied, not the table", async ({
    mount,
    page,
  }) => {
    const component = await mountPanel(mount, [], false);

    await expect(page.getByText("Access Denied")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator('[data-testid="mappings-source-chips"]')
    ).toHaveCount(0);
    await expect(
      page.locator('[data-testid="mappings-create-form"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("the inline create form is present and submits a new mapping", async ({
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
              id: "KE:investment-advisers-act:206",
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

    // maxUsageCount guards against the post-create refetch exhausting mocks.
    const component = await mountPanel(mount, [
      { ...statsMock(STATS), maxUsageCount: 20 },
      { ...statsMock(STATS), maxUsageCount: 20 },
      { ...listMock(ALL_ROWS), maxUsageCount: 20 },
      { ...listMock(ALL_ROWS), maxUsageCount: 20 },
      createMock,
    ]);

    await expect(
      page.locator('[data-testid="mappings-create-form"]')
    ).toBeVisible({ timeout: 10000 });

    await page
      .locator('[data-testid="mappings-new-from"]')
      .fill("investment-advisers-act:206");
    await page.locator('[data-testid="mappings-new-to"]').fill("usc-15:80b-6");

    await page.locator('[data-testid="mappings-create-submit"]').click();

    // Success toast appears and the inputs clear.
    await expect(page.getByText("Mapping created.")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-testid="mappings-new-from"]')).toHaveValue(
      ""
    );

    await component.unmount();
  });

  test("shows a guidance empty state when there are no mappings", async ({
    mount,
    page,
  }) => {
    const component = await mountPanel(mount, [
      statsMock({ totalCount: 0, bySource: [] }),
      statsMock({ totalCount: 0, bySource: [] }),
      listMock([]),
      listMock([]),
    ]);

    await expect(page.getByText("No authority mappings")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-testid="mappings-row"]')).toHaveCount(0);

    await component.unmount();
  });
});
