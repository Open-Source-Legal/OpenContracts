import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { ExtractCellEditor } from "../src/components/extracts/datagrid/ExtractCellEditor";
import { docScreenshot } from "./utils/docScreenshot";

const baseRow = { col1: "test value" };
const baseColumn = { key: "col1", name: "Column 1" };

test.describe("ExtractCellEditor", () => {
  test("renders string input for string schema", async ({ mount, page }) => {
    let committed = false;
    const component = await mount(
      <ExtractCellEditor
        row={baseRow}
        column={baseColumn}
        onRowChange={(row, commit) => {
          if (commit) committed = true;
        }}
        onClose={() => {}}
        schema={{ type: "string" }}
        extractIsList={false}
      />
    );

    // Should render a text input
    const input = page.locator("input[type='text'], input:not([type])");
    await expect(input).toBeVisible({ timeout: 5000 });
    await expect(input).toHaveValue("test value");

    // Should have Save and Cancel buttons
    await expect(page.getByRole("button", { name: /Save/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Cancel/i })).toBeVisible();

    await docScreenshot(page, "extracts--cell-editor--string-input", {
      element: component,
    });

    await component.unmount();
  });

  test("renders number input for number schema", async ({ mount, page }) => {
    const component = await mount(
      <ExtractCellEditor
        row={{ col1: 42 }}
        column={baseColumn}
        onRowChange={() => {}}
        onClose={() => {}}
        schema={{ type: "number" }}
        extractIsList={false}
      />
    );

    const input = page.locator("input[type='number']");
    await expect(input).toBeVisible({ timeout: 5000 });
    await expect(input).toHaveValue("42");

    await component.unmount();
  });

  test("renders checkbox for boolean schema", async ({ mount, page }) => {
    const component = await mount(
      <ExtractCellEditor
        row={{ col1: true }}
        column={baseColumn}
        onRowChange={() => {}}
        onClose={() => {}}
        schema={{ type: "boolean" }}
        extractIsList={false}
      />
    );

    const checkbox = page.locator("input[type='checkbox']");
    await expect(checkbox).toBeVisible({ timeout: 5000 });
    await expect(checkbox).toBeChecked();

    await component.unmount();
  });

  test("renders Edit JSON button for object schema", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ExtractCellEditor
        row={{ col1: { key: "value" } }}
        column={baseColumn}
        onRowChange={() => {}}
        onClose={() => {}}
        schema={{ type: "object" }}
        extractIsList={false}
      />
    );

    await expect(page.getByRole("button", { name: /Edit JSON/i })).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "extracts--cell-editor--json-button", {
      element: component,
    });

    await component.unmount();
  });

  test("renders Edit JSON button for list extract", async ({ mount, page }) => {
    const component = await mount(
      <ExtractCellEditor
        row={{ col1: ["item1", "item2"] }}
        column={baseColumn}
        onRowChange={() => {}}
        onClose={() => {}}
        schema={{ type: "string" }}
        extractIsList={true}
      />
    );

    await expect(page.getByRole("button", { name: /Edit JSON/i })).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("commits value on Save click", async ({ mount, page }) => {
    let committedRow: any = null;
    const component = await mount(
      <ExtractCellEditor
        row={baseRow}
        column={baseColumn}
        onRowChange={(row, commit) => {
          if (commit) committedRow = row;
        }}
        onClose={() => {}}
        schema={{ type: "string" }}
        extractIsList={false}
      />
    );

    const input = page.locator("input[type='text'], input:not([type])");
    await input.fill("new value");
    await page.getByRole("button", { name: /Save/i }).click();

    expect(committedRow).toBeTruthy();
    expect(committedRow.col1).toBe("new value");

    await component.unmount();
  });
});
