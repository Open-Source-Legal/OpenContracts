import React from "react";
import { test, expect } from "./utils/coverage";
import { FetchMoreFooterHarness } from "./FetchMoreFooterTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("FetchMoreFooter - Visibility gating", () => {
  test("renders nothing when visible=false", async ({ mount, page }) => {
    await mount(<FetchMoreFooterHarness visible={false} />);

    // Default test-id should not be present.
    await expect(
      page.locator('[data-testid="fetch-more-spinner"]')
    ).toHaveCount(0);

    // The harness wrapper itself should still be there.
    await expect(page.locator('[data-testid="harness-root"]')).toBeVisible();
  });

  test("renders message and spinner when visible=true with default testid", async ({
    mount,
    page,
  }) => {
    await mount(
      <FetchMoreFooterHarness
        visible={true}
        message="Loading more documents…"
      />
    );

    const footer = page.locator('[data-testid="fetch-more-spinner"]');
    await expect(footer).toBeVisible();

    // Accessibility: should be a polite live region.
    await expect(footer).toHaveAttribute("role", "status");
    await expect(footer).toHaveAttribute("aria-live", "polite");

    // Visible label.
    await expect(footer).toContainText("Loading more documents");

    // Spinner SVG is decorative.
    const spinner = footer.locator("svg");
    await expect(spinner).toHaveAttribute("aria-hidden", "true");

    await docScreenshot(page, "infinite-scroll--fetch-more-footer--visible");
  });

  test("honors custom data-testid override", async ({ mount, page }) => {
    await mount(
      <FetchMoreFooterHarness
        visible={true}
        message="Loading more extracts…"
        data-testid="extracts-fetch-more-spinner"
      />
    );

    // Custom test-id used.
    await expect(
      page.locator('[data-testid="extracts-fetch-more-spinner"]')
    ).toBeVisible();

    // Default test-id should NOT be present (override fully replaced it).
    await expect(
      page.locator('[data-testid="fetch-more-spinner"]')
    ).toHaveCount(0);
  });
});
