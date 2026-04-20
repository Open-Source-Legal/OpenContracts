// Playwright Component Test for PipelineIcons (visual catalog + icon mapping)
import React from "react";
import { test, expect } from "./utils/coverage";
import {
  PipelineIconCatalogWrapper,
  PipelineIconPropsWrapper,
  PipelineIconDispatcherWrapper,
  PipelineDisplayNameWrapper,
} from "./PipelineIconsTestWrapper";
import { PIPELINE_ICON_NAMES } from "./pipeline-icons.ct-constants";

test.describe("PipelineIcons — full catalog rendering", () => {
  test("mounts every exported icon component at default size", async ({
    mount,
    page,
  }) => {
    const component = await mount(<PipelineIconCatalogWrapper />);

    const catalog = page.locator('[data-testid="pipeline-icon-catalog"]');
    await expect(catalog).toBeVisible();

    // Each icon cell should render its name label and some visual element
    // (either an <img> for brand logos or an <svg> for geometric icons).
    for (const name of PIPELINE_ICON_NAMES) {
      const cell = page.locator(`[data-testid="icon-cell-${name}"]`);
      await expect(cell).toBeVisible();
      await expect(cell).toContainText(name);
      const visual = cell.locator("img, svg");
      await expect(visual.first()).toBeVisible();
    }

    await component.unmount();
  });

  test("brand icons render as <img> with correct alt text", async ({
    mount,
    page,
  }) => {
    const component = await mount(<PipelineIconCatalogWrapper />);

    // Docling + LlamaIndex + Sentence Transformers logos are imported SVG
    // assets wrapped in <img>; the inline-SVG icons should not be <img>.
    const doclingCell = page.locator('[data-testid="icon-cell-DoclingIcon"]');
    await expect(doclingCell.locator("img[alt='Docling']")).toBeVisible();

    const llamaCell = page.locator('[data-testid="icon-cell-LlamaParseIcon"]');
    await expect(llamaCell.locator("img[alt='LlamaIndex']")).toBeVisible();

    const sentenceCell = page.locator(
      '[data-testid="icon-cell-SentenceTransformerIcon"]'
    );
    await expect(
      sentenceCell.locator("img[alt='Sentence Transformers']")
    ).toBeVisible();

    // Inline-SVG icon example: TextParserIcon should not render an <img>.
    const textCell = page.locator('[data-testid="icon-cell-TextParserIcon"]');
    await expect(textCell.locator("img")).toHaveCount(0);
    await expect(textCell.locator("svg")).toHaveCount(1);

    await component.unmount();
  });

  test("icons accept size and className props", async ({ mount, page }) => {
    const component = await mount(<PipelineIconPropsWrapper />);

    // Confirm every icon renders in every prop configuration (default + two
    // custom sizes). This exercises the spread/default-value branches in
    // BrandIcon and each inline-SVG component.
    for (const name of PIPELINE_ICON_NAMES) {
      const cell = page.locator(`[data-testid="icon-props-${name}"]`);
      await expect(cell).toBeVisible();
      const visuals = cell.locator("img, svg");
      await expect(visuals).toHaveCount(3);
    }

    // Custom className must propagate to the rendered element. This covers
    // the `className` prop forwarding path in both BrandIcon and the inline
    // SVG components.
    const anyCustom = page.locator(".custom-icon-class").first();
    await expect(anyCustom).toBeVisible();

    const anyLarge = page.locator(".large-icon").first();
    await expect(anyLarge).toBeVisible();

    await component.unmount();
  });
});

test.describe("PipelineIcons — getComponentIcon dispatcher", () => {
  // Every branch of the dispatcher tree, including the compound "pdf + thumb"
  // pattern that must beat the "pdf"-only path.
  const dispatcherCases: { className: string; expected: string }[] = [
    // Compound patterns first
    {
      className: "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
      expected: "PdfThumbnailIcon",
    },
    {
      className:
        "opencontractserver.pipeline.thumbnailers.text_thumb.TextThumbnailer",
      expected: "TextThumbnailIcon",
    },
    {
      className:
        "opencontractserver.pipeline.embedders.modernbert.ModernBertEmbedder",
      expected: "ModernBertIcon",
    },
    {
      className:
        "opencontractserver.pipeline.embedders.modern_bert.ModernBertEmbedder",
      expected: "ModernBertIcon",
    },
    // Specific parser/embedder patterns
    {
      className: "opencontractserver.pipeline.parsers.docling.DoclingParser",
      expected: "DoclingIcon",
    },
    {
      className: "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      expected: "LlamaParseIcon",
    },
    {
      className:
        "opencontractserver.pipeline.embedders.multimodal.MultimodalEmbedder",
      expected: "MultimodalIcon",
    },
    {
      className:
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder",
      expected: "SentenceTransformerIcon",
    },
    // Generic text parser (checked after thumb combos)
    {
      className: "opencontractserver.pipeline.parsers.text_parser.TextParser",
      expected: "TextParserIcon",
    },
    {
      className: "opencontractserver.pipeline.parsers.oc_text.OcTextParser",
      expected: "TextParserIcon",
    },
    // Fallback
    {
      className: "opencontractserver.some.made.up.UnknownThing",
      expected: "GenericComponentIcon",
    },
  ];

  test("maps each className pattern to the expected icon component", async ({
    mount,
    page,
  }) => {
    const classNames = dispatcherCases.map((c) => c.className);
    const component = await mount(
      <PipelineIconDispatcherWrapper classNames={classNames} />
    );

    await expect(
      page.locator('[data-testid="pipeline-icon-dispatcher"]')
    ).toBeVisible();

    for (const { className, expected } of dispatcherCases) {
      const cell = page.locator(`[data-testid="dispatched-${className}"]`);
      await expect(cell).toBeVisible();
      await expect(cell).toHaveAttribute("data-resolved-icon", expected);
      // Rendered icon must produce a visual element.
      await expect(cell.locator("img, svg").first()).toBeVisible();
    }

    await component.unmount();
  });
});

test.describe("PipelineIcons — getComponentDisplayName", () => {
  test("derives a friendly name from a class path and applies acronyms", async ({
    mount,
    page,
  }) => {
    const samples = [
      // Title override beats derivation — first branch in the helper.
      {
        className: "opencontractserver.pipeline.parsers.docling.DoclingParser",
        title: "Docling (ML)",
      },
      // CamelCase conversion without an acronym.
      {
        className: "opencontractserver.pipeline.parsers.docling.DoclingParser",
      },
      // Acronym replacement: "openai" -> "OpenAI".
      {
        className:
          "opencontractserver.pipeline.embedders.openai.OpenaiEmbedder",
      },
      // Acronym replacement: "pdf" -> "PDF".
      {
        className:
          "opencontractserver.pipeline.thumbnailers.pdf.PdfThumbnailer",
      },
      // Plain class path with no acronyms or title — hits final `trim`.
      {
        className: "opencontractserver.something.Generic",
      },
    ];
    const component = await mount(
      <PipelineDisplayNameWrapper samples={samples} />
    );

    await expect(
      page.locator('[data-testid="pipeline-display-names"]')
    ).toBeVisible();

    const cellText = async (idx: number) =>
      (await page
        .locator(`[data-testid="display-name-${idx}"]`)
        .textContent()) || "";

    // Title override: exact passthrough (no CamelCase rewriting).
    expect((await cellText(0)).trim()).toBe("Docling (ML)");

    // No title: "DoclingParser" -> "Docling Parser"
    expect((await cellText(1)).trim()).toBe("Docling Parser");

    // Acronym replacement: "OpenaiEmbedder" -> "Openai Embedder" ->
    // "OpenAI Embedder" after acronym fix.
    expect((await cellText(2)).trim()).toBe("OpenAI Embedder");

    // "PdfThumbnailer" -> "Pdf Thumbnailer" -> "PDF Thumbnailer".
    expect((await cellText(3)).trim()).toBe("PDF Thumbnailer");

    // Plain pass through CamelCase split.
    expect((await cellText(4)).trim()).toBe("Generic");
  });
});
