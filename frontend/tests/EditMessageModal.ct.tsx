import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { EditMessageModalTestWrapper } from "./EditMessageModalTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("EditMessageModal", () => {
  test("renders modal with initial content", async ({ mount, page }) => {
    const component = await mount(
      <EditMessageModalTestWrapper
        isOpen={true}
        initialContent="Hello, this is a test message."
        messageId="msg-1"
      />
    );

    // Modal title should be visible
    await expect(page.locator("text=Edit Message")).toBeVisible({
      timeout: 10000,
    });

    // Save button should be present but disabled (no changes)
    const saveButton = page
      .locator("button")
      .filter({ hasText: "Save Changes" });
    await expect(saveButton).toBeVisible({ timeout: 5000 });
    await expect(saveButton).toBeDisabled();

    // Cancel button should be visible
    await expect(
      page.locator("button").filter({ hasText: "Cancel" })
    ).toBeVisible();

    await docScreenshot(page, "threads--edit-message-modal--initial", {
      element: component,
    });

    await component.unmount();
  });

  test("does not render when closed", async ({ mount, page }) => {
    const component = await mount(
      <EditMessageModalTestWrapper
        isOpen={false}
        initialContent="test"
        messageId="msg-1"
      />
    );

    // Modal title should not be visible
    await expect(page.locator("text=Edit Message")).not.toBeVisible();

    await component.unmount();
  });

  test("shows close button", async ({ mount, page }) => {
    const component = await mount(
      <EditMessageModalTestWrapper
        isOpen={true}
        initialContent="Test content"
        messageId="msg-1"
      />
    );

    await expect(page.locator("text=Edit Message")).toBeVisible({
      timeout: 10000,
    });

    // Close button (X icon) should be visible
    const closeButton = page.getByRole("button", { name: /Close modal/i });
    await expect(closeButton).toBeVisible();

    await component.unmount();
  });
});
