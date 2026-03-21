import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import {
  DocxAnnotatorTestWrapper,
  DocxAnnotatorEditableWrapper,
} from "./DocxAnnotatorTestWrapper";
import { sampleDocText } from "./DocxAnnotatorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { setupDocxodusWasm } from "./utils/docxodusWasm";
import { setupDocxFixture } from "./utils/docxFixture";

// WASM initialization + DOCX conversion needs generous timeouts
test.setTimeout(60_000);

test("DocxAnnotator renders DOCX content via WASM", async ({ mount, page }) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorTestWrapper />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator(".docx-content");
  await expect(content).toBeVisible();

  await docScreenshot(page, "annotator--docx-annotator--rendered");

  await component.unmount();
});

test("DocxAnnotator renders with annotations projected", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(
    <DocxAnnotatorTestWrapper withAnnotations={true} />
  );

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator(".docx-content");
  await expect(content).toBeVisible();

  await docScreenshot(page, "annotator--docx-annotator--with-annotations");

  await component.unmount();
});

test("DocxAnnotator renders in read-only mode", async ({ mount, page }) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorTestWrapper readOnly={true} />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator(".docx-content");
  await expect(content).toBeVisible();

  await docScreenshot(page, "annotator--docx-annotator--read-only");

  await component.unmount();
});

// PaginatedDocument renders text with zero bounding rects in Playwright CT
// (the pagination engine needs a real viewport to compute page dimensions).
// This test requires mouse-drag at screen coordinates, which fails when
// getBoundingClientRect returns zeros. The feature works in the live app.
// TODO: Re-enable when PaginatedDocument supports headless rendering or
// when we add an unpaginated test mode prop to DocxAnnotator.
test.fixme(
  "DocxAnnotator disambiguates repeated text by selecting correct occurrence",
  async ({ mount, page }) => {
    await setupDocxodusWasm(page);
    await setupDocxFixture(page);

    const component = await mount(<DocxAnnotatorEditableWrapper />);

    const annotator = page.getByTestId("docx-annotator");
    await annotator.waitFor({ state: "visible", timeout: 45_000 });

    const content = annotator.locator(".docx-content");
    await expect(content).toBeVisible();

    // sampleDocText has "This" at two positions:
    //   First:  index 13 ("Hello World. This is...")
    //   Second: index 57 ("This paragraph contains...")
    // Offsets are pinned to docxodus@5.5.0 and the sampleDocText fixture
    // defined in DocxAnnotatorTestWrapper.tsx. Update if either changes.
    const FIRST_THIS_OFFSET = 13;
    const SECOND_THIS_OFFSET = 57;

    // Sanity check: verify sampleDocText actually has "This" at the pinned
    // offsets. If a docxodus version bump changes text extraction, this gives
    // a clear failure message rather than a cryptic offset mismatch later.
    expect(
      sampleDocText.substring(FIRST_THIS_OFFSET, FIRST_THIS_OFFSET + 4)
    ).toBe("This");
    expect(
      sampleDocText.substring(SECOND_THIS_OFFSET, SECOND_THIS_OFFSET + 4)
    ).toBe("This");

    // Find the second occurrence of "This" in the rendered DOM and get its
    // bounding rect so we can drag-select it with the mouse.
    const coords = await page.evaluate(() => {
      const el = document.querySelector(".docx-content");
      if (!el) throw new Error("No .docx-content element");

      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      let occurrenceCount = 0;

      while ((node = walker.nextNode())) {
        const text = node.textContent || "";
        let searchStart = 0;
        while (true) {
          const idx = text.indexOf("This", searchStart);
          if (idx === -1) break;
          occurrenceCount++;
          if (occurrenceCount === 2) {
            const range = document.createRange();
            range.setStart(node, idx);
            range.setEnd(node, idx + 4);
            const rect = range.getBoundingClientRect();
            return {
              x: rect.x,
              y: rect.y,
              right: rect.right,
              height: rect.height,
            };
          }
          searchStart = idx + 1;
        }
      }
      throw new Error(
        `Only found ${occurrenceCount} occurrences of "This" in DOM`
      );
    });

    // Drag-select the second "This" using mouse events
    const midY = coords.y + coords.height / 2;
    await page.mouse.move(coords.x, midY);
    await page.mouse.down();
    await page.mouse.move(coords.right, midY);
    await page.mouse.up();

    // The annotation creation menu should appear
    const annotateButton = page.getByText("Annotate Selection");
    await annotateButton.waitFor({ state: "visible", timeout: 5_000 });

    // Click "Annotate Selection" to create the annotation
    await annotateButton.click();

    // The wrapper exposes the created annotation data in a hidden element
    const lastAnnotation = page.getByTestId("last-annotation");
    await lastAnnotation.waitFor({ state: "visible", timeout: 5_000 });

    const start = parseInt(
      (await lastAnnotation.getAttribute("data-start"))!,
      10
    );
    const end = parseInt((await lastAnnotation.getAttribute("data-end"))!, 10);

    // The annotation should be at the SECOND occurrence (index 57),
    // NOT the first (index 13). This proves DOM-based disambiguation works.
    expect(start).toBe(SECOND_THIS_OFFSET);
    expect(end).toBe(SECOND_THIS_OFFSET + 4);

    await component.unmount();
  }
);
