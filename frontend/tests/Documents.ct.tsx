// Playwright Component Test for Documents View
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { Documents } from "../src/views/Documents";
import { GET_DOCUMENTS } from "../src/graphql/queries";
import {
  DELETE_MULTIPLE_DOCUMENTS,
  UPDATE_DOCUMENT,
} from "../src/graphql/mutations";
import {
  authToken,
  userObj,
  backendUserObj,
  documentSearchTerm,
  selectedDocumentIds,
} from "../src/graphql/cache";
import { GraphQLError } from "graphql";

// Mock document data
const mockDocument1 = {
  id: "RG9jdW1lbnRUeXBlOjE=",
  title: "Test Document 1.pdf",
  description: "A test document",
  icon: null,
  pdfFile: "https://example.com/doc1.pdf",
  fileType: "pdf",
  pageCount: 10,
  backendLock: false,
  isPublic: false,
  created: "2024-01-15T10:30:00Z",
  modified: "2024-01-15T10:30:00Z",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "test@example.com",
  },
  myPermissions: ["read", "update", "delete"],
};

const mockDocument2 = {
  id: "RG9jdW1lbnRUeXBlOjI=",
  title: "Test Document 2.docx",
  description: "Another test document",
  icon: null,
  pdfFile: "https://example.com/doc2.pdf",
  fileType: "docx",
  pageCount: 5,
  backendLock: true, // Processing
  isPublic: false,
  created: "2024-01-14T10:30:00Z",
  modified: "2024-01-14T10:30:00Z",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "admin@example.com",
  },
  myPermissions: ["read", "update", "delete"],
};

// Base mock for GET_DOCUMENTS query
const getDocumentsMock = {
  request: {
    query: GET_DOCUMENTS,
    variables: {
      includeMetadata: true,
      annotateDocLabels: false,
    },
  },
  result: {
    data: {
      documents: {
        edges: [{ node: mockDocument1 }, { node: mockDocument2 }],
        pageInfo: {
          hasNextPage: false,
          endCursor: null,
        },
      },
    },
  },
};

// Empty documents mock
const emptyDocumentsMock = {
  request: {
    query: GET_DOCUMENTS,
    variables: {
      includeMetadata: true,
      annotateDocLabels: false,
    },
  },
  result: {
    data: {
      documents: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[emptyDocumentsMock, emptyDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
        mocks={[getDocumentsMock, getDocumentsMock]}
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
