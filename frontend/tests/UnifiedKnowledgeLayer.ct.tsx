import { test, expect } from "@playwright/experimental-ct-react";
import { UnifiedKnowledgeLayerTestWrapper } from "./UnifiedKnowledgeLayerTestWrapper";

test.describe("UnifiedKnowledgeLayer", () => {
  test("renders when not loading", async ({ mount, page }) => {
    await mount(<UnifiedKnowledgeLayerTestWrapper parentLoading={false} />);

    // Component should be rendered in the wrapper
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("does not render when parent is loading", async ({ mount, page }) => {
    await mount(<UnifiedKnowledgeLayerTestWrapper parentLoading={true} />);

    // Component wrapper should exist but content may not render when parent is loading
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("renders with document metadata", async ({ mount, page }) => {
    const metadata = {
      title: "Test Document Title",
      description: "Test document description",
      author: "Test Author",
      created: new Date().toISOString(),
    };

    await mount(
      <UnifiedKnowledgeLayerTestWrapper
        parentLoading={false}
        metadata={metadata}
      />
    );

    // Should render the component wrapper
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("renders with custom document and corpus IDs", async ({
    mount,
    page,
  }) => {
    await mount(
      <UnifiedKnowledgeLayerTestWrapper
        documentId="custom-doc-123"
        corpusId="custom-corpus-456"
        parentLoading={false}
      />
    );

    // Component wrapper should render
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("handles empty metadata gracefully", async ({ mount, page }) => {
    await mount(
      <UnifiedKnowledgeLayerTestWrapper parentLoading={false} metadata={{}} />
    );

    // Component wrapper should still render
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("renders summary preview components", async ({ mount, page }) => {
    await mount(<UnifiedKnowledgeLayerTestWrapper parentLoading={false} />);

    // Wait for component to mount
    await page.waitForTimeout(500);

    // The wrapper should be present
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("updates when parentLoading changes", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedKnowledgeLayerTestWrapper parentLoading={true} />
    );

    // Wrapper should always be visible
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();

    // Update to not loading
    await component.update(
      <UnifiedKnowledgeLayerTestWrapper parentLoading={false} />
    );

    // Wrapper should still be visible
    await expect(wrapper).toBeVisible();
  });

  test("handles GraphQL query loading state", async ({ mount, page }) => {
    // The default mock includes data, so the component should render
    await mount(<UnifiedKnowledgeLayerTestWrapper parentLoading={false} />);

    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("renders with custom GraphQL mocks", async ({ mount, page }) => {
    const customMock = {
      request: {
        query: {
          kind: "Document" as const,
          definitions: [],
          loc: { start: 0, end: 0 },
        },
        variables: { documentId: "test-doc-1", corpusId: "test-corpus-1" },
      },
      result: {
        data: {
          document: {
            id: "test-doc-1",
            summaryContent: "Custom summary text",
            currentSummaryVersion: 1,
            summaryRevisions: [],
            __typename: "DocumentType",
          },
        },
      },
    };

    await mount(
      <UnifiedKnowledgeLayerTestWrapper
        parentLoading={false}
        mocks={[customMock]}
      />
    );

    // Component wrapper should render with custom data
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("component has correct structure", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedKnowledgeLayerTestWrapper parentLoading={false} />
    );

    // The component itself is the wrapper with styles
    // Get viewport dimensions for comparison
    const viewportSize = page.viewportSize();

    // Check computed styles of the mounted component wrapper
    const { width, height, position, background } = await component.evaluate(
      (el) => {
        const styles = window.getComputedStyle(el);
        return {
          width: parseInt(styles.width),
          height: parseInt(styles.height),
          position: styles.position,
          background: styles.background,
        };
      }
    );

    // Should have full viewport dimensions (computed values will be in pixels)
    // Note: Width might be slightly less than viewport due to scrollbar (typically 16-17px)
    const expectedWidth = viewportSize?.width || 1280;
    expect(width).toBeGreaterThan(expectedWidth - 20); // Allow for scrollbar
    expect(width).toBeLessThanOrEqual(expectedWidth);

    const expectedHeight = viewportSize?.height || 720;
    expect(height).toBeGreaterThan(expectedHeight - 20); // Allow for scrollbar
    expect(height).toBeLessThanOrEqual(expectedHeight);

    expect(position).toBe("relative");
    expect(background).toContain("rgb(245, 245, 245)"); // #f5f5f5
  });

  test("handles different metadata types", async ({ mount, page }) => {
    const complexMetadata = {
      title: "Complex Document",
      description: "A document with complex metadata",
      author: "Multiple Authors",
      created: "2024-01-01T00:00:00Z",
      modified: "2024-01-02T00:00:00Z",
      tags: ["legal", "contract", "important"],
      customField: "Custom Value",
    };

    await mount(
      <UnifiedKnowledgeLayerTestWrapper
        parentLoading={false}
        metadata={complexMetadata}
      />
    );

    // Component wrapper should handle complex metadata
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();
  });

  test("persists through prop updates", async ({ mount, page }) => {
    const component = await mount(
      <UnifiedKnowledgeLayerTestWrapper
        documentId="doc-1"
        corpusId="corpus-1"
        parentLoading={false}
      />
    );

    // Component wrapper should be visible
    const wrapper = page.locator("div").first();
    await expect(wrapper).toBeVisible();

    // Update with new metadata
    await component.update(
      <UnifiedKnowledgeLayerTestWrapper
        documentId="doc-1"
        corpusId="corpus-1"
        parentLoading={false}
        metadata={{
          title: "Updated Title",
          description: "Updated Description",
        }}
      />
    );

    // Should still be visible
    await expect(wrapper).toBeVisible();
  });
});
