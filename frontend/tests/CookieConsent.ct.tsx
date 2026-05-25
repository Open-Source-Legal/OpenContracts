import React from "react";
import { test, expect } from "./utils/coverage";
import { CookieConsentHarness } from "./CookieConsentTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

test.describe("CookieConsent — Rendering", () => {
  test("renders the rebranded cookie consent modal with all sections", async ({
    mount,
    page,
  }) => {
    await mount(<CookieConsentHarness />);

    // Modal should be visible
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Header — Source Serif title and "Privacy" eyebrow
    await expect(page.locator(".oc-modal-header__title")).toContainText(
      "Cookies and terms"
    );
    await expect(page.getByText("Privacy", { exact: true })).toBeVisible();

    // Demo banner — text retained verbatim from the OpenContracts-era copy
    await expect(page.getByText("Demo system.")).toBeVisible();

    // All sentence-case section labels visible
    await expect(page.getByText("Cookie usage")).toBeVisible();
    await expect(page.getByText("Data we collect")).toBeVisible();
    await expect(page.getByText("Data you agree to share")).toBeVisible();

    // Data items — every original item is still rendered
    await expect(
      page.getByText("User information (email, name, IP)")
    ).toBeVisible();
    await expect(page.getByText("Usage information")).toBeVisible();
    await expect(page.getByText("System information")).toBeVisible();
    await expect(page.getByText("Labelsets & labels")).toBeVisible();
    await expect(page.getByText("Configured data extractors")).toBeVisible();

    // Accept button — sentence-case "Accept and continue"
    const acceptBtn = page.getByRole("button", {
      name: /Accept and continue/i,
    });
    await expect(acceptBtn).toBeVisible();

    // Disclaimer text — ALL CAPS legal preserved, with a sentence-case label
    await expect(page.getByText("Warranty disclaimer")).toBeVisible();
    await expect(page.getByText(/WITHOUT WARRANTY OF ANY KIND/i)).toBeVisible();

    // Capture desktop documentation screenshot.
    await docScreenshot(page, "cookie-consent--modal--default");
    await releaseScreenshot(page, "v3.0.0.rc1", "cookie-consent-modal");
  });

  test("renders cleanly inside a phone viewport", async ({ mount, page }) => {
    // iPhone 13 logical viewport — below MOBILE_VIEW_BREAKPOINT (600px),
    // so the mobile-only flex layout, footer lift, and inline icon
    // sizing all kick in. Catches regressions to mobile styling that
    // would otherwise only surface on a physical device.
    await page.setViewportSize({ width: 390, height: 844 });
    await mount(<CookieConsentHarness />);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Title still visible at the top of the mobile sheet
    await expect(page.locator(".oc-modal-header__title")).toContainText(
      "Cookies and terms"
    );

    // Accept button must still be reachable at the bottom of the modal —
    // the mobile flex layout anchors it above the safe-area inset and the
    // brand-correct full-width navy button.
    const acceptBtn = page.getByRole("button", {
      name: /Accept and continue/i,
    });
    await expect(acceptBtn).toBeVisible();

    await docScreenshot(page, "cookie-consent--modal--mobile");
    await releaseScreenshot(page, "v3.0.0.rc1", "cookie-consent-modal-mobile");
  });
});
