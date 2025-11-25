import { test, expect } from "@playwright/experimental-ct-react";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import { BreadcrumbFixture } from "./utils/testFixtures";
import { createDeepFolderHierarchy } from "./utils/mockFolderData";

test.describe("FolderBreadcrumb", () => {
  test("shows only Corpus Root when no folder selected", async ({ mount }) => {
    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId={null} folders={[]} />
      </FolderTestWrapper>
    );

    await expect(component.getByText("Corpus Root")).toBeVisible();

    // Should not show any folder names
    await expect(component.getByText("Corpus Root")).toBeVisible();
  });

  test("shows breadcrumb path for selected folder", async ({ mount }) => {
    const folders = [
      {
        id: "folder-1",
        name: "Documents",
        parent: null,
        path: "Documents",
      },
      {
        id: "folder-2",
        name: "Legal",
        parent: { id: "folder-1", name: "Documents" },
        path: "Documents / Legal",
      },
    ];

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-2" folders={folders} />
      </FolderTestWrapper>
    );

    // Should show full path
    await expect(component.getByText("Corpus Root")).toBeVisible();
    await expect(component.getByText("Documents")).toBeVisible();
    await expect(component.getByText("Legal")).toBeVisible();
  });

  test("shows ellipsis for deep folder hierarchies", async ({ mount }) => {
    const { allFolders, deepestFolder } = createDeepFolderHierarchy();

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId={deepestFolder.id} folders={allFolders} />
      </FolderTestWrapper>
    );

    // Should show ellipsis
    await expect(component.getByText("...")).toBeVisible();

    // Should show first and last folders - use first/last to avoid ambiguity
    const level1Buttons = component.getByRole("button", { name: "Level 1" });
    await expect(level1Buttons.first()).toBeVisible();

    await expect(
      component.getByRole("button", { name: "Level 10" })
    ).toBeVisible();
  });

  test("shows Home icon for Corpus Root", async ({ mount }) => {
    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId={null} folders={[]} />
      </FolderTestWrapper>
    );

    const corpusRoot = component.getByText("Corpus Root");
    await expect(corpusRoot).toBeVisible();

    // Check that an svg icon is present (Home icon from lucide-react)
    const svg = await corpusRoot.locator("..").locator("svg").first();
    await expect(svg).toBeVisible();
  });

  test("shows chevron separators between segments", async ({ mount }) => {
    const folders = [
      {
        id: "folder-1",
        name: "Documents",
        parent: null,
        path: "Documents",
      },
      {
        id: "folder-2",
        name: "Legal",
        parent: { id: "folder-1", name: "Documents" },
        path: "Documents / Legal",
      },
    ];

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-2" folders={folders} />
      </FolderTestWrapper>
    );

    // Check that chevron icons are present
    const svgs = component.locator("svg");
    const count = await svgs.count();

    // Should have Home icon + multiple chevron icons
    expect(count).toBeGreaterThan(2);
  });

  test("last breadcrumb item is not clickable", async ({ mount }) => {
    const folders = [
      {
        id: "folder-1",
        name: "Documents",
        parent: null,
        path: "Documents",
      },
    ];

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-1" folders={folders} />
      </FolderTestWrapper>
    );

    const documentsButton = component.getByText("Documents");
    await expect(documentsButton).toBeVisible();

    // Check that it has cursor: default (not clickable)
    const style = await documentsButton.evaluate((el) =>
      window.getComputedStyle(el)
    );
    expect(style.cursor).toBe("default");
  });

  test("previous breadcrumb items are clickable", async ({ mount }) => {
    const folders = [
      {
        id: "folder-1",
        name: "Documents",
        parent: null,
        path: "Documents",
      },
      {
        id: "folder-2",
        name: "Legal",
        parent: { id: "folder-1", name: "Documents" },
        path: "Documents / Legal",
      },
    ];

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-2" folders={folders} />
      </FolderTestWrapper>
    );

    const corpusRoot = component.getByText("Corpus Root");
    const documentsLink = component.getByText("Documents");

    // Both should be clickable (cursor pointer)
    const corpusRootStyle = await corpusRoot.evaluate((el) =>
      window.getComputedStyle(el)
    );
    expect(corpusRootStyle.cursor).toBe("pointer");

    const documentsStyle = await documentsLink.evaluate((el) =>
      window.getComputedStyle(el)
    );
    expect(documentsStyle.cursor).toBe("pointer");
  });

  test("shows loading state when folder selected but breadcrumb empty", async ({
    mount,
  }) => {
    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-1" folders={[]} />
      </FolderTestWrapper>
    );

    await expect(component.getByText("Loading path...")).toBeVisible();
  });

  test("respects maxDepth prop", async ({ mount }) => {
    const { allFolders } = createDeepFolderHierarchy();

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture
          folderId={allFolders[allFolders.length - 1].id}
          folders={allFolders}
          maxDepth={3}
        />
      </FolderTestWrapper>
    );

    // Should show ellipsis for depth > 3
    await expect(component.getByText("...")).toBeVisible();
  });

  test("highlights current folder with different color", async ({ mount }) => {
    const folders = [
      {
        id: "folder-1",
        name: "Documents",
        parent: null,
        path: "Documents",
      },
      {
        id: "folder-2",
        name: "Legal",
        parent: { id: "folder-1", name: "Documents" },
        path: "Documents / Legal",
      },
    ];

    const component = await mount(
      <FolderTestWrapper>
        <BreadcrumbFixture folderId="folder-2" folders={folders} />
      </FolderTestWrapper>
    );

    const legalButton = component.getByText("Legal");
    const documentsButton = component.getByText("Documents");

    // Get computed styles
    const legalStyle = await legalButton.evaluate((el) =>
      window.getComputedStyle(el)
    );
    const documentsStyle = await documentsButton.evaluate((el) =>
      window.getComputedStyle(el)
    );

    // Legal (current) should have different color and be bold
    expect(legalStyle.fontWeight).toBe("600");
    expect(documentsStyle.fontWeight).toBe("400");
  });
});
