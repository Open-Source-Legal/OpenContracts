import { test, expect } from "@playwright/experimental-ct-react";
import { FolderTreeSidebar } from "../../src/components/corpuses/folders/FolderTreeSidebar";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import {
  createMockFolder,
  createMockFolderHierarchy,
} from "./utils/mockFolderData";
import { GET_CORPUS_FOLDERS } from "../../src/graphql/queries/folders";
import { docScreenshot, releaseScreenshot } from "../utils/docScreenshot";

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

    // Check that header is visible (uppercase FOLDERS)
    await expect(component.getByText("Folders")).toBeVisible({
      timeout: 5000,
    });

    // Check that Documents root is visible
    await expect(component.getByText("Documents").first()).toBeVisible({
      timeout: 5000,
    });

    // Check that root folders from mock data are visible
    await expect(component.getByText("Research")).toBeVisible({
      timeout: 5000,
    });
  });

  test("shows Folders header", async ({ mount }) => {
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

    // Check that Folders header is visible (exact match to avoid matching empty state message)
    await expect(component.getByText("Folders", { exact: true })).toBeVisible({
      timeout: 5000,
    });
  });

  test("shows Trash folder", async ({ mount }) => {
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

    // Check that Trash folder is visible
    await expect(component.getByText("Trash")).toBeVisible({ timeout: 5000 });
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

  test("renders folder tree with nested structure", async ({ mount, page }) => {
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
    await expect(component.getByText("Documents").first()).toBeVisible({
      timeout: 5000,
    });
    await expect(component.getByText("Research")).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "folders--tree-sidebar--nested", {
      element: component,
    });
    await releaseScreenshot(page, "v3.0.0.b3", "folder-tree", {
      element: component,
    });
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

  test("Documents root is clickable", async ({ mount }) => {
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

    const documentsRoot = component.getByText("Documents");
    await expect(documentsRoot).toBeVisible({ timeout: 5000 });

    // Should be clickable (cursor pointer)
    const style = await documentsRoot.evaluate((el) =>
      window.getComputedStyle(el.closest("div")!)
    );
    expect(style.cursor).toBe("pointer");
  });
});
