import React from "react";
import { test, expect } from "./utils/coverage";
import { SidebarControlBarTestWrapper } from "./SidebarControlBarTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("SidebarControlBar", () => {
  test("renders control bar with search and filter controls", async ({
    mount,
    page,
  }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    // Verify search input is visible
    await expect(page.getByPlaceholder("Search in content...")).toBeVisible({
      timeout: 10000,
    });

    // Verify Content Types dropdown header is visible
    await expect(page.getByText("Content Types")).toBeVisible();

    // Verify sort dropdown is present (os-legal Dropdown)
    const sortDropdown = page.locator(".oc-dropdown");
    await expect(sortDropdown).toBeVisible();

    await docScreenshot(page, "knowledge-base--sidebar-control-bar--default");

    await component.unmount();
  });

  test("sort dropdown shows sort options", async ({ mount, page }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    // Click the sort dropdown trigger to open it
    const sortDropdown = page.locator(".oc-dropdown");
    await expect(sortDropdown).toBeVisible({ timeout: 10000 });
    await sortDropdown.locator(".oc-dropdown__trigger").click();

    // Verify all sort options are visible
    await expect(
      page.locator(".oc-dropdown__option", { hasText: "Page Number" })
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator(".oc-dropdown__option", { hasText: "Content Type" })
    ).toBeVisible();
    await expect(
      page.locator(".oc-dropdown__option", { hasText: "Date Created" })
    ).toBeVisible();

    await docScreenshot(
      page,
      "knowledge-base--sidebar-control-bar--sort-options"
    );

    await component.unmount();
  });

  test("content type filters are visible", async ({ mount, page }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    // Click the Content Types dropdown to expand it
    await expect(page.getByText("Content Types")).toBeVisible({
      timeout: 10000,
    });
    await page.getByText("Content Types").click();

    // Verify content type filter options appear
    await expect(page.getByText("Notes")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Annotations")).toBeVisible();
    await expect(page.getByText("Relationships")).toBeVisible();

    // Verify quick action buttons
    await expect(page.getByText("Select All")).toBeVisible();
    await expect(page.getByText("Clear All")).toBeVisible();

    await component.unmount();
  });

  test("returns null in chat mode", async ({ mount, page }) => {
    const component = await mount(
      <SidebarControlBarTestWrapper initialViewMode="chat" />
    );

    // In chat mode, the control bar should not render
    await expect(page.getByPlaceholder("Search in content...")).not.toBeVisible(
      { timeout: 5000 }
    );

    await component.unmount();
  });

  test("selecting a sort option updates the sort trigger", async ({
    mount,
    page,
  }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    const sortDropdown = page.locator(".oc-dropdown");
    await expect(sortDropdown).toBeVisible({ timeout: 10000 });
    // Default sort is "page" — the trigger reads "Page Number".
    await expect(sortDropdown).toContainText("Page Number");

    await sortDropdown.locator(".oc-dropdown__trigger").click();
    await page
      .locator(".oc-dropdown__option", { hasText: "Date Created" })
      .click();

    // onSortChange fired; the trigger now reflects the chosen option.
    await expect(sortDropdown).toContainText("Date Created");

    await component.unmount();
  });

  test("toggling a content type updates the selected count", async ({
    mount,
    page,
  }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    // All three content types start selected — the header shows a "3" badge.
    const header = page.getByText("Content Types");
    await expect(header).toBeVisible({ timeout: 10000 });
    await header.click();

    // Deselecting "Notes" drops the selected count to 2.
    await page.getByText("Notes", { exact: true }).click();

    await expect(
      page
        .locator("div")
        .filter({ hasText: /^Content Types2$/ })
        .first()
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("Clear All then Select All toggles every content type", async ({
    mount,
    page,
  }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    await page.getByText("Content Types").click();

    // Clear All deselects everything — the count badge disappears.
    await page.getByText("Clear All").click();
    await expect(
      page
        .locator("div")
        .filter({ hasText: /^Content Types$/ })
        .first()
    ).toBeVisible({ timeout: 5000 });

    // Select All re-selects all three.
    await page.getByText("Select All").click();
    await expect(
      page
        .locator("div")
        .filter({ hasText: /^Content Types3$/ })
        .first()
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("typing in the search field accepts input", async ({ mount, page }) => {
    const component = await mount(<SidebarControlBarTestWrapper />);

    const search = page.getByPlaceholder("Search in content...");
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("indemnification");
    await expect(search).toHaveValue("indemnification");

    await component.unmount();
  });
});
