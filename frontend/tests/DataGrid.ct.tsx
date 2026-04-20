import React from "react";
import { test, expect } from "./utils/coverage";
import { DataGridTestWrapper } from "./DataGridTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../src/types/graphql-api";

// ---------------------------------------------------------------------------
// Fixtures shared between tests. Keep them local so additions here do not
// perturb the defaults baked into DataGridTestWrapper.
// ---------------------------------------------------------------------------

const runningExtract: ExtractType = {
  id: "extract-running",
  name: "Running Extract",
  started: "2024-01-01T00:00:00Z",
  finished: null,
  error: "",
  fieldset: {
    id: "fieldset-1",
    name: "Test Fieldset",
    description: "",
    inUse: false,
    creator: { id: "user-1", email: "test@example.com" },
    columns: { edges: [] },
  },
  corpus: { id: "corpus-1", title: "Test Corpus" } as any,
  creator: { id: "user-1", email: "test@example.com" },
  created: "2024-01-01T00:00:00Z",
} as ExtractType;

const completeExtract: ExtractType = {
  id: "extract-complete",
  name: "Complete Extract",
  started: "2024-01-01T00:00:00Z",
  finished: "2024-01-02T00:00:00Z",
  error: "",
  fieldset: {
    id: "fieldset-1",
    name: "Test Fieldset",
    description: "",
    inUse: true, // triggers the "fieldset in multiple places" warning copy
    creator: { id: "user-1", email: "test@example.com" },
    columns: { edges: [] },
  },
  corpus: { id: "corpus-1", title: "Test Corpus" } as any,
  creator: { id: "user-1", email: "test@example.com" },
  created: "2024-01-01T00:00:00Z",
} as ExtractType;

// Four representative output types: str (text), int (number), bool (boolean),
// and a Pydantic-model-shape (JSON object with list semantics).
const mixedTypeColumns: ColumnType[] = [
  {
    id: "col-text",
    name: "Party Name",
    outputType: "str",
    extractIsList: false,
    taskName: "doc_extract_query_task",
  } as ColumnType,
  {
    id: "col-number",
    name: "Contract Value",
    outputType: "int",
    extractIsList: false,
    taskName: "doc_extract_query_task",
  } as ColumnType,
  {
    id: "col-bool",
    name: "Is Signed",
    outputType: "bool",
    extractIsList: false,
    taskName: "doc_extract_query_task",
  } as ColumnType,
  {
    id: "col-json",
    name: "Line Items",
    outputType: "name: str\nqty: int",
    extractIsList: true,
    taskName: "doc_extract_query_task",
  } as ColumnType,
];

const oneDoc: DocumentType[] = [
  { id: "doc-1", title: "Sample Agreement.pdf" } as DocumentType,
];

const mixedCells: DatacellType[] = [
  {
    id: "cell-text",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-text" } as ColumnType,
    data: { data: "Acme Corp" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
  } as DatacellType,
  {
    id: "cell-number",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-number" } as ColumnType,
    data: { data: 42 },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
  } as DatacellType,
  {
    id: "cell-bool",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-bool" } as ColumnType,
    data: { data: true },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
  } as DatacellType,
  {
    id: "cell-json",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-json" } as ColumnType,
    data: { data: { items: [{ name: "Widget", qty: 3 }] } },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
  } as DatacellType,
];

// ---------------------------------------------------------------------------
// Original render + state tests (kept intact)
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid", () => {
  test("renders table with columns and documents", async ({ mount, page }) => {
    const component = await mount(<DataGridTestWrapper />);

    await expect(page.locator("text=Document").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=Contract Value").first()).toBeVisible();
    await expect(page.locator("text=Effective Date").first()).toBeVisible();

    await expect(
      page.locator("text=Master Service Agreement.pdf").first()
    ).toBeVisible();
    await expect(
      page.locator("text=Non-Disclosure Agreement.pdf").first()
    ).toBeVisible();

    await docScreenshot(page, "extracts--data-grid--with-data");
    await component.unmount();
  });

  test("shows empty state when no documents", async ({ mount, page }) => {
    const component = await mount(<DataGridTestWrapper rows={[]} cells={[]} />);

    await expect(page.locator("text=No documents yet").first()).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "extracts--data-grid--empty");
    await component.unmount();
  });

  test("shows checkbox column when extract not started", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    await expect(page.locator("text=Document").first()).toBeVisible({
      timeout: 10000,
    });

    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible();
    // 1 select-all + 2 rows = 3 checkboxes
    await expect(checkboxes).toHaveCount(3);

    await component.unmount();
  });

  test("hides checkbox column when extract is started", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DataGridTestWrapper extract={runningExtract} />
    );

    await expect(page.locator("text=Document").first()).toBeVisible({
      timeout: 10000,
    });

    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes).toHaveCount(0);

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// Loading state / overlay
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — loading state", () => {
  test("shows 'Loading...' overlay when loading and extract is not running", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper loading={true} />);

    await expect(page.locator("text=Loading...").first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("shows 'Processing...' overlay when loading and extract is running", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DataGridTestWrapper extract={runningExtract} loading={true} />
    );

    await expect(page.locator("text=Processing...").first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// Sorting — click header toggles ASC → DESC → unsorted
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — sorting", () => {
  test("clicking the Document header shows sort indicator and toggles direction", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    const documentHeader = page.locator("th", { hasText: "Document" }).first();
    await expect(documentHeader).toBeVisible({ timeout: 10000 });

    // ASC sort
    await documentHeader.click();
    await expect(documentHeader.locator("svg").last()).toBeVisible();

    // Verify order — "Master Service Agreement.pdf" should come before
    // "Non-Disclosure Agreement.pdf" ASC alphabetically.
    const rowTexts = await page
      .locator('tbody tr td:not([type="checkbox"])')
      .allInnerTexts();
    const msaIdx = rowTexts.findIndex((t) =>
      t.includes("Master Service Agreement")
    );
    const ndaIdx = rowTexts.findIndex((t) =>
      t.includes("Non-Disclosure Agreement")
    );
    expect(msaIdx).toBeGreaterThan(-1);
    expect(ndaIdx).toBeGreaterThan(-1);
    expect(msaIdx).toBeLessThan(ndaIdx);

    // DESC sort — after a second click, NDA comes before MSA
    await documentHeader.click();
    const descTexts = await page
      .locator('tbody tr td:not([type="checkbox"])')
      .allInnerTexts();
    const msaDescIdx = descTexts.findIndex((t) =>
      t.includes("Master Service Agreement")
    );
    const ndaDescIdx = descTexts.findIndex((t) =>
      t.includes("Non-Disclosure Agreement")
    );
    expect(ndaDescIdx).toBeLessThan(msaDescIdx);

    await component.unmount();
  });

  test("clicking a data column header sorts its values", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    const valueHeader = page
      .locator("th", { hasText: "Contract Value" })
      .first();
    await expect(valueHeader).toBeVisible({ timeout: 10000 });

    await valueHeader.click();
    // After clicking, we expect the column header to contain a chevron svg.
    const svgs = valueHeader.locator("svg");
    await expect(svgs.first()).toBeVisible();

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// Row selection / bulk-delete bar
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — row selection", () => {
  test("selecting a row reveals the Delete Selected action bar", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes).toHaveCount(3, { timeout: 10000 });

    // Check the first body row — index 1 because index 0 is the header's
    // "select all" checkbox.
    await checkboxes.nth(1).check();

    await expect(
      page.getByRole("button", { name: /Delete Selected \(1\)/ })
    ).toBeVisible();

    // Select all via header checkbox.
    await checkboxes.nth(0).check();
    await expect(
      page.getByRole("button", { name: /Delete Selected \(2\)/ })
    ).toBeVisible();

    // Unselect all via header toggle — it no longer satisfies the "size > 0"
    // branch so the delete bar disappears.
    await checkboxes.nth(0).uncheck();
    await expect(
      page.getByRole("button", { name: /Delete Selected/ })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("Delete Selected button invokes onRemoveDocIds with selected rows", async ({
    mount,
    page,
  }) => {
    let capturedExtractId: string | null = null;
    let capturedIds: string[] | null = null;

    const component = await mount(
      <DataGridTestWrapper
        onRemoveDocIds={(extractId, documentIds) => {
          capturedExtractId = extractId;
          capturedIds = documentIds;
        }}
      />
    );

    const checkboxes = page.locator('input[type="checkbox"]');
    await expect(checkboxes).toHaveCount(3, { timeout: 10000 });
    await checkboxes.nth(1).check();

    await page.getByRole("button", { name: /Delete Selected \(1\)/ }).click();

    await expect
      .poll(() => capturedExtractId, { timeout: 5000 })
      .toBe("extract-1");
    expect(capturedIds).toEqual(["doc-1"]);

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// Column management (add / edit / delete)
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — column management", () => {
  test("clicking the add-column button opens the Create Column modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    // The small "+" header button is the only Plus icon inside the sticky
    // header row. Scope to the thead so we don't pick up the bottom-left
    // "Add documents" FAB.
    const addColumnButton = page
      .locator('thead button:has(svg[class*="lucide-plus"])')
      .first();
    await expect(addColumnButton).toBeVisible({ timeout: 10000 });
    await addColumnButton.click();

    // CreateColumnModal shows "Create New Column" when no existing_column.
    await expect(page.locator("text=Create New Column")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("clicking the per-column Edit button opens the modal in edit mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    await expect(page.locator("text=Contract Value").first()).toBeVisible({
      timeout: 10000,
    });

    // First Edit button in the header (one per data column).
    // Lucide's "Edit" icon is an alias for "SquarePen", so its class is
    // "lucide-square-pen" — NOT "lucide-edit".
    const editButton = page
      .locator('thead button:has(svg[class*="lucide-square-pen"])')
      .first();
    await editButton.click();

    // Modal title flips to "Edit Column" when existing_column is provided.
    await expect(page.locator("text=Edit Column")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("clicking the per-column Delete button opens a confirmation modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    await expect(page.locator("text=Contract Value").first()).toBeVisible({
      timeout: 10000,
    });

    const deleteButton = page
      .locator('thead button:has(svg[class*="lucide-trash"])')
      .first();
    await deleteButton.click();

    await expect(
      page.getByText(/Are you sure you want to delete the column/)
    ).toBeVisible({ timeout: 5000 });

    // Cancel leaves state untouched.
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByText(/Are you sure you want to delete the column/)
    ).toHaveCount(0);

    await component.unmount();
  });

  test("confirming deletion of a column calls onRemoveColumnId", async ({
    mount,
    page,
  }) => {
    let removedColumnId: string | null = null;

    const component = await mount(
      <DataGridTestWrapper
        onRemoveColumnId={(columnId) => {
          removedColumnId = columnId;
        }}
      />
    );

    await expect(page.locator("text=Contract Value").first()).toBeVisible({
      timeout: 10000,
    });

    const deleteButton = page
      .locator('thead button:has(svg[class*="lucide-trash"])')
      .first();
    await deleteButton.click();

    await expect(
      page.getByText(/Are you sure you want to delete the column/)
    ).toBeVisible({ timeout: 5000 });

    await page.getByRole("button", { name: "Delete" }).click();

    await expect.poll(() => removedColumnId, { timeout: 5000 }).toBe("col-1");

    await component.unmount();
  });

  test("fieldset-in-use warning is shown when fieldset.inUse is true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DataGridTestWrapper extract={completeExtract} rows={[]} cells={[]} />
    );

    // Empty state is rendered because we passed no rows, but the header
    // controls are still present and clickable. We need rows for the Delete
    // column button to appear in the header though — fall back to default
    // rows.
    await component.unmount();

    const component2 = await mount(
      <DataGridTestWrapper extract={{ ...completeExtract, started: null }} />
    );

    await expect(page.locator("text=Contract Value").first()).toBeVisible({
      timeout: 10000,
    });

    const deleteButton = page
      .locator('thead button:has(svg[class*="lucide-trash"])')
      .first();
    await deleteButton.click();

    await expect(
      page.getByText(/This fieldset is used in multiple places/)
    ).toBeVisible({ timeout: 5000 });

    await component2.unmount();
  });
});

// ---------------------------------------------------------------------------
// Add-documents FAB
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — add documents FAB", () => {
  test("clicking the Add Documents FAB opens the document picker modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper />);

    await expect(page.locator("text=Document").first()).toBeVisible({
      timeout: 10000,
    });

    const addDocsFab = page.getByRole("button", { name: "Add documents" });
    await addDocsFab.click();

    // SelectDocumentsModal renders — there's no stable text, but the modal
    // appears as a dialog.
    await expect(page.locator('[role="dialog"]').first()).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// Cell rendering matrix — text / number / boolean / JSON
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — cell rendering matrix", () => {
  test("renders text, number, boolean, and JSON column values", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DataGridTestWrapper
        extract={completeExtract}
        columns={mixedTypeColumns}
        rows={oneDoc}
        cells={mixedCells}
      />
    );

    await expect(page.locator("text=Party Name").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=Contract Value").first()).toBeVisible();
    await expect(page.locator("text=Is Signed").first()).toBeVisible();
    await expect(page.locator("text=Line Items").first()).toBeVisible();

    // Text cell
    await expect(page.locator("text=Acme Corp").first()).toBeVisible();
    // Number cell (rendered as string)
    await expect(page.locator("text=42").first()).toBeVisible();
    // Boolean cell — rendered via String(true) → "true"
    await expect(page.locator("text=true").first()).toBeVisible();
    // JSON object cell renders as "View/Edit JSON" affordance instead of raw.
    await expect(page.locator("text=View/Edit JSON").first()).toBeVisible();

    await docScreenshot(page, "extracts--data-grid--cell-matrix");
    await component.unmount();
  });

  test("corrected cell data takes precedence over original data", async ({
    mount,
    page,
  }) => {
    const correctedCells: DatacellType[] = [
      {
        id: "cell-corr",
        document: { id: "doc-1" } as DocumentType,
        column: { id: "col-text" } as ColumnType,
        data: { data: "Original Value" },
        dataDefinition: "",
        started: "2024-01-01T00:00:00Z",
        completed: "2024-01-02T00:00:00Z",
        failed: null,
        approvedBy: null,
        rejectedBy: null,
        correctedData: "Edited Value",
      } as DatacellType,
    ];

    const component = await mount(
      <DataGridTestWrapper
        extract={completeExtract}
        columns={[mixedTypeColumns[0]]}
        rows={oneDoc}
        cells={correctedCells}
      />
    );

    // Corrected value should render in place of original.
    await expect(page.locator("text=Edited Value").first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});

// ---------------------------------------------------------------------------
// CSV export via imperative handle
// ---------------------------------------------------------------------------

test.describe("ExtractDataGrid — CSV export", () => {
  test("exportToCsv triggers a CSV download via the imperative handle", async ({
    mount,
    page,
  }) => {
    const component = await mount(<DataGridTestWrapper withExportButton />);

    await expect(page.locator("text=Master Service Agreement.pdf")).toBeVisible(
      { timeout: 10000 }
    );

    const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
    await page.getByTestId("trigger-export-csv").click();
    const download = await downloadPromise;

    // Filename uses extract.name
    expect(download.suggestedFilename()).toBe("Test Extract.csv");

    await component.unmount();
  });
});
