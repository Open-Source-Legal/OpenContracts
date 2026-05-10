import React from "react";
import { test, expect } from "./utils/coverage";
import {
  DiscoveryViewLayoutShowcase,
  DiscoveryViewLayoutPropsHarness,
} from "./DiscoveryViewLayoutTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("DiscoveryViewLayout primitives - Composition", () => {
  test("renders the full layout chrome with all primitives", async ({
    mount,
    page,
  }) => {
    await mount(<DiscoveryViewLayoutShowcase />);

    await expect(
      page.locator('[data-testid="discovery-container"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="discovery-header"]')
    ).toBeVisible();
    await expect(page.locator('[data-testid="discovery-title"]')).toContainText(
      "Global Discussions"
    );
    await expect(
      page.locator('[data-testid="discovery-filter-bar"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="discovery-section-header"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="discovery-section-icon"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="discovery-section-title"]')
    ).toContainText("Recent Threads");
    await expect(
      page.locator('[data-testid="discovery-section-count"]')
    ).toContainText("12");

    await docScreenshot(page, "layout--discovery-view-layout--showcase");
  });
});

test.describe("DiscoveryViewLayout primitives - Transient prop overrides", () => {
  test("DiscoveryTitle defaults to no extra margin-bottom", async ({
    mount,
    page,
  }) => {
    await mount(<DiscoveryViewLayoutPropsHarness />);
    const mb = await page
      .locator('[data-testid="discovery-title"]')
      .evaluate((el) => window.getComputedStyle(el).marginBottom);
    expect(mb).toBe("0px");
  });

  test("DiscoveryTitle $marginBottom override applies", async ({
    mount,
    page,
  }) => {
    await mount(
      <DiscoveryViewLayoutPropsHarness $titleMarginBottom="1.5rem" />
    );
    const mb = await page
      .locator('[data-testid="discovery-title"]')
      .evaluate((el) => window.getComputedStyle(el).marginBottom);
    // 1.5rem at the default 16px root = 24px
    expect(mb).toBe("24px");
  });

  test("DiscoverySectionIcon $color override applies", async ({
    mount,
    page,
  }) => {
    await mount(
      <DiscoveryViewLayoutPropsHarness $iconColor="rgb(255, 0, 64)" />
    );
    const bg = await page
      .locator('[data-testid="discovery-section-icon"]')
      .evaluate((el) => window.getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(255, 0, 64)");
  });
});
