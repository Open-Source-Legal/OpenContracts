import React from "react";
import { test, expect } from "./utils/coverage";
import { ExportListTestWrapper } from "./ExportListTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ExportList", () => {
  test("renders table with export items", async ({ mount, page }) => {
    const component = await mount(<ExportListTestWrapper />);

    // Table headers should be visible
    await expect(page.locator("text=Description")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=Requested")).toBeVisible();
    await expect(page.locator("text=Started")).toBeVisible();
    await expect(page.locator("text=Completed")).toBeVisible();
    await expect(page.locator("text=Actions")).toBeVisible();

    // Export names should be visible
    await expect(page.locator("text=Contract Export Q1 2024")).toBeVisible();
    await expect(page.locator("text=NDA Analysis Export")).toBeVisible();
    await expect(page.locator("text=Full Corpus Backup")).toBeVisible();

    await docScreenshot(page, "exports--list--with-data");
    await component.unmount();
  });

  test("renders empty table when no items", async ({ mount, page }) => {
    const component = await mount(<ExportListTestWrapper items={[]} />);

    // Headers should still be visible
    await expect(page.locator("text=Description")).toBeVisible({
      timeout: 5000,
    });

    // No export items
    await expect(page.locator("text=Contract Export")).not.toBeVisible();

    await docScreenshot(page, "exports--list--empty");
    await component.unmount();
  });

  test("shows delete button for each item", async ({ mount, page }) => {
    const component = await mount(<ExportListTestWrapper />);

    await expect(page.locator("text=Contract Export Q1 2024")).toBeVisible({
      timeout: 5000,
    });

    // Delete buttons should be present (one per row)
    const deleteButtons = page.locator('button[aria-label="Delete export"]');
    expect(await deleteButtons.count()).toBe(3);

    await component.unmount();
  });

  test("shows download button only for completed exports", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ExportListTestWrapper />);

    await expect(page.locator("text=Contract Export Q1 2024")).toBeVisible({
      timeout: 5000,
    });

    // Only the first export has finished set, so only 1 download button
    const downloadButtons = page.locator(
      'button[aria-label="Download export"]'
    );
    expect(await downloadButtons.count()).toBe(1);

    await component.unmount();
  });

  test("shows loading overlay on initial load (no items yet)", async ({
    mount,
    page,
  }) => {
    // The overlay covers the table only when ``loading && itemCount === 0``
    // — fetchMore keeps existing rows visible without dimming them.
    const component = await mount(
      <ExportListTestWrapper items={[]} loading={true} />
    );

    await expect(page.locator("text=Loading Exports...")).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "exports--list--loading");
    await component.unmount();
  });

  test("does not cover existing rows during fetchMore (loading=true with items)", async ({
    mount,
    page,
  }) => {
    // When rows are already on screen, a refetch / fetchMore must not paint
    // the modal overlay over them; the FetchMoreFooter spinner takes over.
    const component = await mount(<ExportListTestWrapper loading={true} />);

    await expect(page.locator("text=Contract Export Q1 2024")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=Loading Exports...")).not.toBeVisible();

    await component.unmount();
  });
});
