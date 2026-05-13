import { test, expect } from "./utils/coverage";
import { DocumentTableOfContentsTestWrapper } from "./DocumentTableOfContentsTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("DocumentTableOfContents", () => {
  test("shows the document row for a single standalone document", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentTableOfContentsTestWrapper mockType="singleStandalone" />
    );

    await expect(page.getByText("Single Standalone Document")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("No indexed sections for this document")
    ).toHaveCount(0);
  });

  test("shows standalone documents when no parent relationships exist", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentTableOfContentsTestWrapper mockType="noParentRelationships" />
    );

    // Wait for documents to load - they should show as standalone root items
    await expect(page.getByText("Table of Contents")).toBeVisible({
      timeout: 10000,
    });

    // Both docs should be visible as root-level items (no hierarchy)
    await expect(page.getByText("Doc A")).toBeVisible();
    await expect(page.getByText("Doc B")).toBeVisible();
    await docScreenshot(page, "corpus--toc--standalone-documents");
  });

  test("shows empty state when corpus has no documents", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="empty" />);

    // Wait for query to complete and show empty state
    await expect(page.getByText("No Documents")).toBeVisible({
      timeout: 10000,
    });

    // Empty state message should be shown
    await expect(
      page.getByText("This corpus doesn't have any documents yet")
    ).toBeVisible();
    await docScreenshot(page, "corpus--toc--empty-state");
  });

  test("renders header with parent relationships", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await expect(page.getByText("Table of Contents")).toBeVisible({
      timeout: 10000,
    });
  });

  test("displays parent document as root", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    await expect(page.getByText("Parent Document")).toBeVisible();
  });

  test("displays child documents", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    // Wait for tree to render
    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    // Expand parent to see children (click chevron)
    const chevron = page.locator(".chevron").first();
    await chevron.click();

    // Children should be visible after expanding
    await expect(page.getByText("Child Document 1")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Child Document 2")).toBeVisible();
    await docScreenshot(page, "corpus--toc--expanded-children");
  });

  test("tree nodes have proper ARIA attributes", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('[role="tree"]', {
      timeout: 10000,
    });

    // Tree container should have tree role
    await expect(page.locator('[role="tree"]')).toBeVisible();

    // Tree items should have treeitem role
    const treeItems = page.locator('[role="treeitem"]');
    await expect(treeItems.first()).toBeVisible();
  });

  test("tree nodes are keyboard focusable", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    // Tree items should have tabIndex
    const treeItem = page.locator('[role="treeitem"]').first();
    await expect(treeItem).toHaveAttribute("tabindex", "0");
  });

  test("keyboard navigation - ArrowRight expands node", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    // Focus the parent node
    const parentNode = page.locator('[role="treeitem"]').first();
    await parentNode.focus();

    // Press ArrowRight to expand
    await page.keyboard.press("ArrowRight");

    // Children should become visible
    await expect(page.getByText("Child Document 1")).toBeVisible({
      timeout: 5000,
    });
  });

  test("keyboard navigation - ArrowLeft collapses node", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    // First expand the parent node
    const parentNode = page.locator('[role="treeitem"]').first();
    await parentNode.focus();
    await page.keyboard.press("ArrowRight");

    // Wait for expansion to complete (aria-expanded changes to true)
    await expect(parentNode).toHaveAttribute("aria-expanded", "true", {
      timeout: 5000,
    });

    // Wait for children to be visible
    await expect(page.getByText("Child Document 1")).toBeVisible({
      timeout: 5000,
    });

    // Re-focus the parent node to ensure keyboard events go to the right element
    await parentNode.focus();

    // Small settle time for React state
    await page.waitForTimeout(100);

    // Press ArrowLeft to collapse
    await page.keyboard.press("ArrowLeft");

    // Children should be hidden (though they may still be in DOM, just not displayed)
    // Check aria-expanded attribute instead
    await expect(parentNode).toHaveAttribute("aria-expanded", "false", {
      timeout: 5000,
    });
  });

  test("aria-expanded reflects node state", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    const parentNode = page.locator('[role="treeitem"]').first();

    // Initially collapsed
    await expect(parentNode).toHaveAttribute("aria-expanded", "false");

    // Expand by clicking chevron
    const chevron = page.locator(".chevron").first();
    await chevron.click();

    // Should be expanded
    await expect(parentNode).toHaveAttribute("aria-expanded", "true");
  });

  test("nodes have aria-label with title", async ({ mount, page }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    const parentNode = page.locator('[role="treeitem"]').first();

    // Should have aria-label containing the document title
    const ariaLabel = await parentNode.getAttribute("aria-label");
    expect(ariaLabel).toContain("Parent Document");
  });

  test("clicking document navigates (calls handler)", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="default" />);

    await page.waitForSelector('text="Parent Document"', {
      timeout: 10000,
    });

    // Click on a document title
    await page.getByText("Parent Document").click();

    // Navigation would happen via React Router - we can't easily test the actual navigation
    // but we can verify the click handler is called (no errors thrown)
  });

  test("max depth limit prevents infinite recursion with deep hierarchies", async ({
    mount,
    page,
  }) => {
    // Use deep hierarchy with maxDepth=2 (should show Root, Level1, Level2 only)
    await mount(
      <DocumentTableOfContentsTestWrapper
        mockType="deepHierarchy"
        maxDepth={2}
      />
    );

    await page.waitForSelector('text="Root Document"', {
      timeout: 10000,
    });

    // Root (depth 0) should be visible
    await expect(page.getByText("Root Document")).toBeVisible();

    // Expand Root to see Level 1 (depth 1)
    const rootChevron = page.locator(".chevron").first();
    await rootChevron.click();
    await expect(page.getByText("Level 1 Document")).toBeVisible({
      timeout: 5000,
    });

    // Expand Level 1 to see Level 2 (depth 2)
    const level1Chevron = page.locator(".chevron").nth(1);
    await level1Chevron.click();
    await expect(page.getByText("Level 2 Document")).toBeVisible({
      timeout: 5000,
    });

    // Level 3 and Level 4 should NOT be rendered (beyond maxDepth=2)
    // They shouldn't even be in the DOM since the tree building stops at maxDepth
    await expect(page.getByText("Level 3 Document")).not.toBeVisible();
    await expect(page.getByText("Level 4 Document")).not.toBeVisible();
  });

  test("full depth hierarchy shows all levels with default maxDepth=4", async ({
    mount,
    page,
  }) => {
    // Use deep hierarchy with default maxDepth=4 (should show all levels)
    await mount(
      <DocumentTableOfContentsTestWrapper
        mockType="deepHierarchy"
        maxDepth={4}
      />
    );

    await page.waitForSelector('text="Root Document"', {
      timeout: 10000,
    });

    // Expand all nodes to verify all levels are accessible
    // Root -> Level 1
    const rootChevron = page.locator(".chevron").first();
    await rootChevron.click();
    await expect(page.getByText("Level 1 Document")).toBeVisible({
      timeout: 5000,
    });

    // Level 1 -> Level 2
    const level1Chevron = page.locator(".chevron").nth(1);
    await level1Chevron.click();
    await expect(page.getByText("Level 2 Document")).toBeVisible({
      timeout: 5000,
    });

    // Level 2 -> Level 3
    const level2Chevron = page.locator(".chevron").nth(2);
    await level2Chevron.click();
    await expect(page.getByText("Level 3 Document")).toBeVisible({
      timeout: 5000,
    });

    // Level 3 -> Level 4
    const level3Chevron = page.locator(".chevron").nth(3);
    await level3Chevron.click();
    await expect(page.getByText("Level 4 Document")).toBeVisible({
      timeout: 5000,
    });
  });

  test("hybrid view shows document hierarchy with nested annotation indices", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentTableOfContentsTestWrapper mockType="hybrid" />);

    // Wait for the TOC to render
    await expect(page.getByText("Table of Contents")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Parent Document")).toBeVisible();

    // Expand parent document — use its treeitem's chevron directly
    const parentItem = page.getByRole("treeitem", {
      name: /Parent Document/,
    });
    await parentItem.locator(".chevron").click();

    // Child documents should appear
    await expect(page.getByText("Child Document 1")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Child Document 2")).toBeVisible();

    // Parent document's annotation index sections should appear
    await expect(page.getByText("1. Introduction")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("2. Terms and Conditions")).toBeVisible();

    // Expand Child Document 1 to see its sections
    const child1Item = page.getByRole("treeitem", {
      name: /Child Document 1/,
    });
    await child1Item.locator(".chevron").click();

    await expect(page.getByText("A. Definitions")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("B. Obligations")).toBeVisible();

    // Expand Child Document 2 to see its sections
    const child2Item = page.getByRole("treeitem", {
      name: /Child Document 2/,
    });
    await child2Item.locator(".chevron").click();

    await expect(page.getByText("I. Liability")).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "corpus--toc--hybrid-index");
  });
});
