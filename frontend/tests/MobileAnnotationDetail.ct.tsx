import React from "react";
import { test, expect } from "./utils/coverage";
import { MobileAnnotationDetailTestWrapper } from "./MobileAnnotationDetailTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

/**
 * Regression coverage for the mobile annotation deep-link UX fix.
 *
 * A cold-cache deep-link straight to `?ann=<id>` selects an annotation id that
 * has not arrived yet. The component must distinguish "still fetching"
 * (`loading={true}` → loader) from "genuinely gone" (`loading={false}` →
 * not-found message). Previously it always claimed the annotation was gone.
 */
test.describe("MobileAnnotationDetail", () => {
  test("shows a loader while the document is still loading and the annotation is unresolved", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MobileAnnotationDetailTestWrapper loading={true} />
    );

    // The loader text appears instead of the not-found message.
    await expect(page.getByText("Loading annotation…")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("This annotation is no longer available.")
    ).not.toBeVisible();

    // The loader is exposed as an ARIA live region (role="status" →
    // aria-live="polite") so screen readers announce it on a deep-link.
    await expect(page.getByRole("status")).toBeVisible();

    await docScreenshot(page, "annotations--mobile-annotation-detail--loading");

    await component.unmount();
  });

  test("shows the not-found message once loading settles and the annotation is still unresolved", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MobileAnnotationDetailTestWrapper loading={false} />
    );

    await expect(
      page.getByText("This annotation is no longer available.")
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Loading annotation…")).not.toBeVisible();

    await docScreenshot(
      page,
      "annotations--mobile-annotation-detail--not-found"
    );

    await component.unmount();
  });
});
