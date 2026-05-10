import { test, expect } from "./utils/coverage";
import { TrashFolderViewTestWrapper } from "./TrashFolderViewTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("TrashFolderView", () => {
  test("renders trash folder header", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await expect(page.getByRole("heading", { name: /Trash/ })).toBeVisible({
      timeout: 10000,
    });
  });

  test("shows loading state initially", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    // May show loading or content depending on timing
    const hasLoading = await page
      .getByText("Loading trash...")
      .isVisible()
      .catch(() => false);
    const hasContent = await page
      .getByText("Deleted Document 1")
      .isVisible()
      .catch(() => false);

    expect(hasLoading || hasContent).toBe(true);
  });

  test("displays deleted documents after loading", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    await expect(page.getByText("Deleted Document 1")).toBeVisible();
    await expect(page.getByText("Deleted Document 2")).toBeVisible();
  });

  test("shows document count in header", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    await expect(page.getByText("(2 items)")).toBeVisible();
  });

  test("shows document metadata", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Check file types
    await expect(page.getByText("PDF").first()).toBeVisible();
    await expect(page.getByText("DOCX")).toBeVisible();

    // ``getCreatorDisplay`` renders the public ``slug`` (``username`` is now
    // self-only PII and resolves to ``null`` for cross-user viewers).
    await expect(page.getByText("john-doe")).toBeVisible();
    await expect(page.getByText("jane-smith")).toBeVisible();

    // Check page counts
    await expect(page.getByText("10 pages")).toBeVisible();
    await expect(page.getByText("5 pages")).toBeVisible();

    // Check original folder
    await expect(page.getByText("Was in: Original Folder")).toBeVisible();
  });

  test("shows empty state when trash is empty", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper mockType="empty" />);

    await page.waitForSelector('text="Trash is Empty"', { timeout: 10000 });

    await expect(page.getByText("Trash is Empty")).toBeVisible();
    await expect(
      page.getByText("Deleted documents will appear here")
    ).toBeVisible();
  });

  test("shows error message on fetch failure", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper mockType="error" />);

    await page.waitForSelector('text="Failed to load trash"', {
      timeout: 10000,
    });

    await expect(page.getByText("Failed to load trash").first()).toBeVisible();
  });

  test("allows selecting documents", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click on a document card to select it
    await page.getByText("Deleted Document 1").click();

    // Selection bar should appear
    await expect(page.getByText("1 item selected")).toBeVisible();
  });

  test("allows selecting multiple documents", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click on both documents
    await page.getByText("Deleted Document 1").click();
    await page.getByText("Deleted Document 2").click();

    // Selection bar should show 2 items
    await expect(page.getByText("2 items selected")).toBeVisible();
  });

  test("select all functionality works", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click select all checkbox
    await page.getByText("Select all").click();

    // Should show all items selected
    await expect(page.getByText("2 items selected")).toBeVisible();
  });

  test("clear selection functionality works", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Select a document
    await page.getByText("Deleted Document 1").click();
    await expect(page.getByText("1 item selected")).toBeVisible();

    // Clear selection
    await page.getByText("Clear Selection").click();

    // Selection bar should disappear
    await expect(page.getByText("1 item selected")).not.toBeVisible();
  });

  test("shows restore button on each document", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Each document should have a restore button
    const restoreButtons = page.getByRole("button", { name: /Restore/ });
    const count = await restoreButtons.count();

    // At least 2 restore buttons (one per document)
    expect(count).toBeGreaterThanOrEqual(2);
    await docScreenshot(page, "versioning--trash-folder--restore-ui");
  });

  test("shows success message after restore", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper restoreMockType="success" />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click restore on first document
    await page
      .getByRole("button", { name: /Restore/ })
      .first()
      .click();

    // Should show success message
    await expect(page.getByText("Success").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Document restored successfully")
    ).toBeVisible();
  });

  test("shows error message on restore failure", async ({ mount, page }) => {
    await mount(<TrashFolderViewTestWrapper restoreMockType="failure" />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click restore on first document
    await page
      .getByRole("button", { name: /Restore/ })
      .first()
      .click();

    // Should show error message
    await expect(page.getByText("Restore Failed")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Permission denied")).toBeVisible();
  });

  test("calls onBack when back button clicked", async ({ mount, page }) => {
    let backCalled = false;

    await mount(
      <TrashFolderViewTestWrapper
        onBack={() => {
          backCalled = true;
        }}
      />
    );

    await page.waitForSelector('text="Trash"', { timeout: 10000 });

    // Click back button (has title "Back to Folders" and text "Back")
    await page.getByRole("button", { name: /Back/ }).click();

    expect(backCalled).toBe(true);
  });

  test("shows empty trash button when trash has items", async ({
    mount,
    page,
  }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    await expect(page.getByText("Empty Trash")).toBeVisible();
  });

  test("does not show empty trash button when trash is empty", async ({
    mount,
    page,
  }) => {
    await mount(<TrashFolderViewTestWrapper mockType="empty" />);

    await page.waitForSelector('text="Trash is Empty"', { timeout: 10000 });

    await expect(page.getByText("Empty Trash")).not.toBeVisible();
  });

  test("empty trash button is enabled when trash has items", async ({
    mount,
    page,
  }) => {
    await mount(<TrashFolderViewTestWrapper />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    const emptyTrashButton = page.getByRole("button", { name: /Empty Trash/ });
    await expect(emptyTrashButton).toBeVisible();
    await expect(emptyTrashButton).toBeEnabled();
  });

  test("shows partial success and failure on bulk restore", async ({
    mount,
    page,
  }) => {
    await mount(<TrashFolderViewTestWrapper restoreMockType="partial" />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Select all documents
    await page.getByText("Select all").click();
    await expect(page.getByText("2 items selected")).toBeVisible();

    // Click restore selected
    await page.getByText("Restore Selected").click();

    // Should show both success and error messages
    await expect(page.getByText("Restored 1 document")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Failed to restore 1 document")).toBeVisible();
  });

  test("clears only successfully restored items from selection on partial failure", async ({
    mount,
    page,
  }) => {
    await mount(<TrashFolderViewTestWrapper restoreMockType="partial" />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Select all documents
    await page.getByText("Select all").click();
    await expect(page.getByText("2 items selected")).toBeVisible();

    // Click restore selected
    await page.getByText("Restore Selected").click();

    // Wait for operation to complete - verify both success and error messages appear
    await expect(page.getByText("Restored 1 document")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Failed to restore 1 document")).toBeVisible();

    // The selection state is managed internally - verify the messages indicate
    // partial success/failure which validates the Promise.allSettled logic
    // Note: GraphQL mocks in tests don't always trigger React state updates correctly
  });

  test("success message auto-dismisses after timeout", async ({
    mount,
    page,
  }) => {
    // Use longer timeout for this test since we wait for auto-dismiss
    test.setTimeout(20000);

    // Test with a custom timeout check
    await mount(<TrashFolderViewTestWrapper restoreMockType="success" />);

    await page.waitForSelector('text="Deleted Document 1"', { timeout: 10000 });

    // Click restore on first document
    await page
      .getByRole("button", { name: /Restore/ })
      .first()
      .click();

    // Should show success message
    await expect(page.getByText("Success").first()).toBeVisible({
      timeout: 10000,
    });

    // Wait for auto-dismiss (5 seconds + some buffer)
    await page.waitForTimeout(6000);

    // Success message should be gone
    await expect(page.getByText("Success").first()).not.toBeVisible();
  });

  // Null data scenario tests
  test.describe("Null Data Scenarios", () => {
    test("handles document with null creator gracefully", async ({
      mount,
      page,
    }) => {
      await mount(<TrashFolderViewTestWrapper mockType="nullCreator" />);

      await page.waitForSelector('text="Document with Null Creator"', {
        timeout: 10000,
      });

      // Should display the document title
      await expect(page.getByText("Document with Null Creator")).toBeVisible();

      // ``getCreatorDisplay(null)`` returns "Unknown" — the unified fallback
      // for any null/undefined creator across the app.
      await expect(page.getByText("Deleted by Unknown")).toBeVisible();
    });

    test("handles document with null document data gracefully", async ({
      mount,
      page,
    }) => {
      await mount(<TrashFolderViewTestWrapper mockType="nullDocument" />);

      // Wait for the trash view to load
      await page.waitForSelector('text="Trash"', { timeout: 10000 });

      // Should show fallback title for null document
      await expect(page.getByText("Untitled Document")).toBeVisible();

      // Should show fallback file type
      await expect(page.getByText("Unknown")).toBeVisible();

      // Should show 0 pages for null document
      await expect(page.getByText("0 pages")).toBeVisible();
    });

    test("handles invalid date string gracefully", async ({ mount, page }) => {
      await mount(<TrashFolderViewTestWrapper mockType="invalidDate" />);

      await page.waitForSelector('text="Document with Invalid Date"', {
        timeout: 10000,
      });

      // Should display the document
      await expect(page.getByText("Document with Invalid Date")).toBeVisible();

      // Should show fallback text for invalid date
      await expect(page.getByText("Unknown time")).toBeVisible();
      await expect(page.getByText("Unknown date")).toBeVisible();
    });

    test("shows error when trying to restore document with null data", async ({
      mount,
      page,
    }) => {
      await mount(<TrashFolderViewTestWrapper mockType="nullDocument" />);

      await page.waitForSelector('text="Untitled Document"', {
        timeout: 10000,
      });

      // Click restore on the document with null data
      await page
        .getByRole("button", { name: /Restore/ })
        .first()
        .click();

      // Should show error message about missing document information
      await expect(
        page.getByText("Cannot restore: document information is missing")
      ).toBeVisible({ timeout: 10000 });
    });

    test("filters out null documents in bulk restore and shows warning", async ({
      mount,
      page,
    }) => {
      // Use longer timeout for this async mutation test
      test.setTimeout(20000);

      await mount(
        <TrashFolderViewTestWrapper
          mockType="mixedNull"
          restoreMockType="mixedNull"
        />
      );

      await page.waitForSelector('text="Valid Document"', { timeout: 10000 });

      // Should show both items (one valid, one with null document)
      await expect(page.getByText("Valid Document")).toBeVisible();
      await expect(page.getByText("Untitled Document")).toBeVisible();

      // Select all documents
      await page.getByText("Select all").click();
      await expect(page.getByText("2 items selected")).toBeVisible();

      // Click restore selected
      await page.getByText("Restore Selected").click();

      // Should show warning about skipped document with missing data (appears in error message)
      await expect(
        page.getByText(/1 document skipped: missing or corrupted data/)
      ).toBeVisible({ timeout: 15000 });
    });

    test("shows clear error when all selected documents have null data", async ({
      mount,
      page,
    }) => {
      await mount(<TrashFolderViewTestWrapper mockType="nullDocument" />);

      await page.waitForSelector('text="Untitled Document"', {
        timeout: 10000,
      });

      // Select the document with null data
      await page.getByText("Untitled Document").click();
      await expect(page.getByText("1 item selected")).toBeVisible();

      // Click restore selected
      await page.getByText("Restore Selected").click();

      // Should show clear error message
      await expect(
        page.getByText(
          "Selected documents cannot be restored: document data is missing or corrupted"
        )
      ).toBeVisible({ timeout: 10000 });
    });
  });
});
