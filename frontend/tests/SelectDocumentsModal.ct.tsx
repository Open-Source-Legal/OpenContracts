import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { SelectDocumentsModalTestWrapper } from "./SelectDocumentsModalTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("SelectDocumentsModal", () => {
  test("renders modal with header and buttons", async ({ mount, page }) => {
    const component = await mount(
      <SelectDocumentsModalTestWrapper open={true} />
    );

    // Modal header should be visible
    await expect(page.locator("text=Select Document(s)")).toBeVisible({
      timeout: 10000,
    });

    // Footer buttons should be visible
    await expect(page.getByRole("button", { name: /Cancel/i })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Add Documents/i })
    ).toBeVisible();

    await docScreenshot(page, "modals--select-documents--open");

    await component.unmount();
  });

  test("does not render when closed", async ({ mount, page }) => {
    const component = await mount(
      <SelectDocumentsModalTestWrapper open={false} />
    );

    await expect(page.locator("text=Select Document(s)")).not.toBeVisible();

    await component.unmount();
  });

  test("calls toggleModal on Cancel click", async ({ mount, page }) => {
    let toggled = false;
    const component = await mount(
      <SelectDocumentsModalTestWrapper
        open={true}
        toggleModal={() => {
          toggled = true;
        }}
      />
    );

    await expect(page.locator("text=Select Document(s)")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: /Cancel/i }).click();
    expect(toggled).toBe(true);

    await component.unmount();
  });
});
