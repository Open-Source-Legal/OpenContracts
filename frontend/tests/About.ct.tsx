/**
 * Playwright Component Tests for the cite About page.
 *
 * Mounts /src/views/About.tsx through the shared LandingTestWrapper
 * (which provides BrowserRouter + MockedProvider + Jotai + Auth0
 * stubs) and verifies the four section headings render, then captures
 * the full-page documentation screenshot.
 */
import { test, expect } from "./utils/coverage";
import { About } from "../src/views/About";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

test.describe("About Page", () => {
  test("renders the four section headings + lede", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <About />
      </LandingTestWrapper>
    );

    // Eyebrow + page title
    await expect(page.locator("text=About").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator("text=The citation graph belongs in the public domain.")
    ).toBeVisible();

    // The four section headings from about.md
    await expect(page.locator("text=Why cite exists")).toBeVisible();
    await expect(page.locator("text=Why it’s broken")).toBeVisible();
    await expect(page.locator("text=What cite is")).toBeVisible();
    await expect(
      page.locator("text=Why we think we can do this")
    ).toBeVisible();

    // Doc screenshot: the full /about page anonymous view.
    await docScreenshot(page, "about--full-page--anonymous", {
      fullPage: true,
    });
    await releaseScreenshot(page, "v3.0.0.rc1", "about-page", {
      fullPage: true,
    });

    await component.unmount();
  });

  test("names the proprietary citators explicitly", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <About />
      </LandingTestWrapper>
    );

    // The about copy intentionally names incumbents — these references
    // are load-bearing for the editorial position and must not silently
    // drift back to euphemism in a future copy edit.
    for (const name of [
      "Westlaw",
      "Lexis",
      "JSTOR",
      "USPTO",
      "Wheaton v. Peters",
      "Public.Resource.Org",
      "Free Law Project",
      "OpenStreetMap",
    ]) {
      await expect(page.locator(`text=${name}`).first()).toBeVisible({
        timeout: 10000,
      });
    }

    await component.unmount();
  });
});
