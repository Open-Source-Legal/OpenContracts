import React from "react";
import { test, expect } from "./utils/coverage";
import {
  PageLayoutShowcase,
  PageLayoutPropsHarness,
} from "./PageLayoutTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("PageLayout primitives - Composition", () => {
  test("renders the full layout chrome with all primitives", async ({
    mount,
    page,
  }) => {
    await mount(<PageLayoutShowcase />);

    // All primitives are present.
    await expect(page.locator('[data-testid="page-container"]')).toBeVisible();
    await expect(
      page.locator('[data-testid="content-container"]')
    ).toBeVisible();
    await expect(page.locator('[data-testid="hero-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="hero-title"]')).toContainText(
      "Open"
    );
    await expect(page.locator('[data-testid="hero-title"]')).toContainText(
      "Contracts"
    );
    await expect(page.locator('[data-testid="hero-subtitle"]')).toBeVisible();
    await expect(page.locator('[data-testid="stats-container"]')).toBeVisible();
    await expect(
      page.locator('[data-testid="section-header-default"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="section-header-no-gap"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="empty-state-wrapper"]')
    ).toBeVisible();

    await docScreenshot(page, "layout--page-layout--showcase");
  });

  test("SectionHeader $gap and $wrap props affect CSS", async ({
    mount,
    page,
  }) => {
    await mount(<PageLayoutShowcase />);

    // Default header: gap = 16px, flex-wrap = wrap.
    const defaultHeader = page.locator(
      '[data-testid="section-header-default"]'
    );
    const defaultStyles = await defaultHeader.evaluate((el) => {
      const cs = window.getComputedStyle(el);
      return { gap: cs.gap, flexWrap: cs.flexWrap };
    });
    // Browsers normalize "16px" / "16px 16px" — accept either rendering.
    expect(defaultStyles.gap).toMatch(/16px/);
    expect(defaultStyles.flexWrap).toBe("wrap");

    // Discovery-style header: gap = 0, flex-wrap = nowrap.
    const noGapHeader = page.locator('[data-testid="section-header-no-gap"]');
    const noGapStyles = await noGapHeader.evaluate((el) => {
      const cs = window.getComputedStyle(el);
      return { gap: cs.gap, flexWrap: cs.flexWrap };
    });
    expect(noGapStyles.gap).toMatch(/^0px( 0px)?$/);
    expect(noGapStyles.flexWrap).toBe("nowrap");
  });
});

test.describe("PageLayout primitives - Transient prop overrides", () => {
  test("ContentContainer respects $maxWidth=wide", async ({ mount, page }) => {
    await mount(<PageLayoutPropsHarness $maxWidth="wide" />);
    const maxWidth = await page
      .locator('[data-testid="content-container"]')
      .evaluate((el) => window.getComputedStyle(el).maxWidth);
    expect(maxWidth).toBe("1200px");
  });

  test("ContentContainer defaults to narrow (900px)", async ({
    mount,
    page,
  }) => {
    await mount(<PageLayoutPropsHarness />);
    const maxWidth = await page
      .locator('[data-testid="content-container"]')
      .evaluate((el) => window.getComputedStyle(el).maxWidth);
    expect(maxWidth).toBe("900px");
  });

  test("HeroSection / HeroTitle margin-bottom overrides apply", async ({
    mount,
    page,
  }) => {
    await mount(
      <PageLayoutPropsHarness $heroMarginBottom={40} $titleMarginBottom={12} />
    );

    const heroMb = await page
      .locator('[data-testid="hero-section"]')
      .evaluate((el) => window.getComputedStyle(el).marginBottom);
    expect(heroMb).toBe("40px");

    const titleMb = await page
      .locator('[data-testid="hero-title"]')
      .evaluate((el) => window.getComputedStyle(el).marginBottom);
    expect(titleMb).toBe("12px");
  });
});
