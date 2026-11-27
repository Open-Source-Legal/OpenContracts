import React from "react";
import type { Locator } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import {
  DocxAnnotatorTestWrapper,
  DocxAnnotatorEditableWrapper,
} from "./DocxAnnotatorTestWrapper";
import { sampleDocText } from "./DocxAnnotatorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { setupDocxodusWasm } from "./utils/docxodusWasm";
import { setupDocxFixture } from "./utils/docxFixture";

// WASM initialization + DOCX conversion needs generous timeouts. The
// viewer's frame is mounted at once; its content appears when the document
// has been converted, hence the long waits on `[data-rca-docx-frame]`.
test.setTimeout(60_000);

/**
 * Waits until the viewer has projected the annotation or highlight `id`.
 * The pagination keeps an invisible staging copy of the document, so this
 * counts the projected parts rather than asking for a visible one.
 */
async function expectProjected(content: Locator, id: string) {
  await expect
    .poll(() => content.locator(`[data-annotation-id="${id}"]`).count(), {
      timeout: 15_000,
    })
    .toBeGreaterThan(0);
}

test("DocxAnnotator renders DOCX content via WASM", async ({ mount, page }) => {
  // Load the runtime from the built assets, as the deployed frontend does.
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorTestWrapper />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expect(content).toContainText("Hello World");

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

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expectProjected(content, "ann-1");
  await expectProjected(content, "ann-2");

  await docScreenshot(page, "annotator--docx-annotator--with-annotations");

  await component.unmount();
});

test("DocxAnnotator renders in read-only mode", async ({ mount, page }) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorTestWrapper readOnly={true} />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });

  await docScreenshot(page, "annotator--docx-annotator--read-only");

  await component.unmount();
});

test("DocxAnnotator renders with search result highlights", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(
    <DocxAnnotatorTestWrapper
      searchResults={[
        // "Important Clause" at offset 84–100 in the Docxodus-extracted text
        {
          id: 1,
          start_index: 84,
          end_index: 100,
          text: "Important Clause",
          fullContext: null,
        },
      ]}
    />
  );

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  // The search hit is projected as a highlight over its span.
  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expectProjected(content, "__search__:1");

  await component.unmount();
});

test("DocxAnnotator renders chat-source highlights (selected vs unselected)", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(
    <DocxAnnotatorTestWrapper
      chatSources={[
        {
          start_index: 84,
          end_index: 100,
          sourceId: "source-a",
          messageId: "msg-1",
        },
        {
          start_index: 118,
          end_index: 132,
          sourceId: "source-b",
          messageId: "msg-1",
        },
      ]}
      selectedChatSourceId="source-a"
    />
  );

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  // Picking one source shows that source alone, as the active highlight.
  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expectProjected(content, "__chat_source__:msg-1.0");
  await expect(
    content.locator('[data-annotation-id="__chat_source__:msg-1.0"]').first()
  ).toHaveAttribute("data-label-id", "__highlight_active__");
  await expect(
    content.locator('[data-annotation-id="__chat_source__:msg-1.1"]')
  ).toHaveCount(0);

  await component.unmount();
});

test("DocxAnnotator honors visibleLabels filter via CSS visibility rules", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(
    <DocxAnnotatorTestWrapper
      withAnnotations={true}
      // Only allow label-1 to be visible; label-2 annotations are hidden via CSS
      visibleLabels={[
        {
          id: "label-1",
          text: "Important Clause",
          color: "#FF6B6B",
          icon: "tag",
          description: "",
          labelType: "SPAN_LABEL" as any,
        },
      ]}
    />
  );

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expectProjected(content, "ann-1");
  await expect(content.locator('[data-annotation-id="ann-2"]')).toHaveCount(0);

  await component.unmount();
});

test("DocxAnnotator renders structural annotations when toggle is on", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(
    <DocxAnnotatorTestWrapper withStructuralAnnotation={true} />
  );

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });
  await expectProjected(content, "struct-ann-1");

  await component.unmount();
});

test("DocxAnnotator respects zoom level prop", async ({ mount, page }) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorTestWrapper zoomLevel={1.5} />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });

  await component.unmount();
});

// docxodus' pagination renders text with zero bounding rects in Playwright
// CT (the pagination engine needs a real viewport to compute page
// dimensions). This test requires mouse-drag at screen coordinates, which
// fails when getBoundingClientRect returns zeros. The feature works in the
// live app.
// TODO: Re-enable when the pagination supports headless rendering.
test.fixme("DocxAnnotator disambiguates repeated text by selecting correct occurrence", async ({
  mount,
  page,
}) => {
  await setupDocxodusWasm(page);
  await setupDocxFixture(page);

  const component = await mount(<DocxAnnotatorEditableWrapper />);

  const annotator = page.getByTestId("docx-annotator");
  await annotator.waitFor({ state: "visible", timeout: 45_000 });

  const content = annotator.locator("[data-rca-docx-frame]");
  await expect(content).toBeVisible({ timeout: 45_000 });

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
    const el = document.querySelector("[data-rca-docx-frame]");
    if (!el) throw new Error("No [data-rca-docx-frame] element");

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

  // The selection menu should appear
  const annotateButton = page.getByTestId("apply-label-button");
  await annotateButton.waitFor({ state: "visible", timeout: 5_000 });

  // Apply the active label to create the annotation
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
});
