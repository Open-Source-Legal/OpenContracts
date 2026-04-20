/**
 * Playwright component tests for ExtractDetailContent.
 *
 * Target per issue #1282: at least 60% line coverage via CT. Tests cover:
 *  - Loading state while the extract is being fetched
 *  - Not-found state when the GetExtract query returns null
 *  - Stats panel + Data / Documents / Schema tab rendering
 *  - Running state (spinner + message)
 *  - Failed state (empty state + Retry button)
 *  - Schema tab empty + populated states, Add Column flow, Delete Column flow
 *  - Imperative handle methods (exportToCsv + startExtract)
 */

import React from "react";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { ExtractDetailContentTestWrapper } from "./ExtractDetailContentTestWrapper";

test.describe("ExtractDetailContent — loading & empty states", () => {
  test("shows loading overlay while the extract is being fetched", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper loadingForever />
    );

    await expect(
      page.locator("text=Loading extract details...").first()
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("shows the not-found state when the extract query resolves to null", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="not-found" />
    );

    await expect(page.locator("text=Extract not found").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText(/doesn't exist or you don't have access/)
    ).toBeVisible();

    await docScreenshot(page, "extracts--detail-content--not-found");

    await component.unmount();
  });
});

test.describe("ExtractDetailContent — completed extract", () => {
  test("renders the stats panel and the Data tab by default", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="complete" />
    );

    // Wait for the extract to load — the stats panel labels are rendered
    // inside a StatBlock, not as plain text. Scope to the stat-block label
    // class so we don't collide with the tab name "Documents".
    await expect(
      page.locator(".oc-stat-block__label", { hasText: /^Documents$/ })
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator(".oc-stat-block__label", { hasText: /^Columns$/ })
    ).toBeVisible();
    await expect(
      page.locator(".oc-stat-block__label", { hasText: /^Rows$/ })
    ).toBeVisible();
    await expect(
      page.locator(".oc-stat-block__label", { hasText: /^Success$/ })
    ).toBeVisible();

    // The Data tab is the default; the inner DataGrid renders column headers
    // and document rows.
    await expect(page.getByText("Extracted Data")).toBeVisible();
    await expect(page.getByText(/2 rows/)).toBeVisible();
    await expect(
      page.locator("text=Master Service Agreement.pdf").first()
    ).toBeVisible();

    await docScreenshot(page, "extracts--detail-content--complete");
    await component.unmount();
  });

  test("clicking the Documents tab lists the source documents", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="complete" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Documents" }).click();

    await expect(page.getByText("Source Documents")).toBeVisible();
    await expect(page.getByText(/2 documents/).first()).toBeVisible();
    await expect(
      page.locator("text=Master Service Agreement.pdf").first()
    ).toBeVisible();
    await expect(
      page.locator("text=Non-Disclosure Agreement.pdf").first()
    ).toBeVisible();

    await docScreenshot(page, "extracts--detail-content--documents-tab");
    await component.unmount();
  });

  test("clicking the Schema tab lists the schema columns", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="complete" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Schema" }).click();

    await expect(page.getByText("Extract Schema")).toBeVisible();
    await expect(page.getByText(/2 columns/).first()).toBeVisible();
    await expect(
      page
        .locator(".oc-schema-column__name, div")
        .filter({ hasText: "Contract Value" })
        .first()
    ).toBeVisible();
    await expect(
      page.locator("div").filter({ hasText: "Effective Date" }).first()
    ).toBeVisible();

    await docScreenshot(page, "extracts--detail-content--schema-tab");
    await component.unmount();
  });
});

test.describe("ExtractDetailContent — running & failed states", () => {
  test("renders the running state when the extract is in progress", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="running" />
    );

    await expect(
      page.locator("text=Extraction in progress...").first()
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Processing documents/).first()).toBeVisible();

    // Tabs are hidden while running.
    await expect(page.getByRole("tab", { name: "Data" })).toHaveCount(0);

    await docScreenshot(page, "extracts--detail-content--running");
    await component.unmount();
  });

  test("renders the failed state with a Retry button", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="failed" />
    );

    await expect(page.locator("text=Extraction failed").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText(/could not be completed/).first()
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry/i })).toBeVisible();

    // Tabs are hidden on failure.
    await expect(page.getByRole("tab", { name: "Data" })).toHaveCount(0);

    await docScreenshot(page, "extracts--detail-content--failed");
    await component.unmount();
  });

  test("clicking Retry triggers the start-extract mutation", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="failed" />
    );

    await expect(page.getByRole("button", { name: /Retry/i })).toBeVisible({
      timeout: 10000,
    });

    // Clicking Retry should call startExtract — success toast is rendered
    // by react-toastify at document root.
    await page.getByRole("button", { name: /Retry/i }).click();

    // After the mutation completes, the success toast appears. Toasts are
    // portalled outside the wrapper so a text lookup over the page works.
    await expect(page.getByText(/Extract started!/)).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

test.describe("ExtractDetailContent — schema tab interactions", () => {
  test("Schema tab shows empty state with Add Column button when editable", async ({
    mount,
    page,
  }) => {
    // Using the editable scenario so `canEdit` is true — without it, the
    // EmptyState's action button is not rendered.
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="no-columns-editable" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Schema" }).click();

    await expect(page.getByText("No columns defined")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Add Column/i })
    ).toBeVisible();

    await component.unmount();
  });

  test("Schema tab empty state omits Add Column button when extract is running/complete", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="no-columns" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Schema" }).click();

    await expect(page.getByText("No columns defined")).toBeVisible();
    // canEdit is false for started extracts, so the action button is hidden.
    await expect(page.getByRole("button", { name: /Add Column/i })).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("Add button on Schema tab opens the Create Column modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="complete" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Schema" }).click();

    // Schema tab shows an "Add" button when user canEdit (extract.started is
    // present in scenario=complete, so canEdit=false actually). Use the
    // not-started scenario for this path instead.
    await component.unmount();

    const component2 = await mount(
      <ExtractDetailContentTestWrapper scenario="not-started" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("tab", { name: "Schema" }).click();

    await page.getByRole("button", { name: /^Add$/ }).click();

    await expect(page.getByText("Create New Column")).toBeVisible({
      timeout: 5000,
    });

    await component2.unmount();
  });

  test("clicking the trash icon on a schema column opens the confirmation modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="not-started" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Schema" }).click();

    // The per-column delete button has aria-label="Delete column".
    const deleteButtons = page.locator('button[aria-label="Delete column"]');
    await expect(deleteButtons.first()).toBeVisible();
    await deleteButtons.first().click();

    await expect(
      page.getByText("Are you sure you want to delete this column?")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("ExtractDetailContent — documents tab empty state", () => {
  test("Documents tab shows empty state when there are no rows", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="no-documents" />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("tab", { name: "Documents" }).click();

    await expect(page.getByText("No documents yet")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

test.describe("ExtractDetailContent — imperative handle", () => {
  test("exportToCsv handle triggers a CSV download", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="complete" withExportButton />
    );

    await expect(
      page.locator("text=Master Service Agreement.pdf").first()
    ).toBeVisible({ timeout: 10000 });

    const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
    await page.getByTestId("trigger-export-csv").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("Test Extract.csv");

    await component.unmount();
  });

  test("startExtract handle invokes the mutation", async ({ mount, page }) => {
    const component = await mount(
      <ExtractDetailContentTestWrapper scenario="not-started" withStartButton />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await page.getByTestId("trigger-start-extract").click();

    await expect(page.getByText(/Extract started!/)).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

test.describe("ExtractDetailContent — onExtractLoaded callback", () => {
  test("fires the onExtractLoaded callback once the query resolves", async ({
    mount,
    page,
  }) => {
    let loadedId: string | null = null;

    const component = await mount(
      <ExtractDetailContentTestWrapper
        scenario="complete"
        onExtractLoaded={(extract) => {
          loadedId = extract.id;
        }}
      />
    );

    await expect(page.getByText("Extracted Data")).toBeVisible({
      timeout: 10000,
    });

    await expect.poll(() => loadedId, { timeout: 5000 }).toBe("extract-1");

    await component.unmount();
  });
});
