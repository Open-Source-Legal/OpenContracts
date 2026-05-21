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

test("the More tab opens a sheet listing the Tier-2 surfaces", async ({
  mount,
}) => {
  const c = await mount(<MobileLayoutHarness />);
  await c.getByRole("tab", { name: "More" }).click();
  await expect(c.getByTestId("mobile-more-menu")).toBeVisible();
  await expect(c.getByTestId("mobile-more-discussions")).toBeVisible();
  await expect(c.getByTestId("mobile-more-notes")).toBeVisible();
  await expect(c.getByTestId("mobile-more-info")).toBeVisible();
});

test("the More sheet shows the read-only document info view", async ({
  mount,
}) => {
  const c = await mount(<MobileLayoutHarness />);
  await c.getByRole("tab", { name: "More" }).click();
  await c.getByTestId("mobile-more-info").click();
  const infoSurface = c.getByTestId("mobile-more-info-surface");
  await expect(infoSurface).toBeVisible();
  await expect(infoSurface.getByText("Stub Document")).toBeVisible();
  // The back affordance returns to the menu list.
  await c.getByTestId("mobile-more-back").click();
  await expect(c.getByTestId("mobile-more-menu")).toBeVisible();
});
