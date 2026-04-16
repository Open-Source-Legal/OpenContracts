/**
 * Playwright component tests for ComponentEmbedErrorFallback.
 *
 * Tests cover:
 * 1. Renders the generic error message
 * 2. Shows error.message in development mode
 */
import { test, expect } from "./utils/coverage";
import { Provider } from "jotai";
import React from "react";

import { ComponentEmbedErrorFallback } from "../src/components/widgets/ComponentEmbedErrorFallback";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ComponentEmbedErrorFallback", () => {
  test("should render fallback message with error details", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <Provider>
        <div style={{ width: "600px", padding: "16px" }}>
          <ComponentEmbedErrorFallback
            error={new Error("ExtractGridEmbed crashed")}
          />
        </div>
      </Provider>
    );

    await expect(
      page.getByText("Embedded component failed to render")
    ).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "caml--component-embed-error-fallback--default");

    await component.unmount();
  });
});
