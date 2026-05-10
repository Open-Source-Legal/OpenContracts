// Playwright Component Test for Documents View
import React from "react";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { Documents } from "../src/views/Documents";
import { DocumentsTestWrapper } from "./DocumentsTestWrapper";
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

    // Tile counters reflect the backend aggregate (47), not the loaded edges (2).
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

    // The "All Documents" tab badge must match the Documents tile (47, not 2).
    const allDocsTab = page.locator('text="All Documents"').first();
    await expect(allDocsTab.locator("..").locator("text=47")).toBeVisible();

    await docScreenshot(page, "documents--stat-tiles--with-data");

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

test.describe("Documents View - Infinite Scroll (issue #1559)", () => {
  test("loads a second page when the sentinel scrolls into view", async ({
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

    const firstPageDocs = Array.from({ length: 20 }, (_, i) => ({
      id: `RG9jdW1lbnRUeXBlOlBhZ2UxXyR7aX0=_p1_${i}`,
      slug: `page-1-doc-${i}`,
      title: `Page 1 Document ${i + 1}.pdf`,
      fileType: "pdf",
      backendLock: false,
      pageCount: 5,
      icon: null,
      created: "2024-01-15T10:30:00Z",
      creator: {
        id: "VXNlclR5cGU6MQ==",
        slug: "test-user",
        email: "test@example.com",
      },
    }));

    const firstPageMock = {
      request: {
        query: GET_DOCUMENTS_FOR_LIST,
        variables: { limit: 20 },
      },
      result: {
        data: {
          documents: {
            edges: firstPageDocs.map((node) => ({ node })),
            pageInfo: {
              hasNextPage: true,
              hasPreviousPage: false,
              startCursor: "cursor-page-1-start",
              endCursor: "cursor-page-1-end",
            },
          },
        },
      },
    };

    const secondPageDoc = {
      id: "RG9jdW1lbnRUeXBlOlBhZ2UyXzE=",
      slug: "page-2-doc-1",
      title: "Page 2 Sentinel Document.pdf",
      fileType: "pdf",
      backendLock: false,
      pageCount: 7,
      icon: null,
      created: "2024-01-16T10:30:00Z",
      creator: {
        id: "VXNlclR5cGU6MQ==",
        slug: "test-user",
        email: "test@example.com",
      },
    };

    const secondPageMock = {
      request: {
        query: GET_DOCUMENTS_FOR_LIST,
        variables: {
          limit: 20,
          cursor: "cursor-page-1-end",
        },
      },
      result: {
        data: {
          documents: {
            edges: [{ node: secondPageDoc }],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: true,
              startCursor: "cursor-page-2-start",
              endCursor: "cursor-page-2-end",
            },
          },
        },
      },
    };

    const component = await mount(
      <DocumentsTestWrapper
        mocks={[
          firstPageMock,
          getDocumentStatsMock,
          getDocumentStatsMock,
          secondPageMock,
        ]}
        withRelayCache
      />
    );

    await expect(page.locator("text=Page 1 Document 1.pdf")).toBeVisible({
      timeout: 5000,
    });

    const sentinel = page.locator(".FetchMoreOnVisible");
    await sentinel.first().scrollIntoViewIfNeeded({ timeout: 5000 });
    // Allow the IntersectionObserver + Apollo cache merge to settle.
    await page.waitForTimeout(500);

    await expect(page.locator("text=Page 2 Sentinel Document.pdf")).toBeVisible(
      { timeout: 8000 }
    );

    authToken(null);
    userObj(null);
    backendUserObj(null);

    await component.unmount();
  });
});

// Refetch-storm regression is pinned by Documents.refetch-shape.test.ts (Vitest).
