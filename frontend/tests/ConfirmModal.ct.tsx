import React from "react";
import { test, expect } from "./utils/coverage";
import { ConfirmModal } from "../src/components/widgets/modals/ConfirmModal";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ConfirmModal", () => {
  test("renders when visible with message and buttons", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ConfirmModal
        message="Are you sure you want to delete this item?"
        visible={true}
        yesAction={() => {}}
        noAction={() => {}}
        toggleModal={() => {}}
      />
    );

    // Modal renders via portal, check page not component
    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByText("Are you sure you want to delete this item?")
    ).toBeVisible();

    // Default button labels
    await expect(page.getByRole("button", { name: "Yes" })).toBeVisible();
    await expect(page.getByRole("button", { name: "No" })).toBeVisible();

    await docScreenshot(page, "widgets--confirm-modal--initial");

    await component.unmount();
  });

  test("does not render when visible is false", async ({ mount, page }) => {
    const component = await mount(
      <ConfirmModal
        message="This should not appear"
        visible={false}
        yesAction={() => {}}
        noAction={() => {}}
        toggleModal={() => {}}
      />
    );

    await expect(page.getByText("ARE YOU SURE?")).not.toBeVisible();

    await component.unmount();
  });

  test("calls yesAction and toggleModal when Yes is clicked", async ({
    mount,
    page,
  }) => {
    let yesCalled = false;
    let toggleCalled = false;

    const component = await mount(
      <ConfirmModal
        message="Confirm this action?"
        visible={true}
        yesAction={() => {
          yesCalled = true;
        }}
        noAction={() => {}}
        toggleModal={() => {
          toggleCalled = true;
        }}
      />
    );

    await expect(page.getByRole("button", { name: "Yes" })).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Yes" }).click();

    expect(yesCalled).toBe(true);
    expect(toggleCalled).toBe(true);

    await component.unmount();
  });

  test("calls noAction and toggleModal when No is clicked", async ({
    mount,
    page,
  }) => {
    let noCalled = false;
    let toggleCalled = false;

    const component = await mount(
      <ConfirmModal
        message="Confirm this action?"
        visible={true}
        yesAction={() => {}}
        noAction={() => {
          noCalled = true;
        }}
        toggleModal={() => {
          toggleCalled = true;
        }}
      />
    );

    await expect(page.getByRole("button", { name: "No" })).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "No" }).click();

    expect(noCalled).toBe(true);
    expect(toggleCalled).toBe(true);

    await component.unmount();
  });

  test("renders custom button labels and confirm variant", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ConfirmModal
        message="Delete permanently?"
        visible={true}
        yesAction={() => {}}
        noAction={() => {}}
        toggleModal={() => {}}
        confirmLabel="Delete"
        cancelLabel="Keep"
        confirmVariant="primary"
      />
    );

    await expect(page.getByRole("button", { name: "Delete" })).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("button", { name: "Keep" })).toBeVisible();

    // Default labels should not appear
    await expect(page.getByRole("button", { name: "Yes" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "No" })).not.toBeVisible();

    await component.unmount();
  });

  test("does not auto-close on Yes when confirmLoading is controlled", async ({
    mount,
    page,
  }) => {
    // Opting into the controlled-loading flow (confirmLoading defined, even
    // when false) means the caller owns the close: Yes fires yesAction but
    // must NOT call toggleModal.
    let yesCalled = false;
    let toggleCalled = false;

    const component = await mount(
      <ConfirmModal
        message="Confirm this action?"
        visible={true}
        yesAction={() => {
          yesCalled = true;
        }}
        noAction={() => {}}
        toggleModal={() => {
          toggleCalled = true;
        }}
        confirmLoading={false}
      />
    );

    await expect(page.getByRole("button", { name: "Yes" })).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Yes" }).click();

    expect(yesCalled).toBe(true);
    // Caller-controlled close: toggleModal is intentionally NOT invoked.
    expect(toggleCalled).toBe(false);

    await component.unmount();
  });

  test("stays open with a disabled, loading Yes button while confirmLoading is true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ConfirmModal
        message="Deleting category…"
        visible={true}
        yesAction={() => {}}
        noAction={() => {}}
        toggleModal={() => {}}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        confirmVariant="primary"
        confirmLoading={true}
      />
    );

    // Dialog remains visible (work is in flight) ...
    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 5000,
    });
    // ... and both buttons are disabled so the action can't be double-fired.
    await expect(page.getByRole("button", { name: "Delete" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeDisabled();

    await docScreenshot(page, "widgets--confirm-modal--loading");

    await component.unmount();
  });
});
