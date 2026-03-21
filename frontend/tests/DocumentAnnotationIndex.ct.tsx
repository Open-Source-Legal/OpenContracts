import { test, expect } from "@playwright/experimental-ct-react";
import { DocumentAnnotationIndexTestWrapper } from "./DocumentAnnotationIndexTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("DocumentAnnotationIndex", () => {
  test("renders hierarchical sections with descriptions", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    // Wait for sections to load
    await expect(page.getByText("Sections")).toBeVisible({ timeout: 10000 });

    // Root-level chapters should be visible
    await expect(page.getByText("Chapter 1: Introduction")).toBeVisible();
    await expect(
      page.getByText("Chapter 2: Terms and Conditions")
    ).toBeVisible();
    await expect(page.getByText("Chapter 3: Liability")).toBeVisible();

    // Subsections should NOT be visible until expanded
    await expect(page.getByText("1.1 Purpose")).not.toBeVisible();
    await expect(page.getByText("1.2 Definitions")).not.toBeVisible();

    // Page badges should be shown
    await expect(page.getByText("p. 1", { exact: true })).toBeVisible();
    await expect(page.getByText("p. 5", { exact: true })).toBeVisible();
    await expect(page.getByText("p. 10", { exact: true })).toBeVisible();

    await docScreenshot(page, "corpus--annotation-index--with-hierarchy");
  });

  test("expands children when chevron is clicked", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    // Expand Chapter 1
    const chevron = page.locator(".chevron").first();
    await chevron.click();

    // Subsections should now be visible
    await expect(page.getByText("1.1 Purpose")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("1.2 Definitions")).toBeVisible();

    // Page badges for subsections
    await expect(page.getByText("p. 2")).toBeVisible();
    await expect(page.getByText("p. 3")).toBeVisible();

    await docScreenshot(page, "corpus--annotation-index--expanded-children");
  });

  test("expands markdown description on click", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    // The description should be visible in collapsed (clamped) form
    const description = page.locator(".collapsed").first();
    await expect(description).toBeVisible();

    // Click to expand the description
    await description.click();

    // After expansion, the description should have class "expanded"
    await expect(page.locator(".expanded").first()).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "corpus--annotation-index--expanded-description");
  });

  test("returns null for empty annotation set", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="empty" />);

    // Wait for query to resolve
    await page.waitForTimeout(2000);

    // Component returns null when no entries — nothing should render
    await expect(page.getByText("Sections")).not.toBeVisible();
    await expect(page.locator('[role="tree"]')).not.toBeVisible();
  });

  test("renders flat sections without hierarchy", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="flat" />);

    await expect(page.getByText("Sections")).toBeVisible({ timeout: 10000 });

    // All entries visible as root-level items
    await expect(page.getByText("Chapter 1: Introduction")).toBeVisible();
    await expect(page.getByText("1.1 Purpose")).toBeVisible();
    await expect(page.getByText("1.2 Definitions")).toBeVisible();
    await expect(
      page.getByText("Chapter 2: Terms and Conditions")
    ).toBeVisible();
    await expect(page.getByText("2.1 Payment Terms")).toBeVisible();
    await expect(page.getByText("Chapter 3: Liability")).toBeVisible();

    // No chevrons should be visible (no children)
    const chevrons = page.locator(".chevron svg");
    await expect(chevrons).toHaveCount(0);

    await docScreenshot(page, "corpus--annotation-index--flat");
  });

  test("renders sections without descriptions", async ({ mount, page }) => {
    await mount(
      <DocumentAnnotationIndexTestWrapper mockType="noDescriptions" />
    );

    await expect(page.getByText("Sections")).toBeVisible({ timeout: 10000 });

    // Titles should be visible
    await expect(page.getByText("Chapter 1: Introduction")).toBeVisible();

    // No description elements should exist
    await expect(page.locator(".collapsed")).toHaveCount(0);
    await expect(page.locator(".expanded")).toHaveCount(0);

    await docScreenshot(page, "corpus--annotation-index--no-descriptions");
  });

  test("tree nodes have proper ARIA attributes", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('[role="tree"]', { timeout: 10000 });

    // Tree container should have tree role with label
    const tree = page.locator('[role="tree"]');
    await expect(tree).toBeVisible();
    await expect(tree).toHaveAttribute("aria-label", "Document sections");

    // Tree items should have treeitem role
    const treeItems = page.locator('[role="treeitem"]');
    await expect(treeItems.first()).toBeVisible();

    // Items with children should have aria-expanded
    const firstItem = treeItems.first();
    await expect(firstItem).toHaveAttribute("aria-expanded", "false");

    // Items without children (Chapter 3: Liability) should NOT have aria-expanded
    const lastItem = treeItems.last();
    const ariaExpanded = await lastItem.getAttribute("aria-expanded");
    expect(ariaExpanded).toBeNull();
  });

  test("tree nodes are keyboard focusable", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    const treeItem = page.locator('[role="treeitem"]').first();
    await expect(treeItem).toHaveAttribute("tabindex", "0");
  });

  test("keyboard navigation - ArrowRight expands node", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    const firstNode = page.locator('[role="treeitem"]').first();
    await firstNode.focus();

    // Press ArrowRight to expand
    await page.keyboard.press("ArrowRight");

    // Children should become visible
    await expect(page.getByText("1.1 Purpose")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("1.2 Definitions")).toBeVisible();
  });

  test("keyboard navigation - ArrowLeft collapses node", async ({
    mount,
    page,
  }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    const firstNode = page.locator('[role="treeitem"]').first();
    await firstNode.focus();

    // Expand first
    await page.keyboard.press("ArrowRight");
    await expect(firstNode).toHaveAttribute("aria-expanded", "true", {
      timeout: 5000,
    });
    await expect(page.getByText("1.1 Purpose")).toBeVisible({
      timeout: 5000,
    });

    // Re-focus and collapse
    await firstNode.focus();
    await page.waitForTimeout(100);
    await page.keyboard.press("ArrowLeft");

    await expect(firstNode).toHaveAttribute("aria-expanded", "false", {
      timeout: 5000,
    });
  });

  test("aria-expanded reflects node state", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    const firstNode = page.locator('[role="treeitem"]').first();

    // Initially collapsed
    await expect(firstNode).toHaveAttribute("aria-expanded", "false");

    // Expand by clicking chevron
    const chevron = page.locator(".chevron").first();
    await chevron.click();

    // Should be expanded
    await expect(firstNode).toHaveAttribute("aria-expanded", "true");
  });

  test("nodes have aria-label with title and page", async ({ mount, page }) => {
    await mount(<DocumentAnnotationIndexTestWrapper mockType="default" />);

    await page.waitForSelector('text="Chapter 1: Introduction"', {
      timeout: 10000,
    });

    const firstNode = page.locator('[role="treeitem"]').first();
    const ariaLabel = await firstNode.getAttribute("aria-label");
    expect(ariaLabel).toContain("Chapter 1: Introduction");
    expect(ariaLabel).toContain("page 1");
  });

  test("max depth limits rendering depth", async ({ mount, page }) => {
    // Default mock has 2 levels (chapters -> subsections)
    // With maxDepth=0, only root chapters should render
    await mount(
      <DocumentAnnotationIndexTestWrapper mockType="default" maxDepth={0} />
    );

    await expect(page.getByText("Sections")).toBeVisible({ timeout: 10000 });

    // Root chapters should be visible
    await expect(page.getByText("Chapter 1: Introduction")).toBeVisible();

    // Chapter 1 should NOT be expandable (children beyond maxDepth)
    const firstItem = page.locator('[role="treeitem"]').first();
    const ariaExpanded = await firstItem.getAttribute("aria-expanded");
    expect(ariaExpanded).toBeNull();
  });

  test("embedded mode renders without outer border and header", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentAnnotationIndexTestWrapper mockType="default" embedded={true} />
    );

    // Embedded mode uses role="group" (not "tree") to avoid nested tree
    // violation when mounted inside DocumentTableOfContents's role="tree".
    await page.waitForSelector('[role="group"]', { timeout: 10000 });

    // The tree should render but without the "Sections" header
    await expect(page.getByText("Sections")).not.toBeVisible();

    // Section content should still be present
    await expect(page.getByText("Chapter 1: Introduction")).toBeVisible();

    await docScreenshot(page, "corpus--annotation-index--embedded");
  });

  test("filter narrows visible sections by title", async ({ mount, page }) => {
    await mount(
      <DocumentAnnotationIndexTestWrapper
        mockType="flat"
        filterQuery="Payment"
      />
    );

    await page.waitForSelector('[role="tree"]', { timeout: 10000 });

    // Only "2.1 Payment Terms" should match
    await expect(page.getByText("2.1 Payment Terms")).toBeVisible();

    // Non-matching titles should not be visible
    await expect(page.getByText("Chapter 1: Introduction")).not.toBeVisible();
    await expect(page.getByText("Chapter 3: Liability")).not.toBeVisible();
  });

  test("filter matches on description content", async ({ mount, page }) => {
    await mount(
      <DocumentAnnotationIndexTestWrapper
        mockType="default"
        filterQuery="Effective Date"
      />
    );

    await page.waitForSelector('[role="tree"]', { timeout: 10000 });

    // "1.2 Definitions" has "Effective Date" in its description
    // Its parent "Chapter 1: Introduction" should also appear (preserved path)
    await expect(page.getByText("1.2 Definitions")).toBeVisible();

    // Non-matching branches should be filtered out
    await expect(
      page.getByText("Chapter 2: Terms and Conditions")
    ).not.toBeVisible();
  });
});
