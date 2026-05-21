import { test, expect } from "@playwright/experimental-ct-react";
import { MobileLayoutHarness } from "./MobileDocumentLayout.harness";

test.use({ viewport: { width: 390, height: 844 } });

test("starts on the Document tab with chrome present", async ({ mount }) => {
  const c = await mount(<MobileLayoutHarness />);
  await expect(c.getByRole("tab", { name: "Document" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("selecting the Summary tab swaps the surface", async ({ mount }) => {
  const c = await mount(<MobileLayoutHarness />);
  await c.getByRole("tab", { name: "Summary" }).click();
  await expect(c.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(c.getByTestId("mobile-surface-summary")).toBeVisible();
});
