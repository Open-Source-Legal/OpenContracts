/**
 * Playwright Component Tests for the cite About page.
 *
 * Mounts /src/views/About.tsx through the shared LandingTestWrapper
 * (which provides BrowserRouter + MockedProvider + Jotai + Auth0
 * stubs) and verifies the section structure renders against the active
 * landingContent variant.
 */
import { test, expect } from "./utils/coverage";
import { About } from "../src/views/About";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";
import defaultLandingContent from "../src/config/landingContent/default.json";

/**
 * Strips inline `*italic*` markup the way <renderInlineMarkup /> does
 * for rendering. Lets us assert against JSON content directly.
 */
const text = (input: string): string => input.replace(/\*/g, "");

test.describe("About Page", () => {
  test("renders the eyebrow, title, and every section from the JSON variant", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <LandingTestWrapper>
        <About />
      </LandingTestWrapper>
    );

    const about = defaultLandingContent.about;

    // Eyebrow + page title from the active variant.
    await expect(page.locator(`text=${about.eyebrow}`).first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator(`text=${about.title}`)).toBeVisible();

    // Every section heading defined in JSON is rendered.
    for (const section of about.sections) {
      await expect(page.locator(`text=${section.title}`)).toBeVisible();
    }

    // Doc screenshot: the full /about page anonymous view.
    await docScreenshot(page, "about--full-page--anonymous", {
      fullPage: true,
    });
    await releaseScreenshot(page, "v3.0.0.rc1", "about-page", {
      fullPage: true,
    });

    await component.unmount();
  });

  test("renders the first paragraph of each section", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <LandingTestWrapper>
        <About />
      </LandingTestWrapper>
    );

    // The first paragraph of every section must paint — guards against a
    // regression where <renderInlineMarkup /> or the paragraph map
    // silently drops content. Use a short prefix of the first paragraph
    // (with markup stripped) so the assertion stays resilient to copy
    // tweaks while still proving the body rendered.
    for (const section of defaultLandingContent.about.sections) {
      const firstParagraph = text(section.paragraphs[0]);
      // Grab the first ~60 chars to avoid full-paragraph string matches
      // that turn brittle when wrapped across lines.
      const probe = firstParagraph.slice(0, 60);
      await expect(page.locator(`text=${probe}`).first()).toBeVisible({
        timeout: 10000,
      });
    }

    await component.unmount();
  });
});
