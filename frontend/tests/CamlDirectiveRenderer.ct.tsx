/**
 * Playwright component tests for CamlDirectiveRenderer.
 *
 * Tests cover:
 * 1. Directive extraction and rendering via mock handler
 * 2. Directives are stripped from visible prose text
 * 3. Multiple directives across chapters
 * 4. Duplicate prose block disambiguation
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import type { CamlDocument } from "@os-legal/caml";
import { CamlDirectiveRendererTestWrapper } from "./CamlDirectiveRendererTestWrapper";
import { DOCUMENT_WITH_DUPLICATES } from "./CamlDirectiveRendererFixtures";

test.describe("CamlDirectiveRenderer - Basic Rendering", () => {
  test("should render prose with directives resolved into mock chips", async ({
    mount,
    page,
  }) => {
    const component = await mount(<CamlDirectiveRendererTestWrapper />);

    // Wait for the article to render
    await expect(page.getByText("Introduction")).toBeVisible({
      timeout: 10000,
    });

    // Directive syntax should NOT be visible
    await expect(page.locator("text={{@cite")).toHaveCount(0);

    // Mock citation chips should be rendered (at least one)
    const chips = page.locator("[data-testid^='mock-citation-']");
    await expect(chips.first()).toBeVisible({ timeout: 5000 });

    // The chip should contain the agent name
    await expect(chips.first()).toContainText("@cite:");

    await docScreenshot(page, "caml--directive-renderer--with-citations");

    await component.unmount();
  });

  test("should render paragraph-scope directives with args", async ({
    mount,
    page,
  }) => {
    const component = await mount(<CamlDirectiveRendererTestWrapper />);

    // Wait for the analysis chapter to render
    await expect(page.getByText("Analysis")).toBeVisible({ timeout: 10000 });

    // Both intro and analysis chapters should produce mock chips
    const chips = page.locator("[data-testid^='mock-citation-']");
    const chipCount = await chips.count();
    expect(chipCount).toBeGreaterThanOrEqual(2);

    await component.unmount();
  });
});

test.describe("CamlDirectiveRenderer - Mobile Layout", () => {
  test("should keep full-width CAML chapters inside mobile viewport gutters", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    const mobileDocument: CamlDocument = {
      frontmatter: {},
      chapters: [
        {
          id: "questions",
          kicker: "Section 03",
          title: "Questions Presented",
          theme: "dark",
          gradient: true,
          blocks: [
            {
              type: "prose",
              content:
                'The petition presented two questions; the Court granted review only on the first.\n\n>>> "Whether the court of appeals erred in holding that the Education Act does not permit the assessment of borrower defenses to repayment before default."',
            },
          ],
        },
      ],
    };

    const component = await mount(
      <CamlDirectiveRendererTestWrapper document={mobileDocument} />
    );

    const section = page.locator("article > section").first();
    await expect(section).toBeVisible({ timeout: 10000 });

    const viewport = page.viewportSize()!;
    const sectionBox = await section.boundingBox();
    expect(sectionBox).not.toBeNull();
    expect(sectionBox!.x).toBeGreaterThanOrEqual(0);
    expect(sectionBox!.width).toBeLessThanOrEqual(viewport.width);

    const headingBox = await page
      .getByRole("heading", { name: "Questions Presented" })
      .boundingBox();
    expect(headingBox).not.toBeNull();
    expect(headingBox!.x).toBeGreaterThanOrEqual(16);

    const scrollWidth = await page.evaluate(() =>
      Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
    );
    expect(scrollWidth).toBeLessThanOrEqual(viewport.width);

    await component.unmount();
  });
});

test.describe("CamlDirectiveRenderer - Reading Layer", () => {
  test("should apply the long-form reading layer to article prose and headings", async ({
    mount,
    page,
  }) => {
    // Desktop width so the 720px reading-measure cap and full heading
    // hierarchy (h2/h3/h4) are exercised, not the mobile full-width override.
    await page.setViewportSize({ width: 1280, height: 1024 });

    const readingDocument: CamlDocument = {
      frontmatter: {
        title: "Reading Layer Demo",
      },
      chapters: [
        {
          id: "overview",
          title: "Overview",
          blocks: [
            {
              type: "prose",
              content:
                "## Background\n\nThis paragraph is rendered through the corpus reading layer, which caps the line measure, opens up vertical rhythm, and restores body contrast so long-form CAML articles read like prose rather than chat bubbles.\n\n### Procedural History\n\nNested sections keep a clear hierarchy. The h3 sits below the h2 in size and weight.\n\n#### Deeper Heading\n\nEven h4 and deeper headings stay legible instead of inheriting browser defaults inside the scoped section.\n\n- First list item with comfortable spacing.\n- Second list item to show vertical rhythm.",
            },
          ],
        },
      ],
    };

    const component = await mount(
      <CamlDirectiveRendererTestWrapper document={readingDocument} />
    );

    // The reading layer is scoped to article > section, so confirm a styled
    // section heading renders before snapshotting the typography.
    const heading = page.getByRole("heading", { name: "Background" });
    await expect(heading).toBeVisible({ timeout: 10000 });

    // h2 should pick up the bold, tokenized 3xl size and the teal hairline rule.
    const h2Weight = await heading.evaluate(
      (el) => getComputedStyle(el).fontWeight
    );
    expect(Number(h2Weight)).toBe(600);
    const h2BorderBottom = await heading.evaluate(
      (el) => getComputedStyle(el).borderBottomWidth
    );
    expect(h2BorderBottom).toBe("1px");

    // Section measure should be capped at the reading-measure token (720px).
    const section = page.locator("article > section").first();
    const sectionBox = await section.boundingBox();
    expect(sectionBox).not.toBeNull();
    expect(sectionBox!.width).toBeLessThanOrEqual(720);

    await docScreenshot(page, "corpus--caml-article-frame--reading-layer");

    await component.unmount();
  });
});

test.describe("CamlDirectiveRenderer - Duplicate Content", () => {
  test("should render correct directives for duplicate prose blocks", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlDirectiveRendererTestWrapper document={DOCUMENT_WITH_DUPLICATES} />
    );

    // Wait for content to render
    await expect(page.getByText("Duplicate Content Test")).toBeVisible({
      timeout: 10000,
    });

    // Each duplicate prose block should have its own mock citation chip
    const chips = page.locator("[data-testid^='mock-citation-']");
    const chipCount = await chips.count();
    expect(chipCount).toBe(2);

    await docScreenshot(page, "caml--directive-renderer--duplicate-blocks");

    await component.unmount();
  });
});
