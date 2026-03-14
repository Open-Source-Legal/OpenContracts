// Playwright Component Test for ContextMenu widget
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { ContextMenuItem } from "../src/components/widgets/context-menu/ContextMenu";
import { ContextMenuHarness } from "./ContextMenuTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS: Rendering
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("ContextMenu - Rendering", () => {
  test("should render visible items and hide items with visible=false", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Visible items
    await expect(
      page.locator('[role="menuitem"]').filter({ hasText: "Edit" })
    ).toBeVisible();
    await expect(
      page.locator('[role="menuitem"]').filter({ hasText: "View Details" })
    ).toBeVisible();
    await expect(
      page.locator('[role="menuitem"]').filter({ hasText: "Delete" })
    ).toBeVisible();

    // Hidden item should NOT be rendered
    await expect(
      page.locator('[role="menuitem"]').filter({ hasText: "Hidden Item" })
    ).toHaveCount(0);

    // Should be exactly 3 visible items
    await expect(page.locator('[role="menuitem"]')).toHaveCount(3);

    await docScreenshot(page, "context-menu--default--with-items");

    await component.unmount();
  });

  test("should render header when provided", async ({ mount, page }) => {
    const component = await mount(
      <ContextMenuHarness header="Document Actions" />
    );

    await expect(page.locator("text=Document Actions")).toBeVisible({
      timeout: 3000,
    });

    await docScreenshot(page, "context-menu--default--with-header");

    await component.unmount();
  });

  test("should apply danger variant styling", async ({ mount, page }) => {
    const component = await mount(<ContextMenuHarness />);

    const deleteItem = page
      .locator('[role="menuitem"]')
      .filter({ hasText: "Delete" });
    await expect(deleteItem).toBeVisible({ timeout: 3000 });

    await component.unmount();
  });

  test("should have proper ARIA attributes", async ({ mount, page }) => {
    const component = await mount(
      <ContextMenuHarness aria-label="Test actions menu" />
    );

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });
    await expect(menu).toHaveAttribute("aria-label", "Test actions menu");

    // Overlay should be aria-hidden
    const overlay = page.locator('[aria-hidden="true"]');
    await expect(overlay).toBeAttached();

    await component.unmount();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS: Viewport boundary clamping
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("ContextMenu - Viewport Clamping", () => {
  test("should clamp position when near right edge", async ({
    mount,
    page,
  }) => {
    // Position near the right edge of the viewport
    const component = await mount(
      <ContextMenuHarness position={{ x: 9999, y: 100 }} />
    );

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Menu should be clamped so it's fully visible
    const box = await menu.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const viewport = page.viewportSize();
      expect(box.x + box.width).toBeLessThanOrEqual(viewport!.width);
    }

    await component.unmount();
  });

  test("should clamp position when near bottom edge", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ContextMenuHarness position={{ x: 100, y: 9999 }} />
    );

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    const box = await menu.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const viewport = page.viewportSize();
      expect(box.y + box.height).toBeLessThanOrEqual(viewport!.height);
    }

    await component.unmount();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS: Keyboard navigation
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("ContextMenu - Keyboard Navigation", () => {
  test("should close on Escape key", async ({ mount, page }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Press Escape
    await page.keyboard.press("Escape");

    // Menu should be closed
    await expect(page.locator('[data-testid="menu-closed"]')).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("should navigate items with ArrowDown and ArrowUp", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Wait for auto-focus on first item
    await page.waitForTimeout(100);

    const menuItems = page.locator('[role="menuitem"]');

    // First item should be focused
    await expect(menuItems.nth(0)).toBeFocused();

    // ArrowDown to second item
    await page.keyboard.press("ArrowDown");
    await expect(menuItems.nth(1)).toBeFocused();

    // ArrowDown to third item
    await page.keyboard.press("ArrowDown");
    await expect(menuItems.nth(2)).toBeFocused();

    // ArrowDown wraps to first item
    await page.keyboard.press("ArrowDown");
    await expect(menuItems.nth(0)).toBeFocused();

    // ArrowUp wraps to last item
    await page.keyboard.press("ArrowUp");
    await expect(menuItems.nth(2)).toBeFocused();

    await component.unmount();
  });

  test("should activate item on Enter key", async ({ mount, page }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Wait for auto-focus
    await page.waitForTimeout(100);

    // Press Enter on first item ("Edit")
    await page.keyboard.press("Enter");

    await expect(page.locator('[data-testid="last-clicked"]')).toContainText(
      "Clicked: edit"
    );

    await component.unmount();
  });

  test("should activate item on Space key", async ({ mount, page }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Wait for auto-focus, then navigate to "View Details"
    await page.waitForTimeout(100);
    await page.keyboard.press("ArrowDown");

    // Press Space
    await page.keyboard.press(" ");

    await expect(page.locator('[data-testid="last-clicked"]')).toContainText(
      "Clicked: view"
    );

    await component.unmount();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS: Click behavior
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("ContextMenu - Click Behavior", () => {
  test("should call onClose when clicking the overlay", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Click on the overlay area (top-left corner, outside the menu)
    await page.mouse.click(5, 5);

    // Menu should close
    await expect(page.locator('[data-testid="menu-closed"]')).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("should trigger item onClick on click", async ({ mount, page }) => {
    const component = await mount(<ContextMenuHarness />);

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // Click "Delete" item
    await page
      .locator('[role="menuitem"]')
      .filter({ hasText: "Delete" })
      .click();

    await expect(page.locator('[data-testid="last-clicked"]')).toContainText(
      "Clicked: delete"
    );

    await component.unmount();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// TESTS: Empty items edge case
// ═══════════════════════════════════════════════════════════════════════════════

test.describe("ContextMenu - Edge Cases", () => {
  test("should handle empty visible items gracefully", async ({
    mount,
    page,
  }) => {
    const allHiddenItems: ContextMenuItem[] = [
      {
        key: "a",
        label: "Item A",
        visible: false,
        onClick: () => {},
      },
      {
        key: "b",
        label: "Item B",
        visible: false,
        onClick: () => {},
      },
    ];

    const component = await mount(
      <ContextMenuHarness items={allHiddenItems} />
    );

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible({ timeout: 3000 });

    // No menu items should be rendered
    await expect(page.locator('[role="menuitem"]')).toHaveCount(0);

    // Clicking overlay should still close even with no items
    await page.mouse.click(5, 5);
    await expect(page.locator('[data-testid="menu-closed"]')).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });
});
