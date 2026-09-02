import React from "react";
import { test, expect } from "./utils/coverage";
import { LabelSetSelectorTestWrapper } from "./LabelSetSelectorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { LabelSetType } from "../src/types/graphql-api";

test.describe("LabelSetSelector", () => {
  test("renders with placeholder when no label set selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(<LabelSetSelectorTestWrapper />);

    // Should show the header
    await expect(page.locator("h5")).toContainText("Label Set:");

    // Should show the dropdown with placeholder text
    const placeholder = page.locator(".oc-dropdown__placeholder");
    await expect(placeholder).toBeVisible({ timeout: 10000 });
    await expect(placeholder).toContainText("Choose a label set");

    await docScreenshot(page, "widgets--label-set-selector--default");

    await component.unmount();
  });

  test("renders with pre-selected label set name", async ({ mount, page }) => {
    const preSelected = {
      id: "ls-1",
      icon: "tags",
      title: "Contract Labels",
      description: "Labels for contract analysis",
      created: "2024-01-01T00:00:00Z",
      is_selected: false,
      is_open: false,
      isPublic: true,
      myPermissions: ["read"],
    } as unknown as LabelSetType;

    const component = await mount(
      <LabelSetSelectorTestWrapper labelSet={preSelected} />
    );

    // Should show the selected value, not the placeholder
    const selectedValue = page.locator(".oc-dropdown__value");
    await expect(selectedValue).toBeVisible({ timeout: 10000 });
    await expect(selectedValue).toContainText("Contract Labels");

    await docScreenshot(page, "widgets--label-set-selector--with-selection");

    await component.unmount();
  });

  test("dropdown trigger is clickable", async ({ mount, page }) => {
    const component = await mount(<LabelSetSelectorTestWrapper />);

    // Wait for the dropdown to render
    const trigger = page.locator(".oc-dropdown__trigger");
    await expect(trigger).toBeVisible({ timeout: 10000 });

    // Click the trigger to open the dropdown
    await trigger.click();

    // The dropdown menu should appear
    const menu = page.locator(".oc-dropdown__menu");
    await expect(menu).toBeVisible({ timeout: 10000 });

    // Should show the label set options once data loads
    const options = page.locator(".oc-dropdown__option");
    await expect(options).toHaveCount(2, { timeout: 10000 });
    await expect(options.first()).toContainText("Contract Labels");
    await expect(options.last()).toContainText("Financial Labels");

    await component.unmount();
  });

  test("returns the selected label set object to controlled consumers", async ({
    mount,
    page,
  }) => {
    const component = await mount(<LabelSetSelectorTestWrapper />);

    await page.locator(".oc-dropdown__trigger").click();
    await page
      .locator(".oc-dropdown__option")
      .filter({ hasText: "Financial Labels" })
      .click();

    await expect(component.getByTestId("selected-labelset")).toHaveText("ls-2");
    await expect(page.locator(".oc-dropdown__value")).toContainText(
      "Financial Labels"
    );

    await component.unmount();
  });

  test("read-only mode disables dropdown", async ({ mount, page }) => {
    const component = await mount(
      <LabelSetSelectorTestWrapper read_only={true} />
    );

    // The dropdown trigger should be disabled
    const trigger = page.locator(".oc-dropdown__trigger");
    await expect(trigger).toBeVisible({ timeout: 10000 });

    // Verify the dropdown is disabled (button should have disabled attribute)
    await expect(trigger).toBeDisabled();

    await component.unmount();
  });
});
