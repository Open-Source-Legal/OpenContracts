/**
 * Playwright Component Tests for the ExtractDetail view.
 *
 * ExtractDetail is the extract-detail orchestrator that lives at
 * /extracts/:extractId. It reads the seed extract from the `openedExtract`
 * reactive variable (set by ExtractDetailRoute or CentralRouteManager in
 * production) and hydrates the rest of its state from REQUEST_GET_EXTRACT.
 *
 * These tests cover the orchestration behaviour of the view itself —
 * header/back button, status chips, stats, tabs (Data / Documents / Schema),
 * running/failed state swaps, and the modals it owns. The underlying
 * widgets (ExtractDataGrid, CreateColumnModal, ConfirmModal, status chip
 * utilities) are covered by their own CT suites.
 *
 * Issue #1285 — ExtractDetail.tsx was previously at 7% coverage.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { ExtractDetailTestWrapper } from "./ExtractDetailTestWrapper";
import {
  buildExtractDetailMocks,
  makeMockExtract,
  makeMockColumn,
  makeMockDocument,
  makeMockCell,
} from "./ExtractDetailFixtures";

// ─────────────────────────────────────────────────────────────────────────────
// Empty state — reactive var is null
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — reactive var missing", () => {
  test("renders 'Extract not found' when openedExtract is null", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractDetailTestWrapper extract={null} mocks={[]} />
    );

    await expect(page.getByText("Extract not found")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText(/doesn't exist or you don't have access/i)
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Go to Extracts/i })
    ).toBeVisible();

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Header / status chip / stats
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — header and stats", () => {
  test("renders the title, back link, and corpus context", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      name: "Contract Review Q1",
      corpus: {
        id: "Q29ycHVzVHlwZTox",
        title: "Acme Contracts",
        __typename: "CorpusType",
      } as any,
    });
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract })}
      />
    );

    await expect(
      page.getByRole("heading", { name: "Contract Review Q1" })
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/from Acme Contracts/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Back to Extracts/i })
    ).toBeVisible();

    await component.unmount();
  });

  test("shows 'Not Started' status chip and Start Extract button when extract has not run", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: null,
      finished: null,
      error: null,
    });
    const columns = [makeMockColumn()];
    const documents = [makeMockDocument()];

    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract, columns, documents })}
      />
    );

    await expect(page.getByText(/Not Started/i).first()).toBeVisible({
      timeout: 10_000,
    });
    const startBtn = page.getByRole("button", { name: /Start Extract/i });
    await expect(startBtn).toBeVisible();
    await expect(startBtn).toBeEnabled();

    await component.unmount();
  });

  test("disables Start Extract when there are no documents", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
          documents: [],
        })}
      />
    );

    await expect(page.getByRole("tab", { name: /Data/ })).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole("button", { name: /Start Extract/i })
    ).toBeDisabled();

    await component.unmount();
  });

  test("renders the four StatBlocks with correct labels", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const columns = [
      makeMockColumn(),
      makeMockColumn({ id: "col-2", name: "Other" }),
    ];
    const documents = [
      makeMockDocument(),
      makeMockDocument({ id: "doc-2", title: "Second.pdf" }),
    ];
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract, columns, documents })}
      />
    );

    const statLabels = page.locator(".oc-stat-block__label");
    await expect(statLabels.filter({ hasText: /^Documents$/ })).toBeVisible({
      timeout: 10_000,
    });
    await expect(statLabels.filter({ hasText: /^Columns$/ })).toBeVisible();
    await expect(statLabels.filter({ hasText: /^Rows$/ })).toBeVisible();
    await expect(
      statLabels.filter({ hasText: /^Success Rate$/ })
    ).toBeVisible();

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Running / failed / completed states
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — status-driven rendering", () => {
  test("shows the in-progress overlay and hides tabs when extract is running", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: "2024-01-15T10:00:00Z",
      finished: null,
      error: null,
      id: "running-extract",
    });
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract })}
      />
    );

    await expect(page.getByText(/Extraction in progress/i)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("tab", { name: /Data/ })).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Start Extract/i })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("shows the failed state with a Retry Extract action", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: "2024-01-15T10:00:00Z",
      finished: null,
      error: "Extraction failed: model quota exceeded",
    });
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract })}
      />
    );

    await expect(page.getByText(/Extraction failed/i).first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole("button", { name: /Retry Extract/i })
    ).toBeVisible();

    await component.unmount();
  });

  test("shows completed chip and 100% success rate when every cell is completed", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: "2024-01-15T10:00:00Z",
      finished: "2024-01-15T11:00:00Z",
      error: null,
    });
    const columns = [makeMockColumn()];
    const documents = [makeMockDocument()];
    const cells = [makeMockCell({ completed: "2024-01-15T10:30:00Z" })];

    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract, columns, documents, cells })}
      />
    );

    await expect(page.getByText(/Completed/).first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("100%")).toBeVisible();

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Tabs: Data / Documents / Schema
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — tabs", () => {
  test("switches between Data, Documents, and Schema tabs", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const columns = [makeMockColumn({ name: "Party" })];
    const documents = [makeMockDocument({ title: "Alpha.pdf" })];

    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract, columns, documents })}
      />
    );

    await expect(page.getByText(/Extracted Data/i)).toBeVisible({
      timeout: 10_000,
    });

    await page.getByRole("tab", { name: "Documents" }).click();
    await expect(page.getByText(/Source Documents/i)).toBeVisible();
    await expect(page.getByText("Alpha.pdf")).toBeVisible();

    await page.getByRole("tab", { name: "Schema" }).click();
    await expect(page.getByText(/Extract Schema/i)).toBeVisible();
    await expect(page.getByText("Party")).toBeVisible();

    await component.unmount();
  });

  test("Documents tab shows empty state when no documents are attached", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
          documents: [],
        })}
      />
    );

    await page.getByRole("tab", { name: "Documents" }).click();
    await expect(page.getByText("No documents yet")).toBeVisible({
      timeout: 10_000,
    });

    await component.unmount();
  });

  test("Schema tab shows empty state with 'Add First Column' when no columns", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [],
          documents: [],
        })}
      />
    );

    await page.getByRole("tab", { name: "Schema" }).click();
    await expect(page.getByText("No columns defined")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole("button", { name: /Add First Column/i })
    ).toBeVisible();

    await component.unmount();
  });

  test("Schema tab shows 'Add Column' header button when the extract is editable", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
        })}
      />
    );

    await page.getByRole("tab", { name: "Schema" }).click();
    await expect(page.getByRole("button", { name: /Add Column/i })).toBeVisible(
      { timeout: 10_000 }
    );

    await component.unmount();
  });

  test("Schema tab hides edit/delete controls when the extract has already started", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: "2024-01-15T10:00:00Z",
      finished: "2024-01-15T11:00:00Z",
    });
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
          documents: [makeMockDocument()],
        })}
      />
    );

    await page.getByRole("tab", { name: "Schema" }).click();
    await expect(page.getByText("Sample Column")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: /Add Column/i })).toHaveCount(
      0
    );
    await expect(page.getByLabel(/Edit column/i)).toHaveCount(0);
    await expect(page.getByLabel(/Delete column/i)).toHaveCount(0);

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Modal integration
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — modals", () => {
  test("clicking Add Column opens the CreateColumnModal", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
        })}
      />
    );

    await page.getByRole("tab", { name: "Schema" }).click();
    await page.getByRole("button", { name: /Add Column/i }).click();

    await expect(page.getByText("Create New Column")).toBeVisible({
      timeout: 10_000,
    });

    await component.unmount();
  });

  test("clicking the column delete icon opens the confirm modal", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
        })}
      />
    );

    await page.getByRole("tab", { name: "Schema" }).click();
    await page.getByLabel(/Delete column/i).click();

    await expect(
      page.getByText(/Are you sure you want to delete this column/i)
    ).toBeVisible({ timeout: 10_000 });

    await component.unmount();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Export CSV button
// ─────────────────────────────────────────────────────────────────────────────

test.describe("ExtractDetail — export", () => {
  test("Export CSV button is enabled when the extract is idle", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract();
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({
          extract,
          columns: [makeMockColumn()],
          documents: [makeMockDocument()],
        })}
      />
    );

    const exportBtn = page.getByRole("button", { name: /Export CSV/i });
    await expect(exportBtn).toBeVisible({ timeout: 10_000 });
    await expect(exportBtn).toBeEnabled();

    await component.unmount();
  });

  test("Export CSV button is disabled while extract is running", async ({
    mount,
    page,
  }) => {
    const extract = makeMockExtract({
      started: "2024-01-15T10:00:00Z",
      finished: null,
      error: null,
    });
    const component = await mount(
      <ExtractDetailTestWrapper
        extract={extract}
        mocks={buildExtractDetailMocks({ extract })}
      />
    );

    const exportBtn = page.getByRole("button", { name: /Export CSV/i });
    await expect(exportBtn).toBeVisible({ timeout: 10_000 });
    await expect(exportBtn).toBeDisabled();

    await component.unmount();
  });
});
