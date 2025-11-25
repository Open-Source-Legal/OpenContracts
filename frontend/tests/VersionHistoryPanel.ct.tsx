import { test, expect } from "@playwright/experimental-ct-react";
import { VersionHistoryPanelTestWrapper } from "./VersionHistoryPanelTestWrapper";

test.describe("VersionHistoryPanel", () => {
  test("renders modal when open", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} />
    );

    // Modal should be visible
    await expect(page.locator(".ui.modal")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Version History")).toBeVisible();
    await expect(page.getByText("Test Document")).toBeVisible();
  });

  test("does not render when closed", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={false} />
    );

    // Modal should not be visible
    await expect(page.locator(".ui.modal")).not.toBeVisible();
  });

  test("shows loading indicator or content after mount", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} />
    );

    // Loading state may be transient, so check for either loading or content
    // The component should show one or the other
    const hasLoading = await page
      .getByText("Loading version history...")
      .isVisible()
      .catch(() => false);
    const hasContent = await page
      .getByText("Version 3")
      .isVisible()
      .catch(() => false);

    // Should have either loading indicator or actual content
    expect(hasLoading || hasContent).toBe(true);
  });

  test("displays version list after loading", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} />
    );

    // Wait for loading to finish
    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // All versions should be displayed
    await expect(page.getByText("Version 3")).toBeVisible();
    await expect(page.getByText("Version 2")).toBeVisible();
    await expect(page.getByText("Version 1")).toBeVisible();

    // Current version should be marked
    await expect(page.getByText("(Current)")).toBeVisible();
  });

  test("shows version metadata correctly", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Check usernames are displayed
    await expect(page.getByText("user1").first()).toBeVisible();
    await expect(page.getByText("user2")).toBeVisible();

    // Check change types are displayed
    await expect(page.getByText("CONTENT UPDATE")).toBeVisible();
    await expect(page.getByText("MINOR EDIT")).toBeVisible();
    await expect(page.getByText("INITIAL")).toBeVisible();

    // Check file sizes are formatted (1048576 bytes = 1024 KB = 1 MB)
    // The formatBytes function converts to MB if KB >= 1024
    await expect(page.getByText("1.00 MB")).toBeVisible();
    await expect(page.getByText("500.0 KB")).toBeVisible();
    await expect(page.getByText("250.0 KB")).toBeVisible();
  });

  test("shows error message on fetch failure", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} mockType="error" />
    );

    await page.waitForSelector("text=Failed to load version history", {
      timeout: 10000,
    });

    await expect(
      page.getByText("Failed to load version history")
    ).toBeVisible();
  });

  test("shows empty state when no versions", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} mockType="empty" />
    );

    await page.waitForSelector("text=No Version History", { timeout: 10000 });

    await expect(page.getByText("No Version History")).toBeVisible();
    await expect(
      page.getByText("This document has no previous versions.")
    ).toBeVisible();
  });

  test("calls onClose when close button clicked", async ({ mount, page }) => {
    let closed = false;

    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        onClose={() => {
          closed = true;
        }}
      />
    );

    await page.waitForSelector("text=Version History", { timeout: 10000 });

    // Click close button
    await page.getByRole("button", { name: "Close" }).click();

    expect(closed).toBe(true);
  });

  test("shows restore button for non-current versions", async ({
    mount,
    page,
  }) => {
    let restoreId = "";

    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        onRestore={(versionId) => {
          restoreId = versionId;
        }}
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 2 (not current)
    await page.getByText("Version 2").click();

    // Restore button should appear
    await expect(page.getByText("Restore This Version")).toBeVisible();

    // Click restore
    await page.getByText("Restore This Version").click();

    expect(restoreId).toBe("v2");
  });

  test("shows download button for non-current versions", async ({
    mount,
    page,
  }) => {
    let downloadId = "";

    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        onDownload={(versionId) => {
          downloadId = versionId;
        }}
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 1 (not current)
    await page.getByText("Version 1").click();

    // Download button should appear
    await expect(page.getByRole("button", { name: /Download/ })).toBeVisible();

    // Click download
    await page.getByRole("button", { name: /Download/ }).click();

    expect(downloadId).toBe("v1");
  });

  test("does not show restore/download for current version", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        onRestore={() => {}}
        onDownload={() => {}}
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on current version (v3)
    await page.getByText("Version 3 (Current)").click();

    // Should show info message instead of restore/download buttons
    await expect(page.getByText("This is the current version")).toBeVisible();
    await expect(page.getByText("Restore This Version")).not.toBeVisible();
  });

  test("sorts versions by version number descending", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Get all version titles in order
    const versionCards = page.locator("text=/Version \\d+/");
    const count = await versionCards.count();

    expect(count).toBeGreaterThanOrEqual(3);

    // First visible should be Version 3
    const firstVersion = await versionCards.first().textContent();
    expect(firstVersion).toContain("3");
  });

  test("clicking version card selects it", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} onRestore={() => {}} />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 2
    await page.getByText("Version 2").click();

    // Wait a bit for the click to register
    await page.waitForTimeout(200);

    // Version 2 should show action buttons (since it's selected and not current)
    await expect(page.getByText("Restore This Version")).toBeVisible();
  });

  test("shows success message after successful restore", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        mutationMockType="success"
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 2 to select it
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);

    // Click restore button
    await page.getByText("Restore This Version").click();

    // Should show success message
    await expect(page.getByText("Version Restored")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Successfully restored to version 4")
    ).toBeVisible();
  });

  test("shows error message on restore business logic failure", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        mutationMockType="failure"
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 2 to select it
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);

    // Click restore button
    await page.getByText("Restore This Version").click();

    // Should show error message
    await expect(page.getByText("Restore Failed")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Permission denied")).toBeVisible();
  });

  test("shows error message on restore network error", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper isOpen={true} mutationMockType="error" />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Click on version 2 to select it
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);

    // Click restore button
    await page.getByText("Restore This Version").click();

    // Should show error message
    await expect(page.getByText("Restore Failed")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Network error occurred")).toBeVisible();
  });

  test("success message can be dismissed", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        mutationMockType="success"
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Trigger restore
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);
    await page.getByText("Restore This Version").click();

    // Wait for success message
    await expect(page.getByText("Version Restored")).toBeVisible({
      timeout: 10000,
    });

    // Dismiss the message
    await page.locator(".message.positive .close.icon").click();

    // Message should be gone
    await expect(page.getByText("Version Restored")).not.toBeVisible();
  });

  test("error message can be dismissed", async ({ mount, page }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        mutationMockType="failure"
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Trigger restore failure
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);
    await page.getByText("Restore This Version").click();

    // Wait for error message
    await expect(page.getByText("Restore Failed")).toBeVisible({
      timeout: 10000,
    });

    // Dismiss the message
    await page.locator(".message.negative .close.icon").click();

    // Message should be gone
    await expect(page.getByText("Restore Failed")).not.toBeVisible();
  });

  test("success message auto-dismisses after 5 seconds", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionHistoryPanelTestWrapper
        isOpen={true}
        mutationMockType="success"
      />
    );

    await page.waitForSelector("text=Version 3", { timeout: 10000 });

    // Trigger restore
    await page.getByText("Version 2").click();
    await page.waitForTimeout(100);
    await page.getByText("Restore This Version").click();

    // Wait for success message
    await expect(page.getByText("Version Restored")).toBeVisible({
      timeout: 10000,
    });

    // Wait for auto-dismiss (5 seconds + buffer)
    await page.waitForTimeout(6000);

    // Message should be gone
    await expect(page.getByText("Version Restored")).not.toBeVisible();
  });
});
