/**
 * Playwright component tests for ComponentEmbedErrorFallback.
 *
 * Tests cover:
 * 1. Default rendering with error message
 * 2. Presence of the static fallback text
 */
import { test, expect } from "@playwright/experimental-ct-react";
import { docScreenshot } from "./utils/docScreenshot";
import { ComponentEmbedErrorFallback } from "../src/components/widgets/ComponentEmbedErrorFallback";

test.describe("ComponentEmbedErrorFallback", () => {
  test("should render fallback message with error details", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ComponentEmbedErrorFallback error={new Error("Test render failure")} />
    );

    // Static fallback text should always be visible
    await expect(
      page.getByText("Embedded component failed to render")
    ).toBeVisible({ timeout: 5000 });

    await docScreenshot(page, "caml--embed-error-fallback--default");

    await component.unmount();
  });
});
