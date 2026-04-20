/**
 * CT tests for HighlightItem permission gating (issue #1269).
 *
 * Verifies that the delete affordance only renders on the intersection of:
 *   - not read-only
 *   - not a structural annotation
 *   - user has CAN_REMOVE
 *   - parent supplied an onDelete handler
 * All other branches must hide the delete button.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { HighlightItemHarness } from "./HighlightItemPermissionsTestWrapper";
import { PermissionTypes } from "../src/components/types";

test.describe("HighlightItem - permission gating", () => {
  test("renders delete button when user has CAN_REMOVE and annotation is editable", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_REMOVE]}
        readOnly={false}
        structural={false}
        withOnDelete={true}
      />
    );

    await expect(
      page.getByRole("button", { name: "Delete annotation" })
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("hides delete button when user lacks CAN_REMOVE", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE]}
        readOnly={false}
        structural={false}
        withOnDelete={true}
      />
    );

    await expect(page.getByTestId("highlight-item")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Delete annotation" })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("hides delete button when readOnly is true even with CAN_REMOVE", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_REMOVE]}
        readOnly={true}
        structural={false}
        withOnDelete={true}
      />
    );

    await expect(page.getByTestId("highlight-item")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Delete annotation" })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("hides delete button for structural annotation even with CAN_REMOVE", async ({
    mount,
    page,
  }) => {
    // Structural annotations are always read-only on the client (only
    // superusers can mutate them, and that's enforced server-side).
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_REMOVE]}
        readOnly={false}
        structural={true}
        withOnDelete={true}
      />
    );

    await expect(page.getByTestId("highlight-item")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Delete annotation" })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("hides delete button when no onDelete handler is supplied", async ({
    mount,
    page,
  }) => {
    // Even with full permissions, if the parent doesn't pass a handler
    // the affordance should be hidden (no-op buttons would confuse users).
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_REMOVE]}
        readOnly={false}
        structural={false}
        withOnDelete={false}
      />
    );

    await expect(page.getByTestId("highlight-item")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Delete annotation" })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("invokes onDelete when the delete button is clicked", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HighlightItemHarness
        permissions={[PermissionTypes.CAN_REMOVE]}
        readOnly={false}
        structural={false}
        withOnDelete={true}
      />
    );

    const button = page.getByRole("button", { name: "Delete annotation" });
    await expect(button).toBeVisible({ timeout: 5000 });
    await button.click();

    // The harness renders a receipt div with the deleted annotation id once
    // onDelete fires; asserting on it avoids passing closures into mount().
    await expect(page.getByTestId("delete-receipt")).toHaveText("ann-fixture");

    await component.unmount();
  });
});
