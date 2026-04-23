/**
 * Playwright Component Tests for `FieldsetModal`.
 *
 * The modal lets users create or edit a Fieldset — the schema definition used
 * to drive structured data extraction.  These tests cover the branches called
 * out in issue #1279:
 *
 *   - Create vs Edit mode (title, footer info, pre-filled fields)
 *   - Validation gating ("Please provide a fieldset name" / "Please add at
 *     least one column")
 *   - Column add flow (via the embedded `CreateColumnModal`)
 *   - Column delete flow (local removal for new fieldsets)
 *   - Dismissal paths (X button, Cancel button, overlay click)
 *   - Columns count pill update on add/delete
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { FieldsetModalTestWrapper } from "./FieldsetModalTestWrapper";
import {
  buildGetFieldsetMock,
  DEFAULT_EXTRACT_TASK_NAME,
} from "./FieldsetModalMocks";
import { FieldsetType, ColumnType } from "../src/types/graphql-api";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

const FIELDSET_ID = "existing-fieldset-1";

const existingColumn: ColumnType = {
  id: "col-existing-1",
  name: "Effective Date",
  query: "What is the effective date?",
  matchText: "effective date",
  outputType: "str",
  limitToLabel: "",
  instructions: "Look for dates near the header",
  extractIsList: false,
  taskName: DEFAULT_EXTRACT_TASK_NAME,
};

const existingFieldset = {
  id: FIELDSET_ID,
  name: "Existing Fieldset",
  description: "An existing fieldset for tests",
  inUse: false,
} as FieldsetType;

const editModeMocks = [
  // GET_REGISTERED_EXTRACT_TASKS fires from the embedded CreateColumnModal —
  // the wrapper already includes several copies; we supplement with the
  // fieldset fetch for edit mode.
  buildGetFieldsetMock(FIELDSET_ID, {
    name: "Existing Fieldset",
    description: "An existing fieldset for tests",
    fullColumnList: [existingColumn],
  }),
];

// ---------------------------------------------------------------------------
// Rendering & layout
// ---------------------------------------------------------------------------

test.describe("FieldsetModal — create mode rendering", () => {
  test("renders the create-mode header, empty state, and action buttons", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);

    // The modal has a 50ms mount delay
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    // Subtitle
    await expect(
      page.locator(
        "text=Define the structure for extracting data from documents"
      )
    ).toBeVisible();

    // The "Columns (0)" section header
    await expect(page.locator("text=Columns (0)")).toBeVisible();

    // Empty-state prompt
    await expect(
      page.locator(
        "text=No columns yet. Add columns to define what data to extract."
      )
    ).toBeVisible();

    // Action buttons
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create Fieldset" })
    ).toBeVisible();

    await docScreenshot(page, "widgets--fieldset-modal--create-empty");
  });

  test("disables Create Fieldset while the form is incomplete", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    const createBtn = page.getByRole("button", { name: "Create Fieldset" });
    await expect(createBtn).toBeDisabled();

    // Footer info should prompt for a name first
    await expect(
      page.locator("text=Please provide a fieldset name")
    ).toBeVisible();

    // Fill in the name — but with no columns, footer should flip to the
    // column-required message and button should stay disabled.
    await page
      .locator('input[placeholder="Enter fieldset name..."]')
      .fill("My Fieldset");
    await expect(
      page.locator("text=Please add at least one column")
    ).toBeVisible();
    await expect(createBtn).toBeDisabled();
  });

  test("accepts typed name/description and keeps values", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    const nameInput = page.locator(
      'input[placeholder="Enter fieldset name..."]'
    );
    await nameInput.fill("Payment Terms");
    await expect(nameInput).toHaveValue("Payment Terms");

    const descInput = page.locator(
      'textarea[placeholder="Describe what this fieldset extracts..."]'
    );
    await descInput.fill("Extract payment clauses");
    await expect(descInput).toHaveValue("Extract payment clauses");
  });
});

// ---------------------------------------------------------------------------
// Column add / delete
// ---------------------------------------------------------------------------

test.describe("FieldsetModal — column management", () => {
  test("opens the CreateColumnModal when 'Add First Column' is clicked", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: "Add First Column" }).click();

    // The embedded CreateColumnModal should open
    await expect(page.locator("text=Create New Column")).toBeVisible({
      timeout: 5000,
    });
  });

  test("adds a new column locally and surfaces it in the list", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: "Add First Column" }).click();
    await expect(page.locator("text=Create New Column")).toBeVisible({
      timeout: 5000,
    });

    // Fill the column form (name + query are required)
    await page
      .locator('input[placeholder="Enter column name"]')
      .fill("Contract Amount");
    await page
      .locator(
        'textarea[placeholder="What query shall we use to guide the LLM extraction?"]'
      )
      .fill("What is the total contract amount?");

    await page.getByRole("button", { name: "Create Column" }).click();

    // Column modal should close
    await expect(page.locator("text=Create New Column")).toBeHidden({
      timeout: 5000,
    });

    // New column appears in the parent fieldset modal
    await expect(page.locator("text=Contract Amount")).toBeVisible({
      timeout: 5000,
    });
    // Column counter updates from 0 → 1
    await expect(page.locator("text=Columns (1)")).toBeVisible();
  });

  test("deletes a column from a new (unsaved) fieldset", async ({
    mount,
    page,
  }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });

    // Add a column
    await page.getByRole("button", { name: "Add First Column" }).click();
    await expect(page.locator("text=Create New Column")).toBeVisible({
      timeout: 5000,
    });
    await page
      .locator('input[placeholder="Enter column name"]')
      .fill("Colossus");
    await page
      .locator(
        'textarea[placeholder="What query shall we use to guide the LLM extraction?"]'
      )
      .fill("What is the value?");
    await page.getByRole("button", { name: "Create Column" }).click();

    await expect(page.locator("text=Columns (1)")).toBeVisible({
      timeout: 5000,
    });

    const deleteBtn = page
      .getByRole("button", { name: "Delete column" })
      .first();
    await deleteBtn.click();

    await expect(page.locator("text=Columns (0)")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=Colossus")).toBeHidden();
    // Empty state should reappear
    await expect(
      page.locator(
        "text=No columns yet. Add columns to define what data to extract."
      )
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Edit mode
// ---------------------------------------------------------------------------

test.describe("FieldsetModal — edit mode", () => {
  test("renders Edit Fieldset header and pre-fills fields from query", async ({
    mount,
    page,
  }) => {
    await mount(
      <FieldsetModalTestWrapper
        mode="edit"
        existingFieldset={existingFieldset}
        mocks={editModeMocks}
      />
    );

    // Edit header
    await expect(page.locator("text=Edit Fieldset")).toBeVisible({
      timeout: 5000,
    });
    // Save button label flips to "Update Fieldset"
    await expect(
      page.getByRole("button", { name: "Update Fieldset" })
    ).toBeVisible();

    // Pre-filled name + description from the GetFieldset query
    const nameInput = page.locator(
      'input[placeholder="Enter fieldset name..."]'
    );
    await expect(nameInput).toHaveValue("Existing Fieldset", { timeout: 5000 });
    const descInput = page.locator(
      'textarea[placeholder="Describe what this fieldset extracts..."]'
    );
    await expect(descInput).toHaveValue("An existing fieldset for tests");

    // The existing column should render
    await expect(page.locator("text=Effective Date")).toBeVisible();
    await expect(page.locator("text=Columns (1)")).toBeVisible();

    // Footer info reflects edit mode
    await expect(
      page.locator("text=Editing existing fieldset definition")
    ).toBeVisible();

    await docScreenshot(page, "widgets--fieldset-modal--edit-populated");
  });

  test("shows 'Update Fieldset' as enabled when prefilled data is valid", async ({
    mount,
    page,
  }) => {
    await mount(
      <FieldsetModalTestWrapper
        mode="edit"
        existingFieldset={existingFieldset}
        mocks={editModeMocks}
      />
    );

    await expect(page.locator("text=Edit Fieldset")).toBeVisible({
      timeout: 5000,
    });

    // Wait for the query to populate the name input
    await expect(
      page.locator('input[placeholder="Enter fieldset name..."]')
    ).toHaveValue("Existing Fieldset", { timeout: 5000 });

    const updateBtn = page.getByRole("button", { name: "Update Fieldset" });
    await expect(updateBtn).toBeEnabled({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// Dismissal paths
// ---------------------------------------------------------------------------

test.describe("FieldsetModal — close behavior", () => {
  test("closes on Cancel click", async ({ mount, page }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator("text=Create New Fieldset")).toBeHidden({
      timeout: 3000,
    });
  });

  test("closes on the X close button", async ({ mount, page }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });
    const closeBtn = page.getByRole("button", { name: "Close" });
    await closeBtn.click();
    await expect(page.locator("text=Create New Fieldset")).toBeHidden({
      timeout: 3000,
    });
  });

  test("closes on overlay click", async ({ mount, page }) => {
    await mount(<FieldsetModalTestWrapper />);
    await expect(page.locator("text=Create New Fieldset")).toBeVisible({
      timeout: 5000,
    });
    // Click a corner far from the modal container
    await page.mouse.click(5, 5);
    await expect(page.locator("text=Create New Fieldset")).toBeHidden({
      timeout: 3000,
    });
  });
});
