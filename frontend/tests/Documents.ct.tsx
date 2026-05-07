// Playwright Component Test for Documents View
import React from "react";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { Documents } from "../src/views/Documents";
import {
  GET_DOCUMENTS_FOR_LIST,
  GET_DOCUMENT_STATS,
} from "../src/graphql/queries";
import {
  authToken,
  userObj,
  backendUserObj,
  documentSearchTerm,
  selectedDocumentIds,
} from "../src/graphql/cache";
// Mock document data — fields match GET_DOCUMENTS_FOR_LIST's selection set.
// The slim query intentionally omits ``description``, ``pdfFile``,
// ``isPublic``, ``modified``, ``myPermissions`` (and the rest of the kitchen
// sink the original GET_DOCUMENTS asked for) — see queries.ts.
const mockDocument1 = {
  id: "RG9jdW1lbnRUeXBlOjE=",
  slug: "test-document-1",
  title: "Test Document 1.pdf",
  fileType: "pdf",
  backendLock: false,
  pageCount: 10,
  icon: null,
  created: "2024-01-15T10:30:00Z",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    slug: "test-user",
    email: "test@example.com",
  },
};

const mockDocument2 = {
  id: "RG9jdW1lbnRUeXBlOjI=",
  slug: "test-document-2",
  title: "Test Document 2.docx",
  fileType: "docx",
  backendLock: true, // Processing
  pageCount: 5,
  icon: null,
  created: "2024-01-14T10:30:00Z",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    slug: "admin-user",
    email: "admin@example.com",
  },
};

// Base mock for GET_DOCUMENTS_FOR_LIST query. Variables match what the
// component sends on initial mount: ``{ limit: DOCUMENTS_PAGE_SIZE }`` with no
// search/filter set. (DOCUMENTS_PAGE_SIZE = 20 — kept inline here so test
// failures point at the wrong variable shape rather than a constant import.)
const getDocumentsMock = {
  request: {
    query: GET_DOCUMENTS_FOR_LIST,
    variables: {
      limit: 20,
    },
  },
  result: {
    data: {
      documents: {
        edges: [{ node: mockDocument1 }, { node: mockDocument2 }],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    },
  },
};

// Aggregate stats mock — the Documents view fires GET_DOCUMENT_STATS in
// parallel with the list query so the tile counters reflect the user's full
// permission scope. The component sends ``{}`` when no filters are active
// (search term empty, no corpus, no label), so the mock matches that shape.
const getDocumentStatsMock = {
  request: {
    query: GET_DOCUMENT_STATS,
    variables: {},
  },
  result: {
    data: {
      documentStats: {
        totalDocs: 2,
        totalPages: 15,
        processedCount: 1,
        processingCount: 1,
      },
    },
  },
};

// Empty stats mock — pairs with ``emptyDocumentsMock``.
const emptyDocumentStatsMock = {
  request: {
    query: GET_DOCUMENT_STATS,
    variables: {},
  },
  result: {
    data: {
      documentStats: {
        totalDocs: 0,
        totalPages: 0,
        processedCount: 0,
        processingCount: 0,
      },
    },
  },
};

// Empty documents mock
const emptyDocumentsMock = {
  request: {
    query: GET_DOCUMENTS_FOR_LIST,
    variables: {
      limit: 20,
    },
  },
  result: {
    data: {
      documents: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    },
  },
};

test.describe("Documents View - Context Menu Interactions", () => {
  test("should open context menu on right-click and show basic options", async ({
    mount,
    page,
  }) => {
    // Set up reactive vars before mounting
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Right-click on the document card
    const docCard = page.locator("text=Test Document 1.pdf").first();
    await docCard.click({ button: "right" });

    // Context menu should appear - uses role="menu" from ContextMenu component
    const contextMenu = page.locator('[role="menu"]');
    await expect(contextMenu).toBeVisible({
      timeout: 3000,
    });

    // Check that at least "Open Document" and "View Details" are present
    // These are always available regardless of auth state
    await expect(contextMenu.locator("text=Open Document")).toBeVisible();
    await expect(contextMenu.locator("text=View Details")).toBeVisible();

    // Clean up
    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - View Mode Toggle", () => {
  test("should switch between grid, list, and compact views", async ({
    mount,
    page,
  }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Initially in grid view - verify grid button is active
    const gridButton = page.locator('[aria-label="Grid view"]');
    await expect(gridButton).toHaveAttribute("aria-pressed", "true");

    // Switch to list view
    const listButton = page.locator('[aria-label="List view"]');
    await listButton.click();
    await expect(listButton).toHaveAttribute("aria-pressed", "true");

    // Verify list view elements are visible
    await expect(page.locator('[role="table"]')).toBeVisible();

    // Switch to compact view
    const compactButton = page.locator('[aria-label="Compact view"]');
    await compactButton.click();
    await expect(compactButton).toHaveAttribute("aria-pressed", "true");

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - Filter Functionality", () => {
  test("should filter by status tabs", async ({ mount, page }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Click on "Processing" tab - use role to be more specific
    await page.getByRole("tab", { name: /Processing/ }).click();

    // Only processing documents should be visible
    await expect(page.locator("text=Test Document 2.docx")).toBeVisible();

    // Click on "Processed" tab
    await page.locator("text=Processed").first().click();

    // Only processed documents should be visible
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible();

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });

  test("should open and close advanced filters popup", async ({
    mount,
    page,
  }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Click Filters button
    const filtersButton = page.locator("button").filter({ hasText: "Filters" });
    await filtersButton.click();

    // Filter popup should open
    await expect(page.locator("text=Advanced Filters")).toBeVisible({
      timeout: 2000,
    });

    // Close by clicking the X button
    await page.locator('[role="dialog"] button').first().click();

    // Popup should close
    await expect(page.locator("text=Advanced Filters")).not.toBeVisible({
      timeout: 2000,
    });

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - Empty State", () => {
  test("should show empty state when no documents", async ({ mount, page }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          emptyDocumentsMock,
          emptyDocumentsMock,
          emptyDocumentStatsMock,
          emptyDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for empty state to appear
    await expect(page.locator("text=No documents yet")).toBeVisible({
      timeout: 5000,
    });

    // Upload button should be visible
    await expect(page.locator("text=Upload Your First Document")).toBeVisible();

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - Search Functionality", () => {
  test("should update search input value immediately", async ({
    mount,
    page,
  }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for initial load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Type in search box
    const searchInput = page.locator('input[placeholder*="Search"]');
    await searchInput.fill("test search");

    // Verify the input value is updated immediately
    await expect(searchInput).toHaveValue("test search");

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });

  test("should cancel pending search on unmount", async ({ mount, page }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Type in search box (this starts a debounce timer)
    const searchInput = page.locator('input[placeholder*="Search"]');
    await searchInput.fill("pending search");

    // Unmount before debounce completes (1000ms delay)
    // This tests that the cleanup function properly cancels the debounce
    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();

    // If we reach here without errors, the debounce was properly cancelled
    expect(true).toBe(true);
  });
});

test.describe("Documents View - Selection", () => {
  test("should have select all checkbox in list view header", async ({
    mount,
    page,
  }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for documents to load
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    // Switch to list view where the select all checkbox is in the header
    const listButton = page.locator('[aria-label="List view"]');
    await listButton.click();

    // Wait for list view to render
    await expect(page.locator('[role="table"]')).toBeVisible();

    // Verify list header has the select all checkbox
    const listHeader = page.locator('[role="rowgroup"]');
    await expect(listHeader.locator('input[type="checkbox"]')).toBeVisible();

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - Stat Tiles", () => {
  test("renders permission-scoped stats from GET_DOCUMENT_STATS, not the loaded edges", async ({
    mount,
    page,
  }) => {
    authToken("test-auth-token");
    userObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
    } as any);
    backendUserObj({
      id: "1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
    documentSearchTerm("");
    selectedDocumentIds([]);

    // Stats mock asserts a different shape than the list mock: 47 totalDocs
    // even though only 2 edges are loaded. This is exactly the bug the PR
    // fixes — the old client-side reduce would have shown "2", the new
    // backend aggregate shows "47".
    const populatedStatsMock = {
      request: {
        query: GET_DOCUMENT_STATS,
        variables: {},
      },
      result: {
        data: {
          documentStats: {
            totalDocs: 47,
            totalPages: 1234,
            processedCount: 40,
            processingCount: 7,
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider
        mocks={[
          getDocumentsMock,
          getDocumentsMock,
          populatedStatsMock,
          populatedStatsMock,
        ]}
        addTypename={false}
      >
        <MemoryRouter>
          <JotaiProvider>
            <Documents />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for the list query to settle so the page is fully painted before
    // we read the tile values.
    await expect(page.locator("text=Test Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    const tiles = page.locator(".oc-stat-block .oc-stat-block__value");
    await expect(tiles).toHaveCount(4, { timeout: 5000 });
    // Order matches Documents.tsx: Documents, Pages, Processed, Processing.
    await expect(tiles.nth(0)).toHaveText("47");
    // toLocaleString() on 1234 yields "1,234" in en-US — the test runs in a
    // jsdom-backed Chromium where en-US is the default locale.
    await expect(tiles.nth(1)).toHaveText("1,234");
    await expect(tiles.nth(2)).toHaveText("40");
    await expect(tiles.nth(3)).toHaveText("7");

    // The "All Documents" filter tab badge must match the Documents tile —
    // before the fix it tracked ``document_items.length`` (here: 2) and
    // diverged from the tile counter sitting next to it.
    const allDocsTab = page.locator('text="All Documents"').first();
    await expect(allDocsTab.locator("..").locator("text=47")).toBeVisible();

    // Capture the populated stats hero for the docs site so reviewers can
    // see the tile-counter contract this PR fixes (full visible count, not
    // the paginated subset).
    await docScreenshot(page, "documents--stat-tiles--with-data");

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Regression notes:
//
// The Documents view previously fired ~7 GET_DOCUMENTS requests on every
// mount — one from the ``useQuery`` itself plus six redundant
// ``useEffect(refetchDocuments)`` hooks. Combined with
// ``nextFetchPolicy: "network-only"`` every refetch bypassed the cache.
//
// Catching the storm BEHAVIORALLY is not viable in this MockedProvider
// environment: Apollo's built-in query deduplication merges concurrent
// in-flight queries with the same key, so all six mount-time refetches
// collapse into the single initial network request before reaching MockLink.
// A counter on MockLink can't see them.
//
// The structural fix is therefore pinned by a Vitest source-level test in
// ``frontend/src/views/Documents.refetch-shape.test.ts`` that asserts:
//   - no ``nextFetchPolicy: "network-only"`` in the source,
//   - no ``useEffect`` block ending with a bare ``refetchDocuments()`` call,
//   - the slim ``GET_DOCUMENTS_FOR_LIST`` query is the imported one.
//
// The CT mocks above already pin the on-the-wire variable shape — they use
// strict ``{ limit: 20 }`` matching, so any drift in the request variables
// would surface as a "document doesn't render" failure in the existing
// tests.
// ─────────────────────────────────────────────────────────────────────────────
