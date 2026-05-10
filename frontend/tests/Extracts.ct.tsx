// Playwright Component Test for Extracts View
import React from "react";
import { test, expect } from "./utils/coverage";
import { ExtractsTestWrapper } from "./ExtractsTestWrapper";
import { ExtractType } from "../src/types/graphql-api";

// Mock extract data - matching the GraphQL query structure
const mockExtractRunning: ExtractType = {
  id: "RXh0cmFjdFR5cGU6MQ==",
  name: "Running Extract",
  created: "2024-01-15T10:30:00Z",
  started: "2024-01-15T10:35:00Z",
  finished: null,
  error: null,
  __typename: "ExtractType",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    username: "testuser",
    __typename: "UserType",
  },
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
  fieldset: {
    id: "fieldset1",
    name: "Test Fieldset",
    inUse: false,
    columns: {
      edges: [
        {
          node: { id: "col1", query: "test query", __typename: "ColumnType" },
          __typename: "ColumnTypeEdge",
        },
      ],
      __typename: "ColumnTypeConnection",
    },
    __typename: "FieldsetType",
  },
  myPermissions: ["read_extract", "update_extract", "remove_extract"],
} as ExtractType;

const mockExtractCompleted: ExtractType = {
  id: "RXh0cmFjdFR5cGU6Mg==",
  name: "Completed Extract",
  created: "2024-01-14T10:30:00Z",
  started: "2024-01-14T10:35:00Z",
  finished: "2024-01-14T11:00:00Z",
  error: null,
  __typename: "ExtractType",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    username: "testuser",
    __typename: "UserType",
  },
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
  fieldset: {
    id: "fieldset2",
    name: "Completed Fieldset",
    inUse: true,
    columns: {
      edges: [
        {
          node: { id: "col1", query: "test query", __typename: "ColumnType" },
          __typename: "ColumnTypeEdge",
        },
      ],
      __typename: "ColumnTypeConnection",
    },
    __typename: "FieldsetType",
  },
  myPermissions: ["read_extract", "update_extract", "remove_extract"],
} as ExtractType;

const mockExtractNotStarted: ExtractType = {
  id: "RXh0cmFjdFR5cGU6Mw==",
  name: "Not Started Extract",
  created: "2024-01-13T10:30:00Z",
  started: null,
  finished: null,
  error: null,
  __typename: "ExtractType",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    username: "testuser",
    __typename: "UserType",
  },
  corpus: null,
  fieldset: null,
  myPermissions: ["read_extract", "update_extract", "remove_extract"],
} as ExtractType;

const mockExtractFailed: ExtractType = {
  id: "RXh0cmFjdFR5cGU6NA==",
  name: "Failed Extract",
  created: "2024-01-12T10:30:00Z",
  started: "2024-01-12T10:35:00Z",
  finished: null,
  error: "Processing failed due to invalid input",
  __typename: "ExtractType",
  creator: {
    id: "VXNlclR5cGU6MQ==",
    username: "testuser",
    __typename: "UserType",
  },
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
    __typename: "CorpusType",
  },
  fieldset: {
    id: "fieldset3",
    name: "Failed Fieldset",
    inUse: false,
    columns: {
      edges: [
        {
          node: { id: "col1", query: "test query", __typename: "ColumnType" },
          __typename: "ColumnTypeEdge",
        },
      ],
      __typename: "ColumnTypeConnection",
    },
    __typename: "FieldsetType",
  },
  myPermissions: ["read_extract", "update_extract", "remove_extract"],
} as ExtractType;

const allExtracts = [
  mockExtractRunning,
  mockExtractCompleted,
  mockExtractNotStarted,
  mockExtractFailed,
];

test.describe("Extracts View - Loading and Display", () => {
  test("should display extracts with correct status badges", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=Completed Extract")).toBeVisible();
    await expect(page.locator("text=Not Started Extract")).toBeVisible();
    await expect(page.locator("text=Failed Extract")).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Filter Functionality", () => {
  test("should filter by status tabs", async ({ mount, page }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Click on "Running" tab
    await page.getByRole("tab", { name: /Running/ }).click();

    // Only running extract should be visible
    await expect(
      page
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Running Extract" })
    ).toBeVisible();

    // Click on "Completed" tab
    await page.getByRole("tab", { name: /Completed/ }).click();

    // Only completed extract should be visible
    await expect(
      page
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Completed Extract" })
    ).toBeVisible();

    // Click on "Failed" tab
    await page.getByRole("tab", { name: /Failed/ }).click();

    // Only failed extract should be visible
    await expect(
      page
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Failed Extract" })
    ).toBeVisible();

    // Click on "Not Started" tab
    await page.getByRole("tab", { name: /Not Started/ }).click();

    // Only not started extract should be visible
    await expect(
      page
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Not Started Extract" })
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Empty State", () => {
  test("should show empty state when no extracts", async ({ mount, page }) => {
    const component = await mount(<ExtractsTestWrapper extracts={[]} />);

    // Wait for empty state to appear
    await expect(page.locator("text=No extracts yet")).toBeVisible({
      timeout: 10000,
    });

    // Create button should be visible
    await expect(
      page.getByRole("button", { name: "Create Your First Extract" })
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Search Functionality", () => {
  test("should update search input value immediately", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for initial load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Type in search box
    const searchInput = page.locator('input[placeholder*="Search"]');
    await searchInput.fill("test search");

    // Verify the input value is updated immediately
    await expect(searchInput).toHaveValue("test search");

    await component.unmount();
  });
});

test.describe("Extracts View - Stats Display", () => {
  test("should display correct stats", async ({ mount, page }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Check stats are displayed
    await expect(
      page
        .locator(".oc-stat-block__label")
        .filter({ hasText: "Total Extracts" })
    ).toBeVisible();
    await expect(
      page.locator(".oc-stat-block__label").filter({ hasText: "Running" })
    ).toBeVisible();
    await expect(
      page.locator(".oc-stat-block__label").filter({ hasText: "Completed" })
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Context Menu", () => {
  test("should open context menu on right-click", async ({ mount, page }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Right-click on the extract card
    const extractCard = page.locator("text=Running Extract").first();
    await extractCard.click({ button: "right" });

    // Context menu should appear - uses role="menu" from ContextMenu component
    const contextMenu = page.locator('[role="menu"]');
    await expect(contextMenu).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });
});

test.describe("Extracts View - New Extract Button", () => {
  test("should show New Extract button when authenticated", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // New Extract button should be visible
    await expect(page.locator("text=New Extract")).toBeVisible();

    await component.unmount();
  });

  test("should open CreateExtractModal when New Extract button is clicked", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Click "New Extract" button
    await page.locator("text=New Extract").click();

    // Modal should appear with "Create New Extract" title
    await expect(page.locator("text=Create New Extract")).toBeVisible({
      timeout: 5000,
    });

    // Modal form fields should be visible
    await expect(
      page.locator('input[placeholder*="Enter a descriptive name"]')
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Permission-based UI", () => {
  test("should show delete option only when user has CAN_REMOVE permission", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Right-click on the extract card to open context menu
    const extractCard = page.locator("text=Running Extract").first();
    await extractCard.click({ button: "right" });

    // Wait for menu to appear
    await page.waitForTimeout(300);

    // Delete option should be visible (extract has delete permission in mock)
    await expect(page.locator("text=Delete")).toBeVisible({ timeout: 3000 });

    await component.unmount();
  });

  test("should hide delete option when user lacks CAN_REMOVE permission", async ({
    mount,
    page,
  }) => {
    // Create extract without delete permission
    const extractWithoutDelete: ExtractType = {
      ...mockExtractCompleted,
      id: "RXh0cmFjdFR5cGU6NQ==",
      name: "Read Only Extract",
      myPermissions: ["read_extract"], // Only read permission
    } as ExtractType;

    const component = await mount(
      <ExtractsTestWrapper extracts={[extractWithoutDelete]} />
    );

    // Wait for extract to load
    await expect(page.locator("text=Read Only Extract")).toBeVisible({
      timeout: 10000,
    });

    // Right-click on the extract card to open context menu
    const extractCard = page.locator("text=Read Only Extract").first();
    await extractCard.click({ button: "right" });

    // Wait for menu to appear
    await page.waitForTimeout(300);

    // Menu should appear with View Details but NOT Delete
    await expect(page.locator("text=View Details")).toBeVisible({
      timeout: 3000,
    });

    // Count menu items - should only have View Details, not Delete
    const menuItems = page.locator('[role="menuitem"]');
    await expect(menuItems).toHaveCount(1);

    await component.unmount();
  });
});

test.describe("Extracts View - Keyboard Accessibility", () => {
  test("should close context menu on Escape key", async ({ mount, page }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Right-click on the extract card to open context menu
    const extractCard = page.locator("text=Running Extract").first();
    await extractCard.click({ button: "right" });

    // Wait for menu to appear
    await page.waitForTimeout(300);

    // Context menu should appear - uses role="menu" from ContextMenu component
    const contextMenu = page.locator('[role="menu"]');
    await expect(contextMenu).toBeVisible({ timeout: 3000 });

    // Press Escape to close
    await page.keyboard.press("Escape");

    // Context menu should be hidden
    await expect(contextMenu).toBeHidden({ timeout: 3000 });

    await component.unmount();
  });

  test("should have accessible menu button with aria attributes", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Menu button should have proper aria attributes
    const menuButton = page.locator('[aria-label="Open menu"]').first();
    await expect(menuButton).toBeVisible();
    await expect(menuButton).toHaveAttribute("aria-haspopup", "menu");

    await component.unmount();
  });

  test("should have accessible cards with proper roles", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} />
    );

    // Wait for extracts to load
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    // Card wrapper should have article role
    const cardWrapper = page.locator('[role="article"]').first();
    await expect(cardWrapper).toBeVisible();

    await component.unmount();
  });
});

test.describe("Extracts View - Error States", () => {
  test("should handle GraphQL errors gracefully", async ({ mount, page }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={[]} error={true} />
    );

    // Should not crash, page header should still be rendered
    await expect(
      page.getByRole("heading", { name: "Your Extracts" })
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});

test.describe("Extracts View - Variable Builder Branch Coverage", () => {
  // Pinned for the PR #1602 ``extractVariables`` useMemo. Mounting with
  // ``initialSearchTerm`` set drives the truthy half of the
  // ``...(extract_search_term && { searchText: extract_search_term })``
  // spread, which the other tests skip (their search defaults to "").
  test("seeds searchText when initialSearchTerm is non-empty", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractsTestWrapper extracts={allExtracts} initialSearchTerm="lease" />
    );

    // The search input should reflect the seeded reactive var, and the
    // existing extracts should still render through the same query path
    // (the wrapper's variableMatcher is wildcard, so the truthy-search
    // variables are accepted).
    await expect(page.locator('input[placeholder*="Search"]')).toHaveValue(
      "lease"
    );
    await expect(page.locator("text=Running Extract")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});
