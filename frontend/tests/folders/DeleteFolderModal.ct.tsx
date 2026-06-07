import { test, expect } from "../utils/coverage";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import { DeleteFolderModalFixture } from "./utils/testFixtures";
import { createMockFolder } from "./utils/mockFolderData";
import { docScreenshot } from "../utils/docScreenshot";

test.describe("DeleteFolderModal", () => {
  const targetFolder = createMockFolder({
    id: "folder-1",
    name: "Contracts",
    path: "Contracts",
    documentCount: 5,
    descendantDocumentCount: 12,
  });

  const childFolder = createMockFolder({
    id: "folder-1-1",
    name: "Legal",
    path: "Contracts / Legal",
    parent: { id: "folder-1", name: "Contracts" },
    documentCount: 3,
  });

  const allFolders = [targetFolder, childFolder];

  test("renders confirmation dialog with folder info", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="folder-1" folders={allFolders} />
      </FolderTestWrapper>
    );

    // Modal title (use locator to target the header title specifically)
    await expect(
      page.locator(".oc-modal-header__title", { hasText: "Delete Folder" })
    ).toBeVisible({ timeout: 5000 });

    // Warning heading — folder delete now cascades the whole sub-tree and
    // moves its documents to Trash (recoverable), rather than stranding them
    // at the corpus root.
    await expect(
      page.getByText("Delete folder and move its contents to Trash")
    ).toBeVisible();

    // Folder name in warning (quoted in the warning text)
    await expect(page.getByText('"Contracts"')).toBeVisible();

    // Folder info section
    await expect(page.getByText("Documents in folder:")).toBeVisible();
    await expect(page.getByText("Subfolders:", { exact: true })).toBeVisible();

    await docScreenshot(page, "folders--delete-folder-modal--confirmation");
  });

  test("does not render when showModal is false", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture
          showModal={false}
          folderId="folder-1"
          folders={allFolders}
        />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Delete Folder")).not.toBeVisible();
  });

  test("does not render when folder is not found", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="nonexistent" folders={allFolders} />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Delete Folder")).not.toBeVisible();
  });

  test("shows subfolder and document counts in warning", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="folder-1" folders={allFolders} />
      </FolderTestWrapper>
    );

    // Should show subfolder count in the warning bullet ("…will be removed").
    // Filter on text unique to the subfolder bullet — "subfolder" alone also
    // matches the document bullet, which mentions "subfolders".
    await expect(
      page.locator("li", { hasText: "and any nested below" })
    ).toContainText("1");

    // Documents now move to Trash (cascade delete), not the corpus root: the
    // document bullet reports the descendant count (12) and says "Trash".
    await expect(
      page.locator("li", { hasText: "will be moved to" })
    ).toContainText("Trash");

    // The folder-info panel still surfaces the in-folder (5) and
    // in-subfolder (12) document counts.
    await expect(page.getByText("Documents in folder:")).toBeVisible();
    await expect(page.getByText("Documents in subfolders:")).toBeVisible();
  });

  test("has Cancel and Delete Folder buttons", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="folder-1" folders={allFolders} />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Cancel")).toBeVisible({ timeout: 5000 });

    const deleteButton = page.getByRole("button", { name: "Delete Folder" });
    await expect(deleteButton).toBeVisible();
  });

  test("has close button in header", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="folder-1" folders={allFolders} />
      </FolderTestWrapper>
    );

    const closeButton = page.getByRole("button", { name: "Close" });
    await expect(closeButton).toBeVisible({ timeout: 5000 });
  });

  test("shows parent name when deleting a subfolder", async ({
    mount,
    page,
  }) => {
    // Delete the child folder - items should move to parent "Contracts"
    const component = await mount(
      <FolderTestWrapper>
        <DeleteFolderModalFixture folderId="folder-1-1" folders={allFolders} />
      </FolderTestWrapper>
    );

    await expect(page.getByText('"Legal"')).toBeVisible({ timeout: 5000 });
    // Items will be moved to the parent folder "Contracts"
    await expect(page.getByText("Folder:", { exact: true })).toBeVisible();
  });
});
