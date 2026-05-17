// Direct smoke tests for the three Documents view components extracted in
// PR #1677. The parent Documents.ct.tsx covers the integration paths, but
// codecov flagged uncovered branches inside each view (keyboard handler,
// processing overlay, ``Untitled`` fallback, kebab menu when no row is
// active, etc.). Mounting each view in isolation with permissive props
// is the cheapest way to drive those leaf branches.
import React from "react";
import { test, expect } from "./utils/coverage";
import {
  DocumentsGridViewHarness,
  DocumentsListViewHarness,
  DocumentsCompactViewHarness,
} from "./DocumentsViewsTestWrappers";

test.describe("DocumentsGridView - leaf branches", () => {
  test("renders processing overlay + untitled fallback and fires every handler", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DocumentsGridViewHarness />);

    // ``Untitled`` fallback path on a doc with no title.
    await expect(page.locator("text=Untitled").first()).toBeVisible();

    // backendLock=true -> ProcessingOverlay branch.
    await expect(page.locator("text=Processing...").first()).toBeVisible();

    // doc.icon present -> CardThumbnail branch.
    await expect(page.locator('img[alt="With icon"]')).toBeVisible();

    // doc.pageCount falsy -> "Document" label branch.
    await expect(page.locator("text=Document").first()).toBeVisible();

    // Row click drives onDocumentClick.
    const firstCard = page
      .locator('[role="button"][data-testid="document-card"]')
      .first();
    await firstCard.click();
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Right-click drives row-level onContextMenu.
    await firstCard.click({ button: "right" });
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    // Enter key drives keyboard onDocumentClick branch.
    await firstCard.press("Enter");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Space key drives the same branch.
    await firstCard.press(" ");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Kebab menu drives the second onContextMenu trigger path.
    await firstCard.locator('button[aria-label="Open menu"]').click();
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    // Checkbox onSelect path (stopPropagation on the wrapper).
    await firstCard.locator('input[type="checkbox"]').click();
    await expect(page.locator("text=selected-doc-1")).toBeVisible();

    await component.unmount();
  });
});

test.describe("DocumentsListView - leaf branches", () => {
  test("fires per-row handlers and select-all + processing chip branches", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DocumentsListViewHarness />);

    // Processing chip branch for backendLock=true row.
    await expect(page.locator("text=Processing").first()).toBeVisible();
    // Processed chip branch for backendLock=false row.
    await expect(page.locator("text=Processed").first()).toBeVisible();

    // Select-all checkbox in the rowgroup header.
    const header = page.locator('[role="rowgroup"]');
    await header.locator('input[type="checkbox"]').click();
    await expect(page.locator("text=select-all-fired")).toBeVisible();

    const firstRow = page
      .locator('[role="row"][data-testid="document-card"]')
      .first();

    // Per-row checkbox onSelect.
    await firstRow.locator('input[type="checkbox"]').click();
    await expect(page.locator("text=selected-doc-1")).toBeVisible();

    // Row click -> onDocumentClick.
    await firstRow.click();
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Right-click -> onContextMenu (row variant).
    await firstRow.click({ button: "right" });
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    // Enter key -> keyboard branch.
    await firstRow.press("Enter");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Space key -> same branch.
    await firstRow.press(" ");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Kebab menu -> onContextMenu (button variant).
    await firstRow.locator('button[aria-label="Open menu"]').click();
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    await component.unmount();
  });
});

test.describe("DocumentsCompactView - leaf branches", () => {
  test("fires per-row handlers including keyboard and kebab paths", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DocumentsCompactViewHarness />);

    // Untitled fallback inside the row.
    await expect(page.locator("text=Untitled").first()).toBeVisible();

    const firstRow = page
      .locator('[role="listitem"][data-testid="document-card"]')
      .first();

    // Per-row checkbox onSelect.
    await firstRow.locator('input[type="checkbox"]').click();
    await expect(page.locator("text=selected-doc-1")).toBeVisible();

    // Row click -> onDocumentClick.
    await firstRow.click();
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Right-click -> onContextMenu.
    await firstRow.click({ button: "right" });
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    // Enter key -> keyboard branch.
    await firstRow.press("Enter");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Space key -> same branch.
    await firstRow.press(" ");
    await expect(page.locator("text=clicked-doc-1")).toBeVisible();

    // Kebab menu -> onContextMenu (button variant).
    await firstRow.locator('button[aria-label="Open menu"]').click();
    await expect(page.locator("text=context-doc-1")).toBeVisible();

    await component.unmount();
  });
});
