/**
 * Playwright Component Tests for the cite-rebranded Login view.
 *
 * Verifies that the login card uses the cite icon mark + [cite]
 * wordmark + tagline (no more Open Contracts PNG / turquoise), and
 * captures a doc screenshot for marketing/docs reference.
 */
import { test, expect } from "./utils/coverage";
import { Login } from "../src/views/Login";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

test.describe("Login Page", () => {
  test("renders the cite mark, [cite] title, and tagline", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <LandingTestWrapper>
        <Login />
      </LandingTestWrapper>
    );

    // The Login card uses the inline CiteMark SVG (aria-label="cite mark")
    // — assert it's visible without depending on a PNG that's been
    // removed.
    await expect(
      page.locator('svg[aria-label="cite mark"]').first()
    ).toBeVisible({ timeout: 10000 });

    // [cite] wordmark is now the inline CiteWordmark SVG (aria-label="cite"),
    // and the tagline is variant-neutral so the screen doesn't claim copy
    // from a specific landingContent variant.
    await expect(page.locator('svg[aria-label="cite"]').first()).toBeVisible();
    await expect(page.locator("text=Sign in to continue.")).toBeVisible();

    // Form inputs and the navy primary button render
    await expect(page.locator('input[placeholder="Username"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Password"]')).toBeVisible();
    await expect(page.locator('button:has-text("Login")')).toBeVisible();

    // Doc screenshot: the rebranded login card anonymous state.
    await docScreenshot(page, "login--cite-brand--anonymous", {
      element: component,
    });
    await releaseScreenshot(page, "v3.0.0.rc1", "login-page", {
      element: component,
    });

    await component.unmount();
  });
});
