/**
 * Component tests for the single-authority detail view — the editable surface of
 * the Authority Console. Drives the header edit/save (success, validation, server
 * error), the alias add / Enter / dedupe / remove / save flow, the shared
 * KeyEquivalence create / edit / cancel / delete table (the Relationships
 * section), the danger-zone delete, and the loading/error/not-found states.
 *
 * NOTE: the JSX-component (wrapper) import is kept in its OWN import statement,
 * separate from the helper/query/mutation imports, per the Playwright CT
 * split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityDetailViewTestWrapper } from "./AuthorityDetailViewTestWrapper";
import { GET_AUTHORITY_NAMESPACE_DETAIL } from "../src/graphql/queries";
import {
  CREATE_AUTHORITY_KEY_EQUIVALENCE,
  DELETE_AUTHORITY_KEY_EQUIVALENCE,
  DELETE_AUTHORITY_NAMESPACE,
  SET_AUTHORITY_NAMESPACE_ALIASES,
  UPDATE_AUTHORITY_KEY_EQUIVALENCE,
  UPDATE_AUTHORITY_NAMESPACE,
} from "../src/graphql/mutations";

const PREFIX = "usc-15";
const NS_ID = "NS:usc-15";

const makeNamespace = (over: Record<string, unknown> = {}) => ({
  id: NS_ID,
  prefix: PREFIX,
  displayName: "United States Code, Title 15",
  jurisdiction: "us-federal",
  authorityType: "statute",
  scope: "global",
  source: "manual",
  aliases: ["15 u.s.c.", "securities act"],
  provider: null,
  sourceRootUrl: null,
  license: null,
  isGlobal: true,
  effectiveProvider: "USCodeAuthoritySourceProvider",
  equivalenceCount: 1,
  frontierCount: 1,
  referenceCount: 42,
  createdByUsername: "admin",
  created: "2026-06-01T00:00:00Z",
  modified: "2026-06-01T00:00:00Z",
  authorityCorpus: null,
  ...over,
});

const editableEquiv = {
  id: "KE:1",
  fromKey: "usc-15:78j",
  toKey: "exchange-act:10",
  source: "manual",
  note: null,
  editable: true,
  createdByUsername: "admin",
  modified: "2026-06-01T00:00:00Z",
};

const makeDetail = (over: Record<string, unknown> = {}) => {
  // Pull the namespace override OUT before spreading ``rest`` so the spread can
  // never re-clobber the fully-built ``namespace`` with a partial fragment.
  const { namespace: nsOver, ...rest } = over;
  return {
    namespace: makeNamespace((nsOver as Record<string, unknown>) ?? {}),
    equivalencesOut: [],
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
    ...rest,
  };
};

const detailMock = (detail: ReturnType<typeof makeDetail> | null) => ({
  request: {
    query: GET_AUTHORITY_NAMESPACE_DETAIL,
    variables: { prefix: PREFIX },
  },
  result: { data: { authorityNamespaceDetail: detail } },
});

const detailErrorMock = () => ({
  request: {
    query: GET_AUTHORITY_NAMESPACE_DETAIL,
    variables: { prefix: PREFIX },
  },
  error: new Error("boom"),
});

const okResult = (field: string, message = "SUCCESS") => ({
  data: { [field]: { ok: true, message, obj: null } },
});
const failResult = (field: string, message: string) => ({
  data: { [field]: { ok: false, message, obj: null } },
});

const mountDetail = (mount: any, mocks: any[]) =>
  mount(<AuthorityDetailViewTestWrapper mocks={mocks} prefix={PREFIX} />);

/** Override window.confirm / window.prompt in the page so destructive verbs proceed. */
const allowDialogs = (page: any, promptValue = "") =>
  page.evaluate((v: string) => {
    (window as any).confirm = () => true;
    (window as any).prompt = () => v;
  }, promptValue);

test.describe("AuthorityDetailView", () => {
  test("edits the header and saves successfully", async ({ mount, page }) => {
    const updateMock = {
      request: {
        query: UPDATE_AUTHORITY_NAMESPACE,
        variables: {
          id: NS_ID,
          displayName: "USC Title 15 (edited)",
          jurisdiction: "us-federal",
          authorityType: "regulation",
          provider: "USCodeAuthoritySourceProvider",
          sourceRootUrl: "https://uscode.house.gov",
          license: "public-domain",
        },
      },
      result: okResult("updateAuthorityNamespace"),
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail()),
      updateMock,
      detailMock(makeDetail()),
    ]);

    await expect(page.locator('[data-testid="detail-title"]')).toContainText(
      "United States Code, Title 15",
      { timeout: 15000 }
    );

    await page.locator('[data-testid="detail-edit"]').click();
    await page
      .locator('[data-testid="detail-displayname"]')
      .fill("USC Title 15 (edited)");
    await page
      .locator('[data-testid="detail-jurisdiction"]')
      .fill("us-federal");
    await page
      .locator('[data-testid="detail-provider"]')
      .fill("USCodeAuthoritySourceProvider");
    await page
      .locator('[data-testid="detail-sourceurl"]')
      .fill("https://uscode.house.gov");
    await page.locator('[data-testid="detail-license"]').fill("public-domain");
    await page
      .locator('[data-testid="detail-type"]')
      .selectOption("regulation");
    await page.locator('[data-testid="detail-save"]').click();

    await expect(page.getByText("Authority updated.")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator('[data-testid="detail-change-count"]')
    ).toHaveText("1");

    await component.unmount();
  });

  test("rejects an empty display name without calling the server", async ({
    mount,
    page,
  }) => {
    const component = await mountDetail(mount, [detailMock(makeDetail())]);

    await expect(page.locator('[data-testid="detail-edit"]')).toBeVisible({
      timeout: 15000,
    });
    await page.locator('[data-testid="detail-edit"]').click();
    await page.locator('[data-testid="detail-displayname"]').fill("   ");
    await page.locator('[data-testid="detail-save"]').click();

    await expect(page.getByText("Display name is required.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("surfaces a server-side header save error", async ({ mount, page }) => {
    const updateMock = {
      request: {
        query: UPDATE_AUTHORITY_NAMESPACE,
        variables: {
          id: NS_ID,
          displayName: "United States Code, Title 15",
          jurisdiction: "us-federal",
          authorityType: "statute",
          provider: "",
          sourceRootUrl: "",
          license: "",
        },
      },
      result: failResult("updateAuthorityNamespace", "Prefix is read-only."),
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail()),
      updateMock,
    ]);

    await expect(page.locator('[data-testid="detail-edit"]')).toBeVisible({
      timeout: 15000,
    });
    await page.locator('[data-testid="detail-edit"]').click();
    await page.locator('[data-testid="detail-save"]').click();

    await expect(page.getByText("Prefix is read-only.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("adds (button + Enter), dedupes, removes and saves aliases", async ({
    mount,
    page,
  }) => {
    const setAliasesMock = {
      request: {
        query: SET_AUTHORITY_NAMESPACE_ALIASES,
        variables: { id: NS_ID, aliases: ["alpha", "beta"] },
      },
      result: okResult("setAuthorityNamespaceAliases"),
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail({ namespace: { aliases: ["beta", "gamma"] } })),
      setAliasesMock,
      detailMock(makeDetail({ namespace: { aliases: ["alpha", "beta"] } })),
    ]);

    await expect(page.locator('[data-testid="detail-alias-beta"]')).toBeVisible(
      { timeout: 15000 }
    );

    // Remove "gamma" via its chip X.
    await page.getByRole("button", { name: "Remove alias gamma" }).click();
    // Add "alpha" via the + button.
    await page.locator('[data-testid="detail-new-alias"]').fill("ALPHA");
    await page.locator('[data-testid="detail-add-alias"]').click();
    // Dedupe: adding "beta" again (via Enter) is a no-op.
    await page.locator('[data-testid="detail-new-alias"]').fill("beta");
    await page.locator('[data-testid="detail-new-alias"]').press("Enter");

    await expect(
      page.locator('[data-testid="detail-alias-alpha"]')
    ).toBeVisible();
    await page.locator('[data-testid="detail-save-aliases"]').click();

    await expect(page.getByText("Aliases saved.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("creates a relationship from the detail", async ({ mount, page }) => {
    const createMock = {
      request: {
        query: CREATE_AUTHORITY_KEY_EQUIVALENCE,
        variables: {
          fromKey: "usc-15:80b-6",
          toKey: "investment-advisers-act:206",
          note: null,
        },
      },
      result: okResult(
        "createAuthorityKeyEquivalence",
        "Relationship created."
      ),
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail()),
      createMock,
      detailMock(makeDetail()),
    ]);

    await expect(
      page.locator('[data-testid="detail-equiv-create-form"]')
    ).toBeVisible({ timeout: 15000 });
    await page
      .locator('[data-testid="detail-equiv-new-from"]')
      .fill("usc-15:80b-6");
    await page
      .locator('[data-testid="detail-equiv-new-to"]')
      .fill("investment-advisers-act:206");
    await page.locator('[data-testid="detail-equiv-create-submit"]').click();

    await expect(page.getByText("Relationship created.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("edits (with a cancel) then updates a relationship", async ({
    mount,
    page,
  }) => {
    const updateMock = {
      request: {
        query: UPDATE_AUTHORITY_KEY_EQUIVALENCE,
        variables: {
          id: "KE:1",
          fromKey: "usc-15:78j",
          toKey: "exchange-act:10b-5",
          note: null,
        },
      },
      result: okResult(
        "updateAuthorityKeyEquivalence",
        "Relationship updated."
      ),
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail({ equivalencesOut: [editableEquiv] })),
      updateMock,
      detailMock(makeDetail({ equivalencesOut: [editableEquiv] })),
    ]);

    await expect(page.locator('[data-testid="detail-equiv-row"]')).toHaveCount(
      1,
      { timeout: 15000 }
    );

    // Open the editor, then cancel it (covers the cancel path).
    await page.locator('[data-testid="detail-equiv-edit"]').click();
    await page.locator('[data-testid="detail-equiv-cancel"]').click();

    // Re-open, change the to-key, save.
    await page.locator('[data-testid="detail-equiv-edit"]').click();
    await page
      .locator('[data-testid="detail-equiv-edit-to"]')
      .fill("exchange-act:10b-5");
    await page.locator('[data-testid="detail-equiv-save"]').click();

    await expect(page.getByText("Relationship updated.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("deletes a relationship after confirmation", async ({ mount, page }) => {
    const deleteMock = {
      request: {
        query: DELETE_AUTHORITY_KEY_EQUIVALENCE,
        variables: { id: "KE:1" },
      },
      result: {
        data: {
          deleteAuthorityKeyEquivalence: {
            ok: true,
            message: "Relationship deleted.",
          },
        },
      },
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail({ equivalencesOut: [editableEquiv] })),
      deleteMock,
      detailMock(makeDetail({ equivalencesOut: [] })),
    ]);

    await expect(page.locator('[data-testid="detail-equiv-row"]')).toHaveCount(
      1,
      { timeout: 15000 }
    );
    await allowDialogs(page);
    await page.locator('[data-testid="detail-equiv-delete"]').click();

    await expect(page.getByText("Relationship deleted.")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("deletes the authority from the danger zone", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_AUTHORITY_NAMESPACE,
        variables: { id: NS_ID },
      },
      result: {
        data: {
          deleteAuthorityNamespace: { ok: true, message: "Authority deleted." },
        },
      },
    };

    const component = await mountDetail(mount, [
      detailMock(makeDetail()),
      deleteMock,
    ]);

    await expect(page.locator('[data-testid="detail-delete"]')).toBeVisible({
      timeout: 15000,
    });
    await allowDialogs(page);
    await page.locator('[data-testid="detail-delete"]').click();

    await expect(page.getByText("Authority deleted.")).toBeVisible({
      timeout: 10000,
    });
    // onClose fired -> the wrapper swaps in the closed marker.
    await expect(page.locator('[data-testid="detail-closed"]')).toBeVisible();

    await component.unmount();
  });

  test("renders an error state when the detail query fails", async ({
    mount,
    page,
  }) => {
    const component = await mountDetail(mount, [detailErrorMock()]);

    await expect(page.getByText("Error loading authority")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });

  test("renders not-found and the back link closes it", async ({
    mount,
    page,
  }) => {
    const component = await mountDetail(mount, [detailMock(null)]);

    await expect(page.getByText("Authority not found")).toBeVisible({
      timeout: 15000,
    });
    await page.locator('[data-testid="detail-back"]').click();
    await expect(page.locator('[data-testid="detail-closed"]')).toBeVisible();

    await component.unmount();
  });
});
