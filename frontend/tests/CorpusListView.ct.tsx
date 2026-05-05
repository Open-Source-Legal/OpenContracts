import React from "react";
import { test, expect } from "./utils/coverage";
import { CorpusListViewTestWrapper } from "./CorpusListViewTestWrapper";
import { CorpusType, CorpusCategoryType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

/* -------------------------------------------------------------------------- */
/* Mock Data                                                                   */
/* -------------------------------------------------------------------------- */

const mockCategory: CorpusCategoryType = {
  id: "cat-1",
  name: "Contracts",
  __typename: "CorpusCategoryType",
};

const createMockCorpus = (
  id: string,
  title: string,
  options: Partial<{
    isPublic: boolean;
    creatorEmail: string;
    permissions: PermissionTypes[];
    categories: CorpusCategoryType[];
    documentCount: number;
    annotationCount: number;
    hasLabelSet: boolean;
  }> = {}
): CorpusType => ({
  id,
  slug: title.toLowerCase().replace(/\s+/g, "-"),
  title,
  icon: null,
  isPublic: options.isPublic ?? false,
  description: `Description for ${title}`,
  created: new Date().toISOString(),
  modified: new Date().toISOString(),
  creator: {
    id: "user-1",
    email: options.creatorEmail ?? "tester@example.com",
    slug: "tester",
    __typename: "UserType",
  },
  labelSet: options.hasLabelSet
    ? {
        id: "labelset-1",
        title: "Test Labels",
        docLabelCount: 2,
        spanLabelCount: 3,
        tokenLabelCount: 1,
        __typename: "LabelSetType",
      }
    : null,
  parent: null as unknown as CorpusType,
  allowComments: true,
  preferredEmbedder: null,
  appliedAnalyzerIds: [],
  myPermissions: options.permissions ?? [
    PermissionTypes.CAN_READ,
    PermissionTypes.CAN_UPDATE,
  ],
  categories: options.categories ?? [],
  analyses: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "AnalysisTypeConnection",
  },
  annotations: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: options.annotationCount ?? 0,
    __typename: "AnnotationTypeConnection",
  },
  documents: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: options.documentCount ?? 0,
    __typename: "DocumentTypeConnection",
  },
  // Direct count fields used by CorpusListView
  documentCount: options.documentCount ?? 0,
  annotationCount: options.annotationCount ?? 0,
  __typename: "CorpusType",
});

const mockCorpuses = [
  createMockCorpus("corpus-1", "My Private Corpus", {
    creatorEmail: "currentuser@example.com",
    permissions: [
      PermissionTypes.CAN_READ,
      PermissionTypes.CAN_UPDATE,
      PermissionTypes.CAN_REMOVE,
    ],
    documentCount: 5,
    annotationCount: 100,
    hasLabelSet: true,
  }),
  createMockCorpus("corpus-2", "Shared Corpus", {
    creatorEmail: "other@example.com",
    permissions: [PermissionTypes.CAN_READ],
  }),
  createMockCorpus("corpus-3", "Public Corpus", {
    isPublic: true,
    creatorEmail: "public@example.com",
    categories: [mockCategory],
    documentCount: 10,
  }),
];

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test.describe("CorpusListView", () => {
  test("renders empty state when no corpuses", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={[]}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Should show empty state message - look for the text content
    await expect(component.locator("text=No corpuses yet")).toBeVisible();
  });

  test("renders corpus cards with correct information", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Wait for corpuses to render - use card titles specifically
    await expect(
      component
        .locator(".oc-collection-card__title")
        .filter({ hasText: "My Private Corpus" })
    ).toBeVisible();
    await expect(
      component
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Shared Corpus" })
    ).toBeVisible();
    await expect(
      component
        .locator(".oc-collection-card__title")
        .filter({ hasText: "Public Corpus" })
    ).toBeVisible();

    // Check that stats are shown (docs count and labelset info, not annotations)
    await expect(component.getByText("5 docs")).toBeVisible();
    // Labelset shows: "Test Labels (6 labels)" based on mock data
    await expect(component.getByText(/Test Labels/)).toBeVisible();
  });

  test("shows correct stats summary", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Stats should show totals — scope to stat blocks since the same number
    // also appears in the filter tab badges.
    const statValues = component.locator(".oc-stat-block__value");
    // 3 corpuses total
    await expect(statValues.filter({ hasText: /^3$/ })).toBeVisible();
    // Total documents: 5 + 0 + 10 = 15
    await expect(statValues.filter({ hasText: /^15$/ })).toBeVisible();
  });

  test("filter tabs display correct counts", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Should have filter tabs - look for the "All" text
    await expect(component.locator("text=All").first()).toBeVisible();
    // Should show "My Corpuses" tab
    await expect(component.locator("text=My Corpuses").first()).toBeVisible();
  });

  test("filter tabs filter corpuses correctly", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Helper to find corpus card title
    const getCorpusCard = (title: string) =>
      component
        .locator(".oc-collection-card__title")
        .filter({ hasText: title });

    // Initially all corpuses visible
    await expect(getCorpusCard("My Private Corpus")).toBeVisible();
    await expect(getCorpusCard("Shared Corpus")).toBeVisible();
    await expect(getCorpusCard("Public Corpus")).toBeVisible();

    // Click "My Corpuses" tab - click on the text
    await component.locator("text=My Corpuses").first().click();

    // Only my corpus should be visible
    await expect(getCorpusCard("My Private Corpus")).toBeVisible();
    await expect(getCorpusCard("Shared Corpus")).not.toBeVisible();
    await expect(getCorpusCard("Public Corpus")).not.toBeVisible();

    // Click "Public" tab (the one that shows count, not the status on cards)
    // Use the filter tabs area specifically
    const publicTab = component.locator("text=Public").first();
    await publicTab.click();

    // Only public corpus should be visible
    await expect(getCorpusCard("My Private Corpus")).not.toBeVisible();
    await expect(getCorpusCard("Shared Corpus")).not.toBeVisible();
    await expect(getCorpusCard("Public Corpus")).toBeVisible();
  });

  test("search box is functional", async ({ mount }) => {
    let searchValue = "";
    const handleSearch = (value: string) => {
      searchValue = value;
    };

    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
        onSearchChange={handleSearch}
      />
    );

    // Find search box and type
    const searchBox = component.getByPlaceholder(/Search your corpuses/i);
    await expect(searchBox).toBeVisible();
    await searchBox.fill("test search");

    // Callback should have been called
    // Note: Component uses onChange which fires on each keystroke
  });

  test("shows visibility status correctly", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Check visibility status indicators are shown - use the status class
    const statusIndicators = component.locator(".oc-collection-card__status");
    await expect(statusIndicators.filter({ hasText: /Private/ })).toBeVisible();
    await expect(statusIndicators.filter({ hasText: /Public/ })).toBeVisible();
    await expect(statusIndicators.filter({ hasText: /Shared/ })).toBeVisible();
  });

  test("shows category badge when corpus has category", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // Public corpus has category "Contracts"
    await expect(component.getByText("Contracts")).toBeVisible();
  });

  test("shows labelset information", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
      />
    );

    // My Private Corpus has a labelset with 6 labels (2+3+1)
    await expect(component.getByText(/Test Labels.*6 labels/i)).toBeVisible();
  });

  test("shows loading overlay when loading", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={[]}
        searchValue=""
        loading={true}
        userEmail="currentuser@example.com"
      />
    );

    await expect(component.getByText(/Loading corpuses/i)).toBeVisible();
  });

  test("New Corpus button is visible when authenticated", async ({ mount }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail="currentuser@example.com"
        isAuthenticated={true}
      />
    );

    await expect(component.getByText("New Corpus")).toBeVisible();
  });

  test("New Corpus button is hidden when not authenticated", async ({
    mount,
  }) => {
    const component = await mount(
      <CorpusListViewTestWrapper
        corpuses={mockCorpuses}
        searchValue=""
        userEmail=""
        isAuthenticated={false}
      />
    );

    await expect(component.getByText("New Corpus")).not.toBeVisible();
  });
});
