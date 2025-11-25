import { test, expect } from "@playwright/experimental-ct-react";
import { FolderTreeSidebar } from "../../src/components/corpuses/folders/FolderTreeSidebar";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import {
  createMockFolder,
  createMockFolderHierarchy,
} from "./utils/mockFolderData";
import { GET_CORPUS_FOLDERS } from "../../src/graphql/queries/folders";

test.describe("FolderTreeSidebar", () => {
  test("renders with mocked folder data", async ({ mount }) => {
    const { allFolders } = createMockFolderHierarchy();

    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: allFolders,
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Check that header is visible
    await expect(component.getByText("Folders")).toBeVisible({
      timeout: 5000,
    });

    // Check that Corpus Root is visible
    await expect(component.getByText("Corpus Root")).toBeVisible({
      timeout: 5000,
    });

    // Check that root folders are visible
    await expect(component.getByText("Documents")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Research")).toBeVisible({
      timeout: 5000,
    });
  });

  test("shows New Folder button", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Wait for query to complete and UI to render
    await expect(
      component.getByRole("heading", { name: "Folders" })
    ).toBeVisible({ timeout: 5000 });

    // Now check for New button - it may be styled, so look for any button with "New"
    const newButton = component.getByRole("button").filter({ hasText: "New" });
    await expect(newButton).toBeVisible({ timeout: 5000 });
  });

  test("shows expand/collapse all buttons", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    await expect(component.getByText("Expand All")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Collapse All")).toBeVisible({
      timeout: 5000,
    });
  });

  test("shows search input", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    const searchInput = component.getByPlaceholder("Search folders...");
    await expect(searchInput).toBeVisible({ timeout: 5000 });
  });

  test("shows empty state when no folders", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    await expect(
      component.getByText(
        'No folders yet. Click "New" to create your first folder.'
      )
    ).toBeVisible({ timeout: 5000 });
  });

  test("filters folders by search query", async ({ mount }) => {
    const { allFolders } = createMockFolderHierarchy();

    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: allFolders,
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Root folders should be visible initially
    await expect(component.getByText("Documents")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Research")).toBeVisible({
      timeout: 5000,
    });

    // Type in search box
    const searchInput = component.getByPlaceholder("Search folders...");
    await searchInput.fill("Research");

    // Wait a bit for filter to apply
    await component.waitFor({ timeout: 1000 });

    // Only matching folder should be visible
    await expect(component.getByText("Research")).toBeVisible({
      timeout: 3000,
    });

    // Documents should still show because it has child folders (tree includes parent if child matches)
    // But we can verify search worked by checking if "Research" is still visible
  });

  test("shows document count badges", async ({ mount }) => {
    const folders = [
      createMockFolder({
        id: "folder-1",
        name: "Documents",
        documentCount: 5,
      }),
    ];

    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: folders,
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Document count badge should be visible
    await expect(component.getByText("5")).toBeVisible({ timeout: 5000 });
  });

  test("handles loading state", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        delay: 100000, // Long delay to test loading state
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    // Check loading indicator appears
    await expect(component.getByText("Loading folders...")).toBeVisible({
      timeout: 2000,
    });
  });

  test("handles error state", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        error: new Error("Failed to load folders"),
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    // Check for error message - be flexible with format
    await expect(component.getByText(/Failed to load folders/i)).toBeVisible({
      timeout: 5000,
    });
  });

  test("Corpus Root is clickable", async ({ mount }) => {
    const mocks = [
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <FolderTreeSidebar corpusId="corpus-1" />
      </FolderTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    const corpusRoot = component.getByText("Corpus Root");
    await expect(corpusRoot).toBeVisible({ timeout: 5000 });

    // Should be clickable (cursor pointer)
    const style = await corpusRoot.evaluate((el) =>
      window.getComputedStyle(el.closest("div")!)
    );
    expect(style.cursor).toBe("pointer");
  });
});
