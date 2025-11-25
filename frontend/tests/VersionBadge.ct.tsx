import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { VersionBadge } from "../src/components/documents/VersionBadge";

test.describe("VersionBadge", () => {
  test("renders version number correctly", async ({ mount, page }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={3}
        hasHistory={false}
        isLatest={true}
        versionCount={1}
      />
    );

    await expect(component.getByText("v3")).toBeVisible({ timeout: 10000 });
  });

  test("displays correct cursor for no version history", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={1}
        hasHistory={false}
        isLatest={true}
        versionCount={1}
      />
    );

    // Badge with no history should not have pointer cursor
    await expect(component.getByText("v1")).toBeVisible({ timeout: 10000 });

    // Check it doesn't have clickable cursor - find parent of v1 text
    const badge = component.getByText("v1").locator("..");
    const cursor = await badge.evaluate((el) => getComputedStyle(el).cursor);
    expect(cursor).toBe("default");
  });

  test("displays pointer cursor for latest version with history", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={2}
        hasHistory={true}
        isLatest={true}
        versionCount={2}
      />
    );

    // Badge with history should have pointer cursor
    await expect(component.getByText("v2")).toBeVisible({ timeout: 10000 });

    // Should have pointer cursor since has history and role=button
    const badge = page.getByRole("button");
    const cursor = await badge.evaluate((el) => getComputedStyle(el).cursor);
    expect(cursor).toBe("pointer");
  });

  test("displays version count indicator when has history", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={3}
        hasHistory={true}
        isLatest={true}
        versionCount={5}
      />
    );

    await expect(component.getByText("v3")).toBeVisible({ timeout: 10000 });
    // Version count should be displayed (• 5)
    await expect(component.getByText("5")).toBeVisible();
  });

  test("calls onClick when clicked with history", async ({ mount, page }) => {
    let clicked = false;

    const component = await mount(
      <VersionBadge
        versionNumber={2}
        hasHistory={true}
        isLatest={true}
        versionCount={2}
        onClick={() => {
          clicked = true;
        }}
      />
    );

    // Use role=button selector which is more reliable
    await page.getByRole("button").click();
    expect(clicked).toBe(true);
  });

  test("does not call onClick when no history", async ({ mount, page }) => {
    let clicked = false;

    const component = await mount(
      <VersionBadge
        versionNumber={1}
        hasHistory={false}
        isLatest={true}
        versionCount={1}
        onClick={() => {
          clicked = true;
        }}
      />
    );

    await expect(component.getByText("v1")).toBeVisible({ timeout: 10000 });
    await component.getByText("v1").click();

    expect(clicked).toBe(false);
  });

  test("has correct ARIA attributes with history", async ({ mount, page }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={3}
        hasHistory={true}
        isLatest={true}
        versionCount={3}
        onClick={() => {}}
      />
    );

    const badge = page.getByRole("button");
    await expect(badge).toBeVisible({ timeout: 10000 });

    // Check aria-label contains version info
    const ariaLabel = await badge.getAttribute("aria-label");
    expect(ariaLabel).toContain("Version 3");
    expect(ariaLabel).toContain("click to view history");
  });

  test("has no button role without history", async ({ mount, page }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={1}
        hasHistory={false}
        isLatest={true}
        versionCount={1}
      />
    );

    await expect(component.getByText("v1")).toBeVisible({ timeout: 10000 });

    // Should not have button role when not clickable
    const badge = component.getByText("v1").locator("..");
    const role = await badge.getAttribute("role");
    expect(role).toBeNull();
  });

  test("shows tooltip on hover for documents with history", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={2}
        hasHistory={true}
        isLatest={true}
        versionCount={3}
      />
    );

    const badge = page.getByRole("button");
    await expect(badge).toBeVisible({ timeout: 10000 });

    // Hover over badge to trigger tooltip
    await badge.hover();
    await page.waitForTimeout(500);

    // Tooltip should appear with version information
    await expect(page.getByText("Version Information")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Current: v2")).toBeVisible();
    await expect(page.getByText("Total versions: 3")).toBeVisible();
    await expect(page.getByText("Click to view version history")).toBeVisible();
  });

  test("displays outdated warning for non-latest version", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={2}
        hasHistory={true}
        isLatest={false}
        versionCount={3}
      />
    );

    const badge = page.getByRole("button");
    await expect(badge).toBeVisible({ timeout: 10000 });

    // Hover to show tooltip
    await badge.hover();
    await page.waitForTimeout(500);

    // Should show outdated message
    await expect(page.getByText("Outdated Version")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByText("A newer version is available (you are viewing v2 of 3)")
    ).toBeVisible();
  });

  test("badge is focusable when has history", async ({ mount, page }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={3}
        hasHistory={true}
        isLatest={true}
        versionCount={3}
        onClick={() => {}}
      />
    );

    const badge = page.getByRole("button");
    await expect(badge).toBeVisible({ timeout: 10000 });

    // Check tabIndex for keyboard accessibility
    const tabIndex = await badge.getAttribute("tabindex");
    expect(tabIndex).toBe("0");
  });

  test("applies custom className", async ({ mount, page }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={2}
        hasHistory={true}
        isLatest={true}
        versionCount={2}
        className="custom-test-class"
      />
    );

    const badge = page.getByRole("button");
    await expect(badge).toBeVisible({ timeout: 10000 });
    await expect(badge).toHaveClass(/custom-test-class/);
  });

  test("renders without tooltip when versionNumber is 1 and no history", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <VersionBadge
        versionNumber={1}
        hasHistory={false}
        isLatest={true}
        versionCount={1}
      />
    );

    await expect(component.getByText("v1")).toBeVisible({ timeout: 10000 });

    // Hover and check no tooltip appears
    await component.getByText("v1").hover();
    await page.waitForTimeout(300);

    // No tooltip should appear for v1 with no history
    await expect(page.getByText("Version Information")).not.toBeVisible();
    await expect(page.getByText("Outdated Version")).not.toBeVisible();
  });
});
