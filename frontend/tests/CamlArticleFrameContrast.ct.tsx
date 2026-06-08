/**
 * Regression: CamlArticleFrame must not force dark text on dark-themed chapters.
 *
 * The reading layer in CamlArticleFrame caps the measure and restores heading
 * hierarchy on top of @os-legal/caml-react. It previously also hardcoded dark
 * slate text colors scoped to `article > section`, which outranked the library's
 * theme-aware prose colors and the dark section's light `color`, rendering every
 * heading / paragraph / list item dark-on-dark (invisible) on `theme: dark`
 * chapters. This test renders a light chapter and a dark chapter through the
 * production CamlDirectiveRenderer path and asserts the text actually contrasts
 * with its section background.
 */
import { test, expect } from "./utils/coverage";

import { CamlDirectiveRendererTestWrapper } from "./CamlDirectiveRendererTestWrapper";

import type { CamlDocument } from "@os-legal/caml";

const DOC: CamlDocument = {
  frontmatter: {
    version: "1.0",
    hero: {
      kicker: "Corpus Analysis",
      title: ["Terms of Service", "{Findings}"],
      subtitle: "An exploration of corporate ToS and privacy policies.",
    },
  },
  chapters: [
    {
      id: "overview",
      kicker: "Section 01",
      title: "Overview",
      blocks: [
        {
          type: "prose",
          content:
            "This paragraph sits on a light chapter and must stay dark and readable.",
        },
      ],
    },
    {
      id: "key-findings",
      // Solid dark (not gradient) so the section's backgroundColor is readable
      // for the contrast assertion; the color-override bug is identical for
      // theme:dark and gradient chapters (both set a dark bg + light text).
      theme: "dark",
      centered: true,
      kicker: "Section 02",
      title: "Key Findings",
      blocks: [
        {
          type: "prose",
          content:
            "Each document within the corpus provides unique insights into how major corporations articulate their terms of service and privacy policies.\n\n### Sub-finding on a dark chapter\n\n- First bullet point about data protection.",
        },
      ],
    },
  ],
};

/** sRGB relative luminance (WCAG) from a computed `rgb()/rgba()` string. */
function relLuminance(rgb: string): number {
  const parts = (rgb.match(/[\d.]+/g) ?? []).map(Number);
  const [r, g, b] = parts;
  const lin = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

test("dark chapters keep readable (light-on-dark) text", async ({
  mount,
  page,
}) => {
  await mount(<CamlDirectiveRendererTestWrapper document={DOC} />);

  const darkPara = page.getByText("Each document within the corpus");
  await expect(darkPara).toBeVisible({ timeout: 5000 });
  await darkPara.scrollIntoViewIfNeeded();

  // The dark section's background must actually be dark...
  const bgLum = await darkPara.evaluate((el) => {
    let node: HTMLElement | null = el as HTMLElement;
    while (node) {
      const bg = getComputedStyle(node).backgroundColor;
      if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") return bg;
      node = node.parentElement;
    }
    return "rgb(255, 255, 255)";
  });
  expect(relLuminance(bgLum)).toBeLessThan(0.15);

  // ...and every text path must be light enough to read against it.
  // 1. library-colored paragraph (ProseContainer p -> darkProse)
  const paraLum = relLuminance(
    await darkPara.evaluate((el) => getComputedStyle(el).color)
  );
  expect(paraLum).toBeGreaterThan(0.5);

  // 2. markdown heading the library does NOT color (inherits section color)
  const subheading = page.getByRole("heading", {
    name: "Sub-finding on a dark chapter",
  });
  const headingLum = relLuminance(
    await subheading.evaluate((el) => getComputedStyle(el).color)
  );
  expect(headingLum).toBeGreaterThan(0.5);

  // 3. per-chapter library title (ChapterTitle -> surfaceLight)
  const title = page.getByRole("heading", { name: "Key Findings" });
  const titleLum = relLuminance(
    await title.evaluate((el) => getComputedStyle(el).color)
  );
  expect(titleLum).toBeGreaterThan(0.5);

  // Contrast guard: text clearly brighter than its background.
  expect(paraLum - relLuminance(bgLum)).toBeGreaterThan(0.3);
});

test("light chapters keep dark text (no over-correction)", async ({
  mount,
  page,
}) => {
  await mount(<CamlDirectiveRendererTestWrapper document={DOC} />);

  const lightPara = page.getByText("This paragraph sits on a light chapter");
  await expect(lightPara).toBeVisible({ timeout: 5000 });

  const lum = relLuminance(
    await lightPara.evaluate((el) => getComputedStyle(el).color)
  );
  // proseText (#334155) on a light section — must stay dark.
  expect(lum).toBeLessThan(0.25);
});
