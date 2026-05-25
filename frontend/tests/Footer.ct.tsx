import { FooterHarness } from "./FooterTestWrapper";
// NOTE — per CLAUDE.md, keep JSX component imports in a separate import
// statement from helper/util imports. Playwright CT's babel transform
// only rewrites a statement's specifiers into `importRefs` when every
// specifier is a JSX component; mixing a component with helpers leaves
// the component unrewritten and `mount()` throws "cannot be mounted".

import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("Footer (cite rebrand)", () => {
  test("renders the full-width layout above the 1000px breakpoint", async ({
    mount,
    page,
  }) => {
    // 1280×800 is comfortably above the isCompact threshold (1000px),
    // so the grid + lockup-below variant should render.
    await page.setViewportSize({ width: 1280, height: 800 });

    await mount(<FooterHarness />);

    // Brand lockup, opensource.legal handle, and [cite] wordmark all visible.
    await expect(page.getByLabel("opensource.legal [cite]")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("[cite]").first()).toBeVisible();

    // Footer headings + GitHub external link + About internal link.
    await expect(page.getByText("opensource.legal").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/Open-Source-Legal"
    );
    await expect(page.getByRole("link", { name: "About cite" })).toBeVisible();

    // Inline nav row at the bottom (About, Terms, Privacy). No /contact
    // route exists yet, so the footer intentionally does not link to one.
    await expect(
      page.getByRole("link", { name: "About", exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Terms of Service" })
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Privacy Policy" })
    ).toBeVisible();

    await docScreenshot(page, "layout--footer--full-width");
  });

  test("collapses to the compact stacked layout at or below 1000px", async ({
    mount,
    page,
  }) => {
    // Below the 1000px isCompact threshold but above the 400px isSmall
    // threshold — exercises the `$compact` branch of FooterContainer
    // (renders lockup above the grid) without flipping the lockup typography
    // into its small variant.
    await page.setViewportSize({ width: 800, height: 1024 });

    await mount(<FooterHarness />);

    // Brand lockup remains accessible; the compact layout renders it first
    // in DOM order (above the org grid) rather than at the bottom.
    await expect(page.getByLabel("opensource.legal [cite]")).toBeVisible({
      timeout: 5000,
    });

    // Footer org block still rendered; the only structural difference vs
    // the full-width test is the lockup position, which is hard to assert
    // on directly without coupling to internal selectors. The fact that
    // the compact branch is mounted at all is enough for coverage.
    await expect(page.getByText("opensource.legal").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "About cite" })).toBeVisible();

    await docScreenshot(page, "layout--footer--compact");
  });

  test("uses the small-variant typography below 400px", async ({
    mount,
    page,
  }) => {
    // 360×640 is below isSmall (400px), so the lockup styled-components
    // pick the smaller font-size + tighter gap branches. Visually subtle,
    // but ensures the `$small` ternary in `Lockup`/`LockupHandle`/
    // `LockupWordmark` is exercised.
    await page.setViewportSize({ width: 360, height: 640 });

    await mount(<FooterHarness />);

    await expect(page.getByLabel("opensource.legal [cite]")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("[cite]").first()).toBeVisible();
  });
});
