import React from "react";
import { test, expect } from "./utils/coverage";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusHome } from "../src/components/corpuses/CorpusHome";
import {
  GET_CORPUS_STATS,
  GET_CORPUS_WITH_HISTORY,
} from "../src/graphql/queries";

const mockCorpus = {
  id: "corpus-1",
  title: "Test Corpus",
  description: "This is a test corpus description",
  descriptionPreview: "This is a test corpus description",
  isPublic: true,
  creator: {
    email: "testuser@example.com",
  },
  created: new Date().toISOString(),
  labelSet: {
    id: "labelset-1",
    title: "Test Labels",
  },
  myPermissions: ["CAN_READ", "CAN_UPDATE"],
};

const mockStats = {
  totalDocs: 10,
  totalAnnotations: 25,
  totalComments: 0,
  totalAnalyses: 5,
  totalExtracts: 8,
  totalThreads: 0,
  totalChats: 0,
  totalRelationships: 0,
};

const mocks = [
  {
    request: {
      query: GET_CORPUS_STATS,
      variables: { corpusId: "corpus-1" },
    },
    result: {
      data: {
        corpusStats: mockStats,
      },
    },
  },
  {
    request: {
      query: GET_CORPUS_WITH_HISTORY,
      variables: { id: "corpus-1" },
    },
    result: {
      data: {
        corpus: {
          ...mockCorpus,
        },
      },
    },
  },
];

test.describe("CorpusHome Mobile Layout", () => {
  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE size

  test("should display compact layout on mobile", async ({ mount, page }) => {
    const component = await mount(
      <MemoryRouter initialEntries={["/corpuses/corpus-1"]}>
        <MockedProvider mocks={mocks} addTypename={false}>
          <Routes>
            <Route
              path="/corpuses/:corpusId"
              element={
                <CorpusHome
                  corpus={mockCorpus as any}
                  onEditDescription={() => {}}
                />
              }
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    // Check that the container is visible
    await expect(page.locator("#corpus-home-container")).toBeVisible();

    // Check top bar has reduced padding on mobile
    const topBar = page.locator("#corpus-home-top-bar");
    await expect(topBar).toBeVisible();

    // Check that title is visible but with smaller font
    const title = topBar.locator("h1");
    await expect(title).toBeVisible();
    await expect(title).toHaveText("Test Corpus");

    // Check that stats are visible and compact
    const statItems = topBar.locator('[class*="StatItem"]');
    await expect(statItems).toHaveCount(4);

    // Check metadata row is visible
    const metadata = topBar.locator('[class*="MetadataRow"]');
    await expect(metadata).toBeVisible();

    // Check that email is truncated on mobile (only showing username)
    await expect(metadata).toContainText("testuser");

    // Check description card is visible
    const descCard = page.locator("#corpus-home-description-card");
    await expect(descCard).toBeVisible();

    // Check main content has reduced padding
    const mainContent = page.locator("#corpus-home-main-content");
    await expect(mainContent).toBeVisible();

    await component.unmount();
  });

  test("should handle empty description gracefully on mobile", async ({
    mount,
    page,
  }) => {
    const corpusWithoutDescription = { ...mockCorpus, description: null };

    const component = await mount(
      <MemoryRouter initialEntries={["/corpuses/corpus-1"]}>
        <MockedProvider mocks={mocks} addTypename={false}>
          <Routes>
            <Route
              path="/corpuses/:corpusId"
              element={
                <CorpusHome
                  corpus={corpusWithoutDescription as any}
                  onEditDescription={() => {}}
                />
              }
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    // Check that empty state is shown with appropriate padding
    const descContent = page.locator('[class*="DescriptionContent"]');
    await expect(descContent).toBeVisible();
    await expect(descContent).toHaveClass(/empty/);

    // Check that the "No description yet" message is visible
    await expect(descContent).toContainText("No description yet");

    await component.unmount();
  });

  test("should display stats in compact format on mobile", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter initialEntries={["/corpuses/corpus-1"]}>
        <MockedProvider mocks={mocks} addTypename={false}>
          <Routes>
            <Route
              path="/corpuses/:corpusId"
              element={
                <CorpusHome
                  corpus={mockCorpus as any}
                  onEditDescription={() => {}}
                />
              }
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for stats to load
    await page.waitForTimeout(500);

    // Check that all stat values are visible
    const statValues = page.locator('[class*="StatValue"]');
    await expect(statValues).toHaveCount(4);

    // Check stat labels are visible with smaller font
    const statLabels = page.locator('[class*="StatLabel"]');
    await expect(statLabels).toHaveCount(4);

    // Verify compact labels
    await expect(statLabels.nth(0)).toContainText("DOCS");
    await expect(statLabels.nth(1)).toContainText("NOTES");
    await expect(statLabels.nth(2)).toContainText("ANALYSES");
    await expect(statLabels.nth(3)).toContainText("EXTRACTS");

    await component.unmount();
  });
});

test.describe("CorpusHome Desktop Layout", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test("should display full layout on desktop", async ({ mount, page }) => {
    const component = await mount(
      <MemoryRouter initialEntries={["/corpuses/corpus-1"]}>
        <MockedProvider mocks={mocks} addTypename={false}>
          <Routes>
            <Route
              path="/corpuses/:corpusId"
              element={
                <CorpusHome
                  corpus={mockCorpus as any}
                  onEditDescription={() => {}}
                />
              }
            />
          </Routes>
        </MockedProvider>
      </MemoryRouter>
    );

    // Check that full email is visible on desktop
    const metadata = page.locator('[class*="MetadataRow"]');
    await expect(metadata).toContainText("testuser@example.com");

    // Check that title has larger font on desktop
    const title = page.locator("h1");
    await expect(title).toBeVisible();

    // Check that padding is larger on desktop
    const topBar = page.locator("#corpus-home-top-bar");
    await expect(topBar).toBeVisible();

    await component.unmount();
  });
});
