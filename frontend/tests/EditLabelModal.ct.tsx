import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { EditLabelModalTestWrapper } from "./EditLabelModalTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("EditLabelModal", () => {
  test("renders modal with label dropdown", async ({ mount, page }) => {
    const component = await mount(<EditLabelModalTestWrapper visible={true} />);

    // Modal header should show
    await expect(page.locator("text=Edit Label")).toBeVisible({
      timeout: 10000,
    });

    // Should have Save and Cancel buttons
    await expect(
      page.getByRole("button", { name: /Save Change/i })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Cancel/i })).toBeVisible();

    // Should have a dropdown (the dropdown renders with current value or placeholder)
    const dropdown = page.locator(
      "[class*='dropdown'], [role='listbox'], [role='combobox']"
    );
    await expect(dropdown.first()).toBeVisible();

    await docScreenshot(page, "annotator--edit-label-modal--open");

    await component.unmount();
  });

  test("does not render when not visible", async ({ mount, page }) => {
    const component = await mount(
      <EditLabelModalTestWrapper visible={false} />
    );

    await expect(page.locator("text=Edit Label")).not.toBeVisible();

    await component.unmount();
  });

  test("calls onHide when Cancel is clicked", async ({ mount, page }) => {
    let hidden = false;
    const component = await mount(
      <EditLabelModalTestWrapper
        visible={true}
        onHide={() => {
          hidden = true;
        }}
      />
    );

    await expect(page.locator("text=Edit Label")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: /Cancel/i }).click();
    expect(hidden).toBe(true);

    await component.unmount();
  });
});
