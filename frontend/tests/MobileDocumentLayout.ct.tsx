import { test, expect } from "./utils/coverage";
import { MobileLayoutHarness } from "./MobileDocumentLayout.harness";

test.use({ viewport: { width: 390, height: 844 } });

// MobileDocumentLayout renders inside FullScreenModal, whose underlying
// `Modal` portals its content to `document.body` — outside the mounted
// component's `#root` subtree. Queries must therefore be page-scoped
// (`page.getByRole`), not component-scoped (`c.getByRole`).

test("starts on the Document tab with chrome present", async ({
  mount,
  page,
}) => {
  await mount(<MobileLayoutHarness />);
  await expect(page.getByRole("tab", { name: "Document" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("selecting the Summary tab swaps the surface", async ({ mount, page }) => {
  await mount(<MobileLayoutHarness />);
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByTestId("mobile-surface-summary")).toBeVisible();
});

test("the More tab opens a sheet listing the Tier-2 surfaces", async ({
  mount,
  page,
}) => {
  await mount(<MobileLayoutHarness />);
  await page.getByRole("tab", { name: "More" }).click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible();
  await expect(page.getByTestId("mobile-more-discussions")).toBeVisible();
  await expect(page.getByTestId("mobile-more-notes")).toBeVisible();
  await expect(page.getByTestId("mobile-more-info")).toBeVisible();
});

test("the More sheet shows the read-only document info view", async ({
  mount,
  page,
}) => {
  await mount(<MobileLayoutHarness />);
  await page.getByRole("tab", { name: "More" }).click();
  await page.getByTestId("mobile-more-info").click();
  const infoSurface = page.getByTestId("mobile-more-info-surface");
  await expect(infoSurface).toBeVisible();
  await expect(infoSurface.getByText("Stub Document")).toBeVisible();
  // The back affordance returns to the menu list.
  await page.getByTestId("mobile-more-back").click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible();
});

test("surfaces a query error instead of the tab surfaces", async ({
  mount,
  page,
}) => {
  await mount(
    <MobileLayoutHarness queryErrorMessage="Document failed to load" />
  );
  await expect(page.getByText("Error loading document")).toBeVisible();
  await expect(page.getByText(/Document failed to load/)).toBeVisible();
  // The error replaces the tab surfaces — the Document surface must not render.
  await expect(page.getByTestId("mobile-surface-document")).toHaveCount(0);
});
