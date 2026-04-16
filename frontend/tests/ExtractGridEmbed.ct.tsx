/**
 * Playwright component tests for ExtractGridEmbed.
 *
 * Tests cover:
 * 1. Populated state with documents, columns, and cells
 * 2. Empty state (no datacells)
 * 3. Not-found state (extract null)
 * 4. Error state (GraphQL error)
 * 5. Loading state (spinner while fetching)
 * 6. Missing extractId prop
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { ExtractGridEmbedTestWrapper } from "./ExtractGridEmbedTestWrapper";

test.describe("ExtractGridEmbed - Populated", () => {
  test("should render table with document rows and column headers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="populated" />
    );

    // Header should show extract name
    await expect(page.getByText("Contract Key Terms")).toBeVisible({
      timeout: 10000,
    });

    // Column headers should be visible
    await expect(page.getByText("Document")).toBeVisible();
    await expect(page.getByText("Effective Date")).toBeVisible();
    await expect(page.getByText("Governing Law")).toBeVisible();

    // Document titles should appear as links
    await expect(page.getByText("Master Services Agreement")).toBeVisible();
    await expect(page.getByText("NDA - Acme Corp")).toBeVisible();

    // Cell values should be rendered
    await expect(page.getByText("2024-01-15")).toBeVisible();
    await expect(page.getByText("State of Delaware")).toBeVisible();

    // Corrected data should be shown when present
    await expect(page.getByText("2023-11-02")).toBeVisible();

    // Source chips should appear for cells with sources.
    // Annotation.page is 1-based, so page:2 displays as "p.2", page:5 as "p.5".
    await expect(page.getByText("p.2").first()).toBeVisible();
    await expect(page.getByText("p.5").first()).toBeVisible();

    await docScreenshot(page, "caml--extract-grid-embed--populated");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Empty", () => {
  test("should show empty state when extract has no datacells", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="empty" />
    );

    // Header should show extract name
    await expect(page.getByText("Empty Extract")).toBeVisible({
      timeout: 10000,
    });

    // Empty message should be displayed
    await expect(page.getByText("No data extracted yet.")).toBeVisible();

    await docScreenshot(page, "caml--extract-grid-embed--empty");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Not Found", () => {
  test("should show not-found message when extract is null", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="not-found" />
    );

    await expect(
      page.getByText("Extract not found or not accessible.")
    ).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "caml--extract-grid-embed--not-found");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Error", () => {
  test("should show error message on GraphQL failure", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="error" />
    );

    await expect(page.getByText("Failed to load extract data.")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "caml--extract-grid-embed--error");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Loading", () => {
  test("should show loading spinner while data is being fetched", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="loading" />
    );

    // Loading message should be visible
    await expect(page.getByText("Loading extract data...")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "caml--extract-grid-embed--loading");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Too Many Rows", () => {
  test("should render partial table with 'showing N of M documents' banner", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="too-many-rows" />
    );

    await expect(page.getByText("Large Extract")).toBeVisible({
      timeout: 10000,
    });

    // Partial-data banner should report visible-of-total document count.
    await expect(page.getByText(/Showing 200 of 201 documents/)).toBeVisible();
    await expect(
      page.getByText(/View the full extract in the Extracts panel/)
    ).toBeVisible();

    await docScreenshot(page, "caml--extract-grid-embed--too-many-rows");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Partial (server-side limit)", () => {
  test("should render table with 'showing N of M cells' banner when payload is bounded", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="partial" />
    );

    await expect(page.getByText("Partial Extract")).toBeVisible({
      timeout: 10000,
    });

    // Table should render the returned slice.
    await expect(page.getByText("Document A")).toBeVisible();
    await expect(page.getByText("Document B")).toBeVisible();

    // Partial-data footer should report fetched-vs-total cell count.
    await expect(page.getByText(/Showing 4 of 800 cells/)).toBeVisible();

    await docScreenshot(page, "caml--extract-grid-embed--partial");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Both Truncated", () => {
  test("should show combined banner when both row clip and server-side limit apply", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="both-truncated" />
    );

    await expect(page.getByText("Both Truncated Extract")).toBeVisible({
      timeout: 10000,
    });

    // The combined banner should mention documents and cell counts, covering
    // the branch where both cellsTruncated and rowsTruncated are true.
    await expect(page.getByText(/Showing 200 of 201 documents/)).toBeVisible();
    await expect(
      page.getByText(/201 of 1000 total cells loaded/)
    ).toBeVisible();

    await docScreenshot(page, "caml--extract-grid-embed--both-truncated");

    await component.unmount();
  });
});

test.describe("ExtractGridEmbed - Missing ID", () => {
  test("should show missing-id message when no extractId is provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractGridEmbedTestWrapper state="missing-id" />
    );

    await expect(page.getByText("Missing extractId prop.")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "caml--extract-grid-embed--missing-id");

    await component.unmount();
  });
});
