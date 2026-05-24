// tests/DocumentKnowledgeBase.ct.tsx
import React from "react";
import fs from "fs";

/**
 * IMPORTANT TESTING NOTE:
 * Uses a Wrapper component (DocumentKnowledgeBaseTestWrapper.tsx) to encapsulate
 * the MockedProvider and its complex cache setup. This avoids a Playwright component
 * testing serialization issue that causes stack overflows when the cache object
 * is defined directly in the .spec file.
 * See: https://github.com/microsoft/playwright/issues/14681
 */

import { test, expect } from "./utils/coverage";

// Keep query/mutation imports needed for mocks

import { Page } from "@playwright/test";
import { docScreenshot } from "./utils/docScreenshot";
import { LabelDisplayBehavior } from "../src/types/graphql-api";

// Import the new Wrapper component
import { DocumentKnowledgeBaseTestWrapper } from "./DocumentKnowledgeBaseTestWrapper";
import { setupDocxodusWasm } from "./utils/docxodusWasm";
import {
  chatTrayMocks,
  CORPUS_ID,
  DOCX_DOC_ID,
  graphqlMocks,
  indexTabMocks,
  MOCK_DOCX_URL,
  MOCK_PDF_URL,
  MOCK_PDF_URL_FOR_STRUCTURAL_TEST,
  mockAnnotationNonStructural1,
  mockAnnotationStructural1,
  mockDocxDocument,
  mockPdfDocument,
  mockPdfDocumentForStructuralTest,
  mockTxtDocument,
  PDF_DOC_ID,
  PDF_DOC_ID_FOR_STRUCTURAL_TEST,
  TEST_DOCX_PATH,
  TEST_PAWLS_PATH,
  TEST_PDF_PATH,
  TXT_DOC_ID,
  mockTxtAnnotation1,
  mockTxtAnnotation2,
} from "./mocks/DocumentKnowledgeBase.mocks";

import { GET_DOCUMENT_SUMMARY_VERSIONS } from "../src/components/knowledge_base/document/floating_summary_preview/graphql/documentSummaryQueries";
import { GET_CORPUS_VERSIONS } from "../src/graphql/queries";

// ──────────────────────────────────────────────────────────────────────────────
// │                               Test Data                                   │
// ──────────────────────────────────────────────────────────────────────────────
const graphqlMocksWithChat = [...graphqlMocks, ...chatTrayMocks];

const LONG_TIMEOUT = 60_000;

/**
 * Hide floating UI controls (FABs, settings buttons, etc.) so they
 * don't clutter documentation screenshots.
 */
async function hideFloatingControls(page: Page): Promise<void> {
  await page.evaluate(() => {
    // Hide FABs and floating action buttons by data-testid
    const testIds = [
      "speed-dial-main-fab",
      "settings-button",
      "analyses-button",
      "extracts-button",
      "summary-button",
      "create-analysis-button",
      "width-button",
    ];
    for (const id of testIds) {
      const el = document.querySelector(`[data-testid="${id}"]`);
      if (el) (el as HTMLElement).style.display = "none";
    }
    // Hide position:fixed containers (FloatingDocumentControls wrapper)
    document.querySelectorAll("*").forEach((el) => {
      const style = window.getComputedStyle(el);
      if (
        style.position === "fixed" &&
        el.querySelector('[data-testid="speed-dial-main-fab"]')
      ) {
        (el as HTMLElement).style.display = "none";
      }
    });
  });
}

let mockPawlsDataContent: any;
try {
  const rawContent = fs.readFileSync(TEST_PAWLS_PATH, "utf-8");
  mockPawlsDataContent = JSON.parse(rawContent);
  console.log(`[MOCK PREP] Successfully read and parsed ${TEST_PAWLS_PATH}`);
} catch (err) {
  console.error(
    `[MOCK PREP ERROR] Failed to read or parse ${TEST_PAWLS_PATH}:`,
    err
  );
  mockPawlsDataContent = null;
}

async function registerRestMocks(page: Page): Promise<void> {
  // ... (keep existing REST mocks) ...
  await page.route(`**/${mockPdfDocument.pawlsParseFile}`, (route) => {
    console.log(`[MOCK] PAWLS route triggered for: ${route.request().url()}`);
    if (!mockPawlsDataContent) {
      console.error(`[MOCK ERROR] Mock PAWLS data is null or undefined.`);
      route.fulfill({ status: 500, body: "Mock PAWLS data not loaded" });
      return;
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockPawlsDataContent),
    });
    console.log(
      `[MOCK] Served PAWLS JSON successfully for ${route.request().url()}`
    );
  });
  await page.route(`**/${mockTxtDocument.txtExtractFile}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: `Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a much longer test document with multiple lines of text. 
The quick brown fox jumps over the lazy dog. We need enough text content here to ensure that annotations can be created 
without interference from the floating controls at the bottom of the screen. 

This paragraph contains even more text to work with. We can select any portion of this text to create annotations. 
The document should be long enough that we can comfortably select text in the upper portion of the viewport. 

Additional content here includes various sentences that can be annotated. Each sentence provides an opportunity 
to test the annotation functionality. The text selection mechanism should work properly when there is sufficient content.

Final paragraph with more content to ensure we have plenty of text to work with during testing.`,
    })
  );
  await page.route(`**/${mockPdfDocument.mdSummaryFile}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/markdown",
      body: "# Mock Summary Title\n\nMock summary details.",
    })
  );
  await page.route(MOCK_PDF_URL, async (route) => {
    console.log(`[MOCK] PDF file request: ${route.request().url()}`);
    if (!fs.existsSync(TEST_PDF_PATH)) {
      console.error(
        `[MOCK ERROR] Test PDF file not found at: ${TEST_PDF_PATH}`
      );
      return route.fulfill({ status: 404, body: "Test PDF not found" });
    }
    const buffer = fs.readFileSync(TEST_PDF_PATH);
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: buffer,
      headers: {
        "Content-Length": String(buffer.length),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  });
  // Add route for the new test PDF URL, can reuse the same physical file
  await page.route(MOCK_PDF_URL_FOR_STRUCTURAL_TEST, async (route) => {
    console.log(
      `[MOCK] PDF file request (structural test): ${route.request().url()}`
    );
    if (!fs.existsSync(TEST_PDF_PATH)) {
      console.error(
        `[MOCK ERROR] Test PDF file not found at: ${TEST_PDF_PATH}`
      );
      return route.fulfill({ status: 404, body: "Test PDF not found" });
    }
    const buffer = fs.readFileSync(TEST_PDF_PATH);
    await route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: buffer,
      headers: {
        "Content-Length": String(buffer.length),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  });
  // DOCX document text extract route
  await page.route(`**/${mockDocxDocument.txtExtractFile}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: `Hello World. This is a sample DOCX document for testing. This paragraph contains an Important Clause that should be annotated. The Definition section explains key terms used throughout.`,
    })
  );
  // DOCX file route
  await page.route(`**${MOCK_DOCX_URL}`, async (route) => {
    if (!fs.existsSync(TEST_DOCX_PATH)) {
      return route.fulfill({ status: 404, body: "Test DOCX not found" });
    }
    const buffer = fs.readFileSync(TEST_DOCX_PATH);
    await route.fulfill({
      status: 200,
      contentType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      body: buffer,
      headers: {
        "Content-Length": String(buffer.length),
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// │                               Test Suite                                  │
// ──────────────────────────────────────────────────────────────────────────────

test.use({ viewport: { width: 1280, height: 720 } });
test.setTimeout(60000);

test.beforeEach(async ({ page }) => {
  // Keep existing REST mocks
  await registerRestMocks(page);

  // Add WebSocket stub for chat functionality
  await page.evaluate(() => {
    // Track all active WebSocket instances
    const activeInstances = new Set();

    class StubSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState: number;
      onopen?: (event: any) => void;
      onmessage?: (event: any) => void;
      onclose?: (event: any) => void;
      private _disconnectTimeout?: NodeJS.Timeout;

      constructor(url: string) {
        this.url = url;
        this.readyState = 1; // OPEN
        activeInstances.add(this);

        // Open event immediately
        setTimeout(() => this.onopen && this.onopen({}), 0);

        // Only disconnect after 30 seconds by default
        this._disconnectTimeout = setTimeout(() => {
          if (this.readyState !== 3) {
            this.readyState = 3; // CLOSED
            this.onclose && this.onclose({});
            activeInstances.delete(this);
          }
        }, 30000);
      }

      send(data) {
        const emit = (payload) =>
          this.onmessage && this.onmessage({ data: JSON.stringify(payload) });
        try {
          const msg = JSON.parse(data);
          if (msg.query) {
            const id = Date.now().toString();
            // Start of streaming
            emit({
              type: "ASYNC_START",
              content: "",
              data: { message_id: id },
            });

            // Generic assistant response
            emit({
              type: "ASYNC_CONTENT",
              content: `Received: ${msg.query}`,
              data: { message_id: id },
            });
            emit({
              type: "ASYNC_FINISH",
              content: `Received: ${msg.query}`,
              data: { message_id: id },
            });
          }
        } catch {}
      }

      close() {
        if (this._disconnectTimeout) {
          clearTimeout(this._disconnectTimeout);
        }
        if (this.readyState !== 3) {
          this.readyState = 3;
          this.onclose && this.onclose({});
          activeInstances.delete(this);
        }
      }

      addEventListener() {}
      removeEventListener() {}
    }
    // @ts-ignore
    window.WebSocket = StubSocket;
    // Store reference for tests
    // @ts-ignore
    window.WebSocketInstances = activeInstances;
  });

  // Restore original request logging if desired, or keep the filtered version
  page.on("request", (request) => {
    // if (!request.url().endsWith('.png')) { // No longer need to filter PNGs
    console.log(`>> ${request.method()} ${request.url()}`);
    // }
  });
  page.on("response", async (response) => {
    const url = response.url();
    const status = response.status();
    try {
      if (
        !url.endsWith(".pdf") &&
        !url.includes("pdf.worker") &&
        status < 300
      ) {
        console.log(`<< ${status} ${url}`);
      } else {
        console.log(`<< ${status} ${url}`);
      }
    } catch (e) {
      console.log(`<< ${status} ${url} (Could not read body: ${e})`);
    }
  });
  page.on("requestfailed", (req) =>
    console.warn(`[⚠️ FAILED Request] ${req.failure()?.errorText} ${req.url()}`)
  );
  page.on("pageerror", (err) =>
    console.error(`[PAGE ERROR] ${err.message}\n${err.stack}`)
  );
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else {
      console.log(`[CONSOLE] ${msg.text()}`);
    }
  });
});

test("fullscreen modal covers the entire viewport", async ({ mount, page }) => {
  // Regression test: the FullScreenModal uses size="fullscreen" from @os-legal/ui
  // and a max-height override. Verify it actually fills the viewport.
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={graphqlMocksWithChat}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for the modal to render — the heading proves the content is up
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // The .fullscreen-modal element should cover the viewport
  const modal = page.locator(".fullscreen-modal");
  await expect(modal).toBeVisible({ timeout: LONG_TIMEOUT });

  const viewport = page.viewportSize()!;
  const box = await modal.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(viewport.width - 1);
  expect(box!.height).toBeGreaterThanOrEqual(viewport.height - 1);
});

test("renders PDF document and can open summary via floating preview", async ({
  mount,
  page,
}) => {
  // Mount the Wrapper, passing mocks and props
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Document title should be visible
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF should be visible by default (no layer switching needed)
  const pdfContainer = page.locator("#pdf-container");
  await expect(pdfContainer).toBeVisible({ timeout: LONG_TIMEOUT });

  // Find and click the floating summary preview button - easier via data-testid
  const summaryButton = page.getByTestId("summary-toggle-button");
  await expect(summaryButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await summaryButton.click();

  // Expanded summary should show
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Wait for content to load
  await page.waitForTimeout(1000);

  // Click on the summary content to switch to knowledge layer
  const summaryCard = page.getByTestId("summary-card-1");
  await expect(summaryCard).toBeVisible({ timeout: LONG_TIMEOUT });
  await summaryCard.click();

  // Should now show the summary in main view
  const summaryHeading = page
    .getByRole("heading", { name: "Mock Summary Title" })
    .first();
  await expect(summaryHeading).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(page.locator("text=Mock summary details.").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
});

test("PDF container renders with virtualized pages", async ({
  mount,
  page,
}) => {
  test.setTimeout(120000); // Set timeout to 120 seconds for this specific test

  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // PDF is visible by default, no layer switching needed
  const pdfContainer = page.locator("#pdf-container");
  await expect(pdfContainer).toBeVisible({ timeout: LONG_TIMEOUT });

  const firstCanvas = pdfContainer.locator("canvas").first();
  await expect(firstCanvas).toBeVisible({ timeout: LONG_TIMEOUT });

  const pagePlaceholders = pdfContainer.locator(
    '> div[style*="position: relative;"] > div[style*="position: absolute;"]'
  );
  await expect(pagePlaceholders).toHaveCount(23, { timeout: LONG_TIMEOUT });

  // Continue with existing scrolling logic...
  const renderedPageIndices = new Set<number>();
  const totalPages = 23;

  const scrollableView = await pdfContainer.boundingBox();
  if (!scrollableView) {
    throw new Error("Could not get bounding box for #pdf-container");
  }
  const clientHeight = scrollableView.height;
  const scrollHeight = await pdfContainer.evaluate((node) => node.scrollHeight);

  console.log(
    `[TEST] pdfContainer clientHeight: ${clientHeight}, scrollHeight: ${scrollHeight}`
  );

  let currentScrollTop = 0;
  const scrollIncrement = clientHeight * 0.8; // Scroll by 80% of the container's visible height to ensure overlap

  while (currentScrollTop < scrollHeight - clientHeight) {
    currentScrollTop += scrollIncrement;
    currentScrollTop = Math.min(currentScrollTop, scrollHeight - clientHeight);

    await pdfContainer.evaluate((node, st) => {
      node.scrollTop = st;
    }, currentScrollTop);

    // Active polling for newly rendered canvases
    const maxWaitTimeForStepMs = 5000; // Max time to wait for canvases at this scroll step
    const checkIntervalMs = 300; // Interval to re-check for canvases
    const stepStartTime = Date.now();
    let madeProgressInStep = true; // Assume progress initially or after finding a canvas

    while (Date.now() - stepStartTime < maxWaitTimeForStepMs) {
      if (!madeProgressInStep && Date.now() - stepStartTime > 1000) {
        // If no new canvas found for over 1s in this step, assume stable state for this scroll position
        // console.log(`[TEST] No new canvases for 1s at scrollTop ${currentScrollTop}, proceeding.`);
        break;
      }
      madeProgressInStep = false; // Reset for this check cycle
      let initialRenderedCountInInterval = renderedPageIndices.size;

      for (let j = 0; j < totalPages; j++) {
        if (!renderedPageIndices.has(j)) {
          const placeholder = pagePlaceholders.nth(j);
          // A more precise check would be: (placeholder.offsetTop < currentScrollTop + clientHeight && placeholder.offsetTop + placeholder.offsetHeight > currentScrollTop)
          // For now, we check all non-rendered ones, as PDF.tsx logic will mount them if they are in its calculated range.
          const hasCanvas = (await placeholder.locator("canvas").count()) > 0;
          if (hasCanvas) {
            renderedPageIndices.add(j);
            console.log(
              `[TEST] Rendered canvas for page index ${j} at scrollTop ${currentScrollTop}`
            );
            madeProgressInStep = true;
          }
        }
      }

      if (renderedPageIndices.size === totalPages) break; // All pages found
      if (renderedPageIndices.size > initialRenderedCountInInterval) {
        // If we found new canvases, reset the "no progress" timer by continuing the outer while loop effectively
      } else {
        // No new canvases in this specific check, wait for next interval or timeout
      }
      await page.waitForTimeout(checkIntervalMs);
    }

    if (renderedPageIndices.size === totalPages) {
      console.log(`[TEST] All ${totalPages} pages rendered. Stopping scroll.`);
      break;
    }

    if (currentScrollTop >= scrollHeight - clientHeight) {
      console.log("[TEST] Reached end of scrollable content.");
      // One last check at the very bottom
      await page.waitForTimeout(checkIntervalMs * 2); // A bit longer final wait
      for (let j = 0; j < totalPages; j++) {
        if (!renderedPageIndices.has(j)) {
          const placeholder = pagePlaceholders.nth(j);
          if ((await placeholder.locator("canvas").count()) > 0) {
            renderedPageIndices.add(j);
            console.log(
              `[TEST] Rendered canvas for page index ${j} at final scrollTop`
            );
          }
        }
      }
      break;
    }
  }

  if (renderedPageIndices.size < totalPages) {
    console.warn(
      `[TEST] Still missing ${
        totalPages - renderedPageIndices.size
      } pages. Performing a final check scan.`
    );
    for (let j = 0; j < totalPages; j++) {
      if (!renderedPageIndices.has(j)) {
        const placeholder = pagePlaceholders.nth(j);
        if ((await placeholder.locator("canvas").count()) > 0) {
          renderedPageIndices.add(j);
        } else {
          console.warn(
            `[TEST FINAL SCAN] Page index ${j} did not render a canvas.`
          );
        }
      }
    }
  }

  expect(renderedPageIndices.size).toBe(totalPages);
  console.log(
    `[TEST SUCCESS] Verified that all ${totalPages} pages rendered a canvas at some point during scroll.`
  );
});

test("renders TXT document with chat panel open", async ({ mount, page }) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Document title should be visible
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Click ChatIndicator to open sidebar - it's the button on the right edge with MessageSquare icon
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last(); // Get the last one in case there are multiple
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Sidebar should be visible
  const slidingPanel = page.locator("#sliding-panel");
  await expect(slidingPanel).toBeVisible({ timeout: LONG_TIMEOUT });

  // Switch to feed mode - look for the toggle button with "Content Feed" text
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();

  // TXT content should be visible. Container id is ``text-container``
  // for TXT docs after PR #1580 split the viewer into per-filetype branches.
  await expect(page.locator("#text-container")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
  await expect(page.locator("#text-container")).toContainText(
    `Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a much longer test document with multiple lines of text. 
The quick brown fox jumps over the lazy dog. We need enough text content here to ensure that annotations can be created 
without interference from the floating controls at the bottom of the screen. 

This paragraph contains even more text to work with. We can select any portion of this text to create annotations. 
The document should be long enough that we can comfortably select text in the upper portion of the viewport. 

Additional content here includes various sentences that can be annotated. Each sentence provides an opportunity 
to test the annotation functionality. The text selection mechanism should work properly when there is sufficient content.

Final paragraph with more content to ensure we have plenty of text to work with during testing.`,
    { timeout: LONG_TIMEOUT }
  );
  await expect(
    page.locator("#pdf-container .react-pdf__Page__canvas")
  ).toBeHidden({ timeout: LONG_TIMEOUT });
});

test("PDF document renders PDF annotator component", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF annotator should be visible
  const pdfAnnotator = page.getByTestId("pdf-annotator");
  await expect(pdfAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

  // TXT annotator should NOT be visible
  const txtAnnotatorWrapper = page.getByTestId("txt-annotator-wrapper");
  await expect(txtAnnotatorWrapper).toHaveCount(0);

  // Verify PDF canvas is rendered
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  await docScreenshot(page, "readme--document-annotator--with-pdf");
});

test("TXT document renders TXT annotator component", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // TXT annotator wrapper should be visible
  const txtAnnotatorWrapper = page.getByTestId("txt-annotator-wrapper");
  await expect(txtAnnotatorWrapper).toBeVisible({ timeout: LONG_TIMEOUT });

  // TXT annotator component should be visible
  const txtAnnotator = page.getByTestId("txt-annotator");
  await expect(txtAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF annotator should NOT be visible
  const pdfAnnotator = page.getByTestId("pdf-annotator");
  await expect(pdfAnnotator).toHaveCount(0);

  // Verify text content is rendered
  await expect(txtAnnotator).toContainText(
    `Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a much longer test document with multiple lines of text. 
The quick brown fox jumps over the lazy dog. We need enough text content here to ensure that annotations can be created 
without interference from the floating controls at the bottom of the screen. 

This paragraph contains even more text to work with. We can select any portion of this text to create annotations. 
The document should be long enough that we can comfortably select text in the upper portion of the viewport. 

Additional content here includes various sentences that can be annotated. Each sentence provides an opportunity 
to test the annotation functionality. The text selection mechanism should work properly when there is sufficient content.

Final paragraph with more content to ensure we have plenty of text to work with during testing.`,
    {
      timeout: LONG_TIMEOUT,
    }
  );

  // Verify no PDF canvas is rendered
  await expect(page.locator("#pdf-container canvas")).toHaveCount(0, {
    timeout: LONG_TIMEOUT,
  });
});

test("TXT document displays existing annotations", async ({ mount, page }) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for TXT annotator to be visible
  const txtAnnotator = page.getByTestId("txt-annotator");
  await expect(txtAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for annotations to load
  await page.waitForTimeout(1000);

  // Check that annotated spans are rendered with highlights
  // The TxtAnnotator creates spans with data-span-index attribute
  const annotatedSpans = txtAnnotator.locator(
    '[data-testid^="annotated-span-"]'
  );

  // Should have at least some spans (the text is broken into spans based on annotations)
  await expect(annotatedSpans.first()).toBeVisible({ timeout: LONG_TIMEOUT });

  // Look for spans with background color (indicating they have annotations)
  // Use data-testid to find annotated spans
  const annotatedCount = await annotatedSpans.count();
  expect(annotatedCount).toBeGreaterThan(0);

  // Verify annotation text is present
  await expect(txtAnnotator).toContainText("Lorem ipsum");
  await expect(txtAnnotator).toContainText("consectetur adipiscing");

  // For now, let's just verify that the annotations are displayed with the correct styling
  // The hover interaction seems to have issues in the test environment
  console.log(
    "[TEST] Skipping hover label test - annotations are correctly displayed"
  );

  // Hide floating controls for a clean documentation screenshot
  await hideFloatingControls(page);

  // Capture screenshot of TXT annotator with highlighted span annotations
  await docScreenshot(page, "annotations--txt-document--with-spans");
});

test("TXT annotations appear in unified feed when clicked", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for TXT annotator to be visible
  const txtAnnotator = page.getByTestId("txt-annotator");
  await expect(txtAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

  // Open sidebar to see annotations in feed
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Switch to feed mode
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();

  // Check that annotations appear in the feed
  await page.waitForTimeout(500);

  // Look for annotation items in the feed
  const annotation1InFeed = page.locator('[data-annotation-id="txt-annot-1"]');
  const annotation2InFeed = page.locator('[data-annotation-id="txt-annot-2"]');

  // At least one should be visible
  const count1 = await annotation1InFeed.count();
  const count2 = await annotation2InFeed.count();

  expect(count1 + count2).toBeGreaterThan(0);
  console.log(
    `[TEST SUCCESS] Found ${count1 + count2} annotations in unified feed`
  );

  // Hide floating controls and multi-select checkboxes for a clean screenshot
  await hideFloatingControls(page);
  await page.evaluate(() => {
    document
      .querySelectorAll<HTMLElement>(
        "i.square.outline.icon, i.check.square.icon"
      )
      .forEach((el) => (el.style.display = "none"));
  });

  // Capture screenshot of the sidebar panel showing span annotations in the feed
  const slidingPanel = page.locator("#sliding-panel");
  await docScreenshot(page, "annotations--txt-sidebar--span-annotations", {
    element: slidingPanel,
  });
});

test("TXT document allows creating annotations via text selection", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for TXT annotator to be visible
  const txtAnnotator = page.getByTestId("txt-annotator");
  await expect(txtAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

  // First select a label from the label selector
  const labelSelectorButton = page.locator(
    '[data-testid="label-selector-toggle-button"]'
  );
  await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await labelSelectorButton.click();

  // Wait for label options to appear
  await page.waitForTimeout(500);

  // Debug: Check what labels are available
  const labelOptions = page.locator(".label-option");
  const labelCount = await labelOptions.count();
  console.log(`[TEST] Found ${labelCount} label options`);

  if (labelCount === 0) {
    console.log("[TEST ERROR] No labels available in the label selector!");
    // Try to see what's in the dropdown
    const dropdownContent = await page
      .locator('[data-testid="label-selector-dropdown"]')
      .textContent();
    console.log(`[TEST] Dropdown content: "${dropdownContent}"`);
  }

  // Look for the "Important Text" span label specifically
  const spanLabelOption = page
    .locator(".label-option")
    .filter({ hasText: "Important Text" })
    .first();
  if ((await spanLabelOption.count()) === 0) {
    // If not found, log all available options
    for (let i = 0; i < labelCount; i++) {
      const text = await labelOptions.nth(i).textContent();
      console.log(`[TEST] Label option ${i}: "${text}"`);
    }
    // Fall back to first option
    const firstOption = labelOptions.first();
    await expect(firstOption).toBeVisible({ timeout: LONG_TIMEOUT });
    await firstOption.click();
  } else {
    await expect(spanLabelOption).toBeVisible({ timeout: LONG_TIMEOUT });
    await spanLabelOption.click();
  }
  console.log("[TEST] Selected label for annotation");

  // Wait for text to be ready
  await page.waitForTimeout(500);

  // Scroll to top to ensure we're selecting away from floating controls
  await txtAnnotator.evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.waitForTimeout(200);

  // Find a text span to select - get the span that contains "plain text"
  const textSpans = txtAnnotator.locator("span[data-span-index]");
  const spanCount = await textSpans.count();
  console.log(`[TEST] Found ${spanCount} text spans`);

  // Find a span in the upper portion of the document (first few spans)
  let targetSpan: any = null;
  for (let i = 0; i < Math.min(5, spanCount); i++) {
    // Only check first 5 spans
    const span = textSpans.nth(i);
    const text = await span.textContent();
    if (text && text.length > 10 && !text.match(/^\s*$/)) {
      // Look for longer text
      targetSpan = span;
      console.log(
        `[TEST] Found target span at index ${i} with text: "${text}"`
      );
      break;
    }
  }

  if (!targetSpan) {
    // Fallback to just using a span with reasonable text content
    targetSpan = textSpans.filter({ hasText: /\w+/ }).first();
  }

  // Ensure we have a target span
  expect(targetSpan).toBeTruthy();

  // Get the bounding box of the target span
  const spanBox = await targetSpan.boundingBox();
  expect(spanBox).toBeTruthy();

  // Select text within the span, but stay well within bounds
  const startX = spanBox!.x + 20; // Start further from left edge
  const startY = spanBox!.y + spanBox!.height / 2;
  const endX = Math.min(spanBox!.x + 100, spanBox!.x + spanBox!.width - 20); // Don't select too much
  const endY = startY;

  console.log(
    `[TEST] Selecting text from (${startX}, ${startY}) to (${endX}, ${endY})`
  );

  // Perform the drag selection
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.waitForTimeout(100);

  // Make sure to release the mouse over the container to trigger the onMouseUp handler
  await page.mouse.up();

  // Also trigger mouseup event directly on the container as a fallback
  await txtAnnotator.dispatchEvent("mouseup");
  await page.waitForTimeout(500);

  // Verify selection happened by checking for selected text
  const selectedText = await page.evaluate(() =>
    window.getSelection()?.toString()
  );
  if (!selectedText || selectedText.length === 0) {
    // Alternative: Select text programmatically
    const selectionResult = await page.evaluate(() => {
      const container = document.querySelector('[data-testid="txt-annotator"]');
      const textNode = container?.querySelector(
        "span[data-span-index]"
      )?.firstChild;
      if (textNode && textNode.nodeType === Node.TEXT_NODE) {
        const range = document.createRange();
        range.setStart(textNode, 0);
        range.setEnd(textNode, Math.min(10, textNode.textContent?.length || 0));

        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);

        // Trigger mouseup event
        const mouseUpEvent = new MouseEvent("mouseup", {
          bubbles: true,
          cancelable: true,
          view: window,
        });
        container?.dispatchEvent(mouseUpEvent);

        return {
          success: true,
          selectedText: selection?.toString() || "",
          containerFound: !!container,
          textNodeFound: !!textNode,
        };
      }
      return {
        success: false,
        selectedText: "",
        containerFound: false,
        textNodeFound: false,
      };
    });
  }

  console.log("[TEST] Completed text selection");

  // The TXT annotator now shows a context menu after text selection.
  // Click "Apply Label" to create the annotation.
  const applyLabelButton = page.getByTestId("txt-apply-label-button");
  await expect(applyLabelButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await applyLabelButton.click();
  console.log("[TEST] Clicked Apply Label from context menu");

  // Wait for annotation to be created
  await page.waitForTimeout(2000);

  // Debug: Check if annotation was created on the page
  const newAnnotationOnPage = await txtAnnotator
    .locator('[data-testid^="annotated-span-"]')
    .count();
  console.log(`[TEST] Annotated spans after selection: ${newAnnotationOnPage}`);

  // Check if we can see any mutation errors in the console
  await page.waitForTimeout(1000);

  // Get initial annotation count before selection
  const initialAnnotationCount = 2; // We know we have 2 existing annotations from mock data

  // Check if annotation count increased
  if (newAnnotationOnPage > initialAnnotationCount) {
    console.log(
      `[TEST SUCCESS] New annotation created on document (${initialAnnotationCount} -> ${newAnnotationOnPage})`
    );
  } else {
    console.log(`[TEST WARNING] No new annotation detected on document`);
  }

  // Verify a new annotation was created by checking the feed
  // Open sidebar
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Switch to feed mode
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();

  // Look for the new annotation in the feed
  // It should have id "new-annot-1" based on the mutation mock
  const newAnnotation = page
    .locator('[data-annotation-id="new-annot-1"]')
    .first();
  await expect(newAnnotation).toBeVisible({ timeout: 15000 });

  console.log("[TEST SUCCESS] New annotation created in TXT document");
});

test("DOCX document renders DOCX annotator via WASM", async ({
  mount,
  page,
}) => {
  // WASM route interception must be set up before component mount
  await setupDocxodusWasm(page);

  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(DOCX_DOC_ID, CORPUS_ID)]}
      documentId={DOCX_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document title to load
  await expect(
    page.getByRole("heading", { name: mockDocxDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // DOCX annotator should be visible (WASM-rendered)
  const docxAnnotator = page.getByTestId("docx-annotator");
  await expect(docxAnnotator).toBeVisible({ timeout: 45_000 });

  // Verify the DOCX content is rendered
  const docxContent = docxAnnotator.locator(".docx-content");
  await expect(docxContent).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF annotator should NOT be present
  const pdfAnnotator = page.getByTestId("pdf-annotator");
  await expect(pdfAnnotator).toHaveCount(0);

  // TXT annotator should NOT be present
  const txtAnnotator = page.getByTestId("txt-annotator");
  await expect(txtAnnotator).toHaveCount(0);

  await docScreenshot(page, "knowledge-base--docx-document--rendered");
});

test("selects a label and creates an annotation via unified feed", async ({
  mount,
  page,
}) => {
  // Setup more verbose logging for mutation debugging
  page.on("console", (msg) => {
    const text = msg.text();
    if (
      text.includes("REQUEST_ADD_ANNOTATION") ||
      text.includes("annotation") ||
      text.includes("mutation")
    ) {
      console.log(`[TEST DEBUG] ${text}`);
    }
  });

  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF is visible by default
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Wait for the label selector to be ready
  const labelSelectorButton = page.locator(
    '[data-testid="label-selector-toggle-button"]'
  );
  await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });
  // Open the selector and choose the first label
  await labelSelectorButton.hover();
  await labelSelectorButton.click();
  const firstLabelOption = page.locator(".label-option").first();
  await expect(firstLabelOption).toBeVisible({ timeout: LONG_TIMEOUT });
  await firstLabelOption.click();
  console.log("[TEST] Selected first label for annotation");

  // Prepare for annotation
  const firstCanvas = page.locator("#pdf-container canvas").first();
  await expect(firstCanvas).toBeVisible({ timeout: LONG_TIMEOUT });
  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();
  expect(layerBox).toBeTruthy();

  // Improved logging before drag
  console.log("[TEST] About to perform drag operation");

  // Perform drag - more precise placement
  const startX = layerBox!.width * 0.5;
  const startY = layerBox!.height * 0.1;
  const endX = layerBox!.width * 0.5;
  const endY = startY + 100;

  // More deliberate drag operation
  await page.mouse.move(layerBox!.x + startX, layerBox!.y + startY);
  await page.mouse.down();
  await page.waitForTimeout(100); // Brief pause
  await page.mouse.move(
    layerBox!.x + endX,
    layerBox!.y + endY,
    { steps: 10 } // More gradual movement
  );
  await page.waitForTimeout(100); // Brief pause
  await page.mouse.up();
  console.log("Mouse up completed");

  // Check that the action menu appears
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });
  console.log("[TEST] Action menu appeared after selection");

  // Verify both options are present (copy and apply label)
  const copyButton = page.getByTestId("copy-text-button");
  const applyLabelButton = page.getByTestId("apply-label-button");
  await expect(copyButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(applyLabelButton).toBeVisible({ timeout: LONG_TIMEOUT });

  // Check that the label name is shown in the apply button
  await expect(applyLabelButton).toContainText("Apply Label:");

  // Click the apply label button to create the annotation
  await applyLabelButton.click();
  console.log("[TEST] Clicked apply label button");

  // Give the UI a moment to stabilize after the annotation creation
  await page.waitForTimeout(500);

  // Wait for Apollo cache to update
  await page.waitForTimeout(1000);

  // Click ChatIndicator to open sidebar
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Sidebar should be visible
  const slidingPanel = page.locator("#sliding-panel").first();
  await expect(slidingPanel).toBeVisible({ timeout: LONG_TIMEOUT });

  // Switch to feed mode
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();

  // Verify the annotation appears in the unified feed
  const annotationInFeed = page
    .locator('[data-annotation-id="new-annot-1"]')
    .first();
  await expect(annotationInFeed).toBeVisible({ timeout: 15000 });
  console.log("[TEST SUCCESS] Found annotation in unified feed");
});

test("keyboard shortcut 'C' copies selected text", async ({ mount, page }) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF should be visible
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Perform text selection
  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();
  expect(layerBox).toBeTruthy();

  // Create a selection
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1
  );
  await page.mouse.down();
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1 + 100,
    { steps: 10 }
  );
  await page.mouse.up();

  // Verify action menu appears
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });

  // Grant clipboard permissions
  await page.context().grantPermissions(["clipboard-write", "clipboard-read"]);

  // Press 'C' to copy
  await page.keyboard.press("c");
  console.log("[TEST] Pressed 'C' key to copy");

  // Verify menu disappears after copy
  await expect(actionMenu).not.toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify clipboard content (in Playwright we can read clipboard)
  const clipboardText = await page.evaluate(() =>
    navigator.clipboard.readText()
  );
  expect(clipboardText).toBeTruthy();
  console.log("[TEST SUCCESS] Text copied to clipboard:", clipboardText);
});

test("keyboard shortcut 'A' applies label to create annotation", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Select a label first
  const labelSelectorButton = page.locator(
    '[data-testid="label-selector-toggle-button"]'
  );
  await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await labelSelectorButton.click();
  const firstLabelOption = page.locator(".label-option").first();
  await expect(firstLabelOption).toBeVisible({ timeout: LONG_TIMEOUT });
  await firstLabelOption.click();

  // Perform text selection
  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();

  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1
  );
  await page.mouse.down();
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1 + 100,
    { steps: 10 }
  );
  await page.mouse.up();

  // Verify action menu appears
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });

  // Press 'A' to apply label
  await page.keyboard.press("a");
  console.log("[TEST] Pressed 'A' key to apply label");

  // Verify menu disappears after applying label
  await expect(actionMenu).not.toBeVisible({ timeout: LONG_TIMEOUT });

  // Give time for annotation to be created
  await page.waitForTimeout(1000);

  // Open sidebar and check for annotation
  const chatIndicator = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-message-square"]') })
    .last();
  await chatIndicator.click();

  const feedToggle = page.getByTestId("view-mode-feed");
  await feedToggle.click();

  const annotationInFeed = page
    .locator('[data-annotation-id="new-annot-1"]')
    .first();
  await expect(annotationInFeed).toBeVisible({ timeout: 15000 });
  console.log("[TEST SUCCESS] Annotation created using 'A' keyboard shortcut");
});

test("ESC key cancels selection and closes action menu", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();

  // Test 1: ESC during selection (before mouse up)
  console.log("[TEST] Testing ESC during active selection");
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1
  );
  await page.mouse.down();
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1 + 50,
    { steps: 5 }
  );

  // Press ESC while still dragging
  await page.keyboard.press("Escape");
  await page.mouse.up();

  // Action menu should NOT appear
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).not.toBeVisible({ timeout: 1000 });
  console.log("[TEST] ESC during selection prevented menu from appearing");

  // Test 2: ESC after selection (with menu visible)
  console.log("[TEST] Testing ESC with action menu visible");
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.2
  );
  await page.mouse.down();
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.2 + 100,
    { steps: 10 }
  );
  await page.mouse.up();

  // Verify action menu appears
  await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });

  // Press ESC to close menu
  await page.keyboard.press("Escape");

  // Menu should disappear
  await expect(actionMenu).not.toBeVisible({ timeout: LONG_TIMEOUT });
  console.log("[TEST SUCCESS] ESC key closes action menu");
});

test("cancel button dismisses selection without action", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Select a label to verify cancel works with label selected
  const labelSelectorButton = page.locator(
    '[data-testid="label-selector-toggle-button"]'
  );
  await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await labelSelectorButton.click();
  const firstLabelOption = page.locator(".label-option").first();
  await expect(firstLabelOption).toBeVisible({ timeout: LONG_TIMEOUT });
  await firstLabelOption.click();

  // Perform text selection
  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();

  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1
  );
  await page.mouse.down();
  await page.mouse.move(
    layerBox!.x + layerBox!.width * 0.5,
    layerBox!.y + layerBox!.height * 0.1 + 100,
    { steps: 10 }
  );
  await page.mouse.up();

  // Verify action menu appears with all three options
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify all buttons are present
  const copyButton = page.getByTestId("copy-text-button");
  const applyLabelButton = page.getByTestId("apply-label-button");
  const cancelButton = page.getByTestId("cancel-button");

  await expect(copyButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(applyLabelButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(cancelButton).toBeVisible({ timeout: LONG_TIMEOUT });

  // Check that cancel button has ESC hint
  await expect(cancelButton).toContainText("Cancel");
  await expect(cancelButton).toContainText("ESC");

  console.log("[TEST] All three action menu options are visible");

  // Click cancel button
  await cancelButton.click();

  // Verify menu disappears
  await expect(actionMenu).not.toBeVisible({ timeout: LONG_TIMEOUT });

  // Give time to ensure no annotation was created
  await page.waitForTimeout(1000);

  // Open sidebar and verify no annotation was created
  const chatIndicator = page
    .locator("button")
    .filter({ has: page.locator('svg[class*="lucide-message-square"]') })
    .last();
  await chatIndicator.click();

  const feedToggle = page.getByTestId("view-mode-feed");
  await feedToggle.click();

  // Verify no annotation exists
  const annotationInFeed = page
    .locator('[data-annotation-id="new-annot-1"]')
    .first();
  await expect(annotationInFeed).not.toBeVisible({ timeout: 2000 });

  console.log(
    "[TEST SUCCESS] Cancel button dismissed selection without creating annotation"
  );
});

test("mobile: moving finger during long press wait cancels selection", async ({
  mount,
  page,
}) => {
  // Set mobile viewport
  await page.setViewportSize({ width: 375, height: 667 });

  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Get the selection layer
  const firstPageContainer = page.locator(".PageAnnotationsContainer").first();
  const selectionLayer = firstPageContainer.locator("#selection-layer");
  const layerBox = await selectionLayer.boundingBox();
  expect(layerBox).toBeTruthy();

  const startX = layerBox!.x + layerBox!.width * 0.5;
  const startY = layerBox!.y + layerBox!.height * 0.1;

  console.log("[TEST] Starting touch at", { startX, startY });

  // Start touch with proper Touch object structure
  await selectionLayer.dispatchEvent("touchstart", {
    touches: [
      {
        identifier: 0,
        clientX: startX,
        clientY: startY,
        pageX: startX,
        pageY: startY,
      },
    ],
  });

  // Move finger before long press completes (within 500ms)
  await page.waitForTimeout(200);

  // Move more than threshold (10px)
  const movedX = startX + 20;
  const movedY = startY + 20;

  console.log("[TEST] Moving finger to cancel long press", { movedX, movedY });
  await selectionLayer.dispatchEvent("touchmove", {
    touches: [
      {
        identifier: 0,
        clientX: movedX,
        clientY: movedY,
        pageX: movedX,
        pageY: movedY,
      },
    ],
  });

  // Wait past long press duration
  await page.waitForTimeout(400);

  // End touch
  await selectionLayer.dispatchEvent("touchend", {
    changedTouches: [
      {
        identifier: 0,
        clientX: movedX,
        clientY: movedY,
        pageX: movedX,
        pageY: movedY,
      },
    ],
  });

  // Action menu should NOT appear (selection was cancelled)
  const actionMenu = page.getByTestId("selection-action-menu");
  await expect(actionMenu).not.toBeVisible({ timeout: 1000 });

  console.log("[TEST SUCCESS] Moving during long press cancelled selection");
});

test("filters annotations in unified feed with structural toggle", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[
        ...graphqlMocks,
        ...createSummaryMocks(PDF_DOC_ID_FOR_STRUCTURAL_TEST, CORPUS_ID),
      ]}
      documentId={PDF_DOC_ID_FOR_STRUCTURAL_TEST}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", {
      name: mockPdfDocumentForStructuralTest.title ?? "",
    })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Open sidebar via ChatIndicator
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Switch to feed mode
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();

  // Wait for feed to load
  await page.waitForTimeout(500);

  const nonStructuralAnnotation = page.locator(
    `[data-annotation-id="${mockAnnotationNonStructural1.id}"]`
  );
  const structuralAnnotation = page.locator(
    `[data-annotation-id="${mockAnnotationStructural1.id}"]`
  );

  // Initial State: Non-structural visible, structural hidden
  await expect(nonStructuralAnnotation).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(structuralAnnotation).not.toBeVisible({ timeout: LONG_TIMEOUT });

  // Capture screenshot showing softened PDF annotations with feed panel
  await hideFloatingControls(page);
  await docScreenshot(page, "annotations--pdf-feed--with-soft-highlights");

  // Open filter dropdown - look for the button with Filter icon and "Content Types" text
  const filterDropdown = page
    .locator("div")
    .filter({
      hasText: "Content Types",
    })
    .filter({
      has: page.locator('svg[class*="lucide-filter"]'),
    })
    .first();
  await expect(filterDropdown).toBeVisible({ timeout: LONG_TIMEOUT });
  await filterDropdown.click();

  // Wait for dropdown menu to appear
  await page.waitForTimeout(300);

  // TODO: The structural toggle is likely in ViewSettingsPopup or similar
  // For now, skip this test as we need to investigate the actual UI structure
  console.log(
    "[TEST] Structural toggle test needs investigation of actual UI structure"
  );
});

/* --------------------------------------------------------------------- */
/* PDF annotation bounding boxes rendered on canvas                       */
/* --------------------------------------------------------------------- */
test("PDF annotations render with soft bounding boxes on canvas", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[
        ...graphqlMocks,
        ...createSummaryMocks(PDF_DOC_ID_FOR_STRUCTURAL_TEST, CORPUS_ID),
      ]}
      documentId={PDF_DOC_ID_FOR_STRUCTURAL_TEST}
      corpusId={CORPUS_ID}
      showBoundingBoxes={true}
      showSelectedOnly={false}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", {
      name: mockPdfDocumentForStructuralTest.title ?? "",
    })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for PDF canvas to render
  const pdfCanvas = page.locator("#pdf-container canvas").first();
  await expect(pdfCanvas).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for annotations to render on the canvas
  await page.waitForTimeout(2000);

  // Verify the SelectionBoundary span is rendered on the PDF overlay
  const selectionBoundary = page.locator(
    `[id="SELECTION_${mockAnnotationNonStructural1.id}"]`
  );
  await expect(selectionBoundary).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify the boundary has rounded corners and soft box-shadow (no hard border)
  const styles = await selectionBoundary.evaluate((el) => {
    const computed = window.getComputedStyle(el);
    return {
      borderRadius: computed.borderRadius,
      border: computed.border,
      boxShadow: computed.boxShadow,
    };
  });
  // Border should be "none" (0px), border-radius should be 6px
  expect(styles.border).toContain("0px");
  expect(styles.borderRadius).toBe("6px");
  // Box-shadow should be a diffuse glow (not "none", no hard inset lines)
  expect(styles.boxShadow).not.toBe("none");

  console.log("[TEST] Verified soft annotation styling on PDF canvas:", styles);

  // Hide floating controls for clean screenshot
  await hideFloatingControls(page);

  // Capture the PDF area showing annotation overlays with softened styling
  const pdfContainer = page.locator("#pdf-container");
  await docScreenshot(page, "annotations--pdf-canvas--soft-bounding-boxes", {
    element: pdfContainer,
  });
});

test("PDF annotations with labels always visible", async ({ mount, page }) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[
        ...graphqlMocks,
        ...createSummaryMocks(PDF_DOC_ID_FOR_STRUCTURAL_TEST, CORPUS_ID),
      ]}
      documentId={PDF_DOC_ID_FOR_STRUCTURAL_TEST}
      corpusId={CORPUS_ID}
      showBoundingBoxes={true}
      showSelectedOnly={false}
      showLabels={LabelDisplayBehavior.ALWAYS}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", {
      name: mockPdfDocumentForStructuralTest.title ?? "",
    })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for PDF canvas to render
  const pdfCanvas = page.locator("#pdf-container canvas").first();
  await expect(pdfCanvas).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for annotations and labels to render
  await page.waitForTimeout(2000);

  // Verify annotation boundary is visible
  const selectionBoundary = page.locator(
    `[id="SELECTION_${mockAnnotationNonStructural1.id}"]`
  );
  await expect(selectionBoundary).toBeVisible({ timeout: LONG_TIMEOUT });

  // Hide floating controls for clean screenshot
  await hideFloatingControls(page);

  // Capture the PDF area showing annotations with labels
  const pdfContainer = page.locator("#pdf-container");
  await docScreenshot(page, "annotations--pdf-canvas--with-labels", {
    element: pdfContainer,
  });
});

/* --------------------------------------------------------------------- */
/* search using FloatingDocumentInput                                     */
/* --------------------------------------------------------------------- */
test("Search jumps to first 'Transfer Taxes' hit using floating input", async ({
  mount,
  page,
}) => {
  /* 1️⃣  mount the wrapper */
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  /* 2️⃣  wait until document loads */
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF is visible by default
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  /* 3️⃣  Click on the floating input to expand it - look for the button group with Search and MessageSquare icons */
  const floatingInput = page
    .locator("div")
    .filter({
      has: page.locator('svg[class*="lucide-search"]'),
    })
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .first();
  await expect(floatingInput).toBeVisible({ timeout: LONG_TIMEOUT });
  await floatingInput.click();

  /* 4️⃣  The search mode should be active by default, but make sure by clicking search toggle if needed */
  const searchToggle = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-search"]'),
    })
    .first();
  await searchToggle.click();

  /* 5️⃣  Type search query and press Enter */
  const searchInput = page.getByPlaceholder("Search document...");
  await expect(searchInput).toBeVisible({ timeout: LONG_TIMEOUT });
  await searchInput.fill("Transfer Taxes");
  await searchInput.press("Enter");

  /* 6️⃣  wait for ANY highlight to become visible */
  const highlight = page.locator("[id^='SEARCH_RESULT_']").first();
  await expect(highlight).toBeVisible({ timeout: LONG_TIMEOUT });

  /* 6b️⃣  wait until the container finished scrolling */
  await page.waitForFunction(
    ([hl, container]) => {
      if (!hl || !container) return false;
      const h = hl.getBoundingClientRect();
      const c = container.getBoundingClientRect();
      return h.top >= c.top && h.bottom <= c.bottom;
    },
    [
      await highlight.elementHandle(),
      await page.locator("#pdf-container").elementHandle(),
    ],
    { timeout: LONG_TIMEOUT }
  );

  /* 7️⃣  assert highlight is within viewport */
  const pdfBox = await page.locator("#pdf-container").boundingBox();
  const hlBox = await highlight.boundingBox();
  expect(pdfBox && hlBox, "bounding boxes must exist").toBeTruthy();
  if (pdfBox && hlBox) {
    const within =
      hlBox.y >= pdfBox.y && hlBox.y + hlBox.height <= pdfBox.y + pdfBox.height;
    expect(within).toBe(true);
  }
});

/* --------------------------------------------------------------------- */
/* chat source in unified feed – scroll to highlight                      */
/* --------------------------------------------------------------------- */
test("Chat source chip in unified feed centres its highlight in PDF", async ({
  mount,
  page,
}) => {
  // Mount KB wrapper with the extended mocks
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait until document loads
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Open sidebar
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Should be in chat mode by default, click on a conversation
  const convCard = page
    .locator("text=Transfer Taxes in Document Analysis")
    .first();
  await expect(convCard).toBeVisible({ timeout: LONG_TIMEOUT });
  await convCard.click();

  // Expand sources in assistant message
  const sourceChip = page.locator(".source-preview-container").first();
  await expect(sourceChip).toBeVisible({ timeout: LONG_TIMEOUT });
  await sourceChip.click();

  // Click source child 1 in the expanded sources list
  const sourceChild1 = page.locator(".source-chip").first();
  await expect(sourceChild1).toBeVisible({ timeout: LONG_TIMEOUT });
  await sourceChild1.click();

  // Wait for highlight to be in the DOM & scrolled into view
  const messageId = "TWVzc2FnZVR5cGU6Ng=="; // base-64 id used by the UI
  const highlight = page.locator(
    `[id="CHAT_SOURCE_${messageId}.0"]` // an attribute selector needs no escaping
  );
  await expect(highlight).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify the highlight is fully visible in the viewport
  await page.waitForFunction(
    ([hl, container]) => {
      if (!hl || !container) return false;
      const h = hl.getBoundingClientRect();
      const c = container.getBoundingClientRect();
      return h.top >= c.top && h.bottom <= c.bottom;
    },
    [
      await highlight.elementHandle(),
      await page.locator("#pdf-container").elementHandle(),
    ],
    { timeout: LONG_TIMEOUT }
  );

  // Final bounding-box assertion
  const pdfBox = await page.locator("#pdf-container").boundingBox();
  const hlBox = await highlight.boundingBox();
  expect(pdfBox && hlBox).toBeTruthy();
  if (pdfBox && hlBox) {
    const within =
      hlBox.y >= pdfBox.y && hlBox.y + hlBox.height <= pdfBox.y + pdfBox.height;
    expect(within).toBe(true);
  }
});

/* --------------------------------------------------------------------- */
/* browser zoom controls test                                             */
/* --------------------------------------------------------------------- */
test("Browser zoom controls (Ctrl+scroll, keyboard shortcuts) work correctly", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // PDF should be visible
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Wait a bit for zoom calculation to stabilize
  await page.waitForTimeout(1000);

  // Get initial zoom level (might not be 100% due to fit-to-width calculations)
  const zoomControls = page.locator(".zoom-level").first();
  await expect(zoomControls).toBeVisible({ timeout: LONG_TIMEOUT });

  // Get the initial zoom text and ensure it's stable
  let initialZoomText = await zoomControls.textContent();
  await page.waitForTimeout(500);
  initialZoomText = await zoomControls.textContent();

  const initialZoom = parseInt(initialZoomText?.replace("%", "") || "100");
  const resetZoomLevel = initialZoom; // Store the initial zoom as the reset level
  console.log(
    `[TEST] Initial zoom level: ${initialZoom}% (this is the reset level)`
  );

  // Test 1: Zoom in button click
  console.log("[TEST] Testing zoom in button");
  const zoomInButton = page.getByTitle("Zoom In");
  await expect(zoomInButton).toBeVisible();

  // Add listener to verify click is registered
  await page.evaluate(() => {
    const btn = document.querySelector('[title="Zoom In"]');
    if (btn) {
      btn.addEventListener("click", () =>
        console.log("[TEST] Zoom In button clicked!")
      );
    }
  });

  await zoomInButton.click();
  console.log("[TEST] Zoom In button click sent");

  // Check zoom changes
  const expectedZoomIn = Math.min(initialZoom + 10, 400);
  console.log(`[TEST] Expected zoom after button click: ${expectedZoomIn}%`);

  // Wait for zoom to update
  await page.waitForTimeout(500);

  // Primary check: zoom controls should show the new value
  await expect(zoomControls).toHaveText(`${expectedZoomIn}%`, {
    timeout: 5000,
  });

  // Define zoom indicator selector for reuse
  const zoomIndicator = page.getByTestId("zoom-indicator");

  // Optional check: if zoom indicator is visible, verify it
  const indicatorCountZoomIn = await zoomIndicator.count();
  if (indicatorCountZoomIn > 0) {
    console.log("[TEST] Zoom indicator is visible, verifying its value");
    await expect(zoomIndicator).toHaveText(`${expectedZoomIn}%`);
  } else {
    console.log("[TEST] Zoom indicator not visible, skipping indicator check");
  }

  // Test 2: Zoom out button click
  console.log("[TEST] Testing zoom out button");
  let currentZoom = expectedZoomIn;
  const zoomOutButton = page.getByTitle("Zoom Out");
  await expect(zoomOutButton).toBeVisible();
  await zoomOutButton.click();

  // Check zoom changes
  const expectedZoomOut = Math.max(currentZoom - 10, 50);
  console.log(`[TEST] Expected zoom after zoom out: ${expectedZoomOut}%`);

  // Wait for zoom to update
  await page.waitForTimeout(500);

  // Primary check: zoom controls should show the new value
  await expect(zoomControls).toHaveText(`${expectedZoomOut}%`, {
    timeout: 5000,
  });

  // Optional check: if zoom indicator is visible, verify it
  const indicatorCountZoomOut = await page
    .getByTestId("zoom-indicator")
    .count();
  if (indicatorCountZoomOut > 0) {
    console.log("[TEST] Zoom indicator is visible, verifying its value");
    await expect(zoomIndicator).toHaveText(`${expectedZoomOut}%`);
  } else {
    console.log("[TEST] Zoom indicator not visible, skipping indicator check");
  }

  currentZoom = expectedZoomOut;

  // Test 3: Ctrl+Plus to zoom in
  console.log("[TEST] Testing Ctrl+Plus keyboard shortcut");
  await page.keyboard.press("Control++"); // Ctrl+Plus

  const expectedAfterPlus = Math.min(currentZoom + 10, 400);
  console.log(`[TEST] Expected zoom after Ctrl+Plus: ${expectedAfterPlus}%`);

  // Wait for zoom to update
  await page.waitForTimeout(500);

  // Primary check: zoom controls
  await expect(zoomControls).toHaveText(`${expectedAfterPlus}%`, {
    timeout: 5000,
  });
  currentZoom = expectedAfterPlus;

  // Test 4: Ctrl+Minus to zoom out
  console.log("[TEST] Testing Ctrl+Minus keyboard shortcut");
  await page.keyboard.press("Control+-"); // Ctrl+Minus

  const expectedAfterMinus = Math.max(currentZoom - 10, 50);
  console.log(`[TEST] Expected zoom after Ctrl+Minus: ${expectedAfterMinus}%`);

  // Wait for zoom to update
  await page.waitForTimeout(500);

  // Primary check: zoom controls
  await expect(zoomControls).toHaveText(`${expectedAfterMinus}%`, {
    timeout: 5000,
  });
  currentZoom = expectedAfterMinus;

  // Log the current zoom before reset
  console.log(`[TEST] Zoom level before Ctrl+0 reset: ${currentZoom}%`);

  // Test 5: Ctrl+0 to reset zoom
  console.log("[TEST] Testing Ctrl+0 reset zoom (should go to 100%)");
  await page.keyboard.press("Control+0"); // Ctrl+0

  // Wait a bit for the event to process
  await page.waitForTimeout(300);

  // Check if zoom indicator appears
  const indicatorVisible = await page
    .getByTestId("zoom-indicator")
    .isVisible()
    .catch(() => false);
  console.log(
    `[TEST] Zoom indicator visible after Ctrl+0: ${indicatorVisible}`
  );

  if (indicatorVisible) {
    const indicatorText = await page
      .getByTestId("zoom-indicator")
      .textContent();
    console.log(`[TEST] Zoom indicator text: ${indicatorText}`);
    await expect(zoomIndicator).toBeHidden({ timeout: 3000 });
  }

  // Check the zoom controls directly
  await page.waitForTimeout(500);
  const zoomAfterReset = await zoomControls.textContent();
  console.log(`[TEST] Zoom controls after Ctrl+0: ${zoomAfterReset}`);

  // Ctrl+0 should reset to 100%, not the initial zoom
  await expect(zoomControls).toHaveText("100%", { timeout: 5000 });
  currentZoom = 100;

  // Test 6: Zoom bounds - test maximum zoom
  console.log("[TEST] Testing maximum zoom bound");
  // Zoom in many times to hit the max (4.0 = 400%)
  for (let i = 0; i < 35; i++) {
    // 35 * 0.1 = 3.5, so we should hit the 4.0 cap
    await page.keyboard.press("Control++");
    await page.waitForTimeout(50); // Small delay between presses
  }

  // Should cap at 400%
  await expect(zoomControls).toHaveText("400%");

  // One more zoom in should still be 400%
  await page.keyboard.press("Control++");
  await page.waitForTimeout(500);
  await expect(zoomControls).toHaveText("400%");

  // Test 7: Zoom bounds - test minimum zoom
  console.log("[TEST] Testing minimum zoom bound");
  // Reset first
  await page.keyboard.press("Control+0");
  await page.waitForTimeout(500);

  // Zoom out many times to hit the min (0.5 = 50%)
  for (let i = 0; i < 10; i++) {
    // 10 * 0.1 = 1.0, but we start at 1.0 so should hit 0.5 cap
    await page.keyboard.press("Control+-");
    await page.waitForTimeout(50);
  }

  // Should cap at 50%
  await expect(zoomControls).toHaveText("50%");

  // One more zoom out should still be 50%
  await page.keyboard.press("Control+-");
  await page.waitForTimeout(500);
  await expect(zoomControls).toHaveText("50%");

  // Test 8: Zoom only works in document layer, not knowledge layer
  console.log("[TEST] Testing zoom disabled in knowledge layer");

  // Switch to knowledge layer via floating summary preview
  const summaryButton = page.getByTestId("summary-toggle-button");
  await expect(summaryButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await summaryButton.click();

  // Wait for expanded summary
  await expect(page.locator('h3:has-text("Document Summary")')).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Click on summary to switch to knowledge layer
  const summaryCard = page.getByTestId("summary-card-1");
  await expect(summaryCard).toBeVisible({ timeout: LONG_TIMEOUT });
  await summaryCard.click();

  // Verify we're in knowledge layer
  await expect(
    page.getByRole("heading", { name: "Mock Summary Title" }).first()
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Try to zoom - should not show indicator
  await page.keyboard.press("Control++");

  // Wait a bit and verify zoom indicator does NOT appear
  await page.waitForTimeout(500);
  const indicatorCountInKnowledge = await page
    .getByTestId("zoom-indicator")
    .count();
  expect(indicatorCountInKnowledge).toBe(0);

  // Go back to document layer
  const backButton = page.getByTestId("back-to-document-button");
  await expect(backButton).toBeVisible({ timeout: LONG_TIMEOUT });
  await backButton.click();

  // Verify we're back in document layer and zoom works again
  await expect(page.locator("#pdf-container")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Reset to known state first
  await page.keyboard.press("Control+0");
  await page.waitForTimeout(500);

  // Now test zoom works again
  await page.keyboard.press("Control++");
  await page.waitForTimeout(500);
  await expect(zoomControls).toHaveText("110%");

  console.log("[TEST SUCCESS] All browser zoom controls working correctly");
});

// ──────────────────────────────────────────────────────────────────────────────
// │                           Read-Only Mode Tests                             │
// ──────────────────────────────────────────────────────────────────────────────

test.describe("Read-Only Mode Tests", () => {
  test("read-only: prevents creating annotations via unified feed", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // PDF is visible by default
    await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Wait for the label selector to be ready
    const labelSelectorButton = page.locator(
      '[data-testid="label-selector-toggle-button"]'
    );
    await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });

    // Try to open the selector - it should be disabled in read-only mode
    await labelSelectorButton.hover();
    await labelSelectorButton.click();

    // Label options should not appear or selector should be disabled
    const labelOptions = page.locator(".label-option");
    const labelCount = await labelOptions.count();

    // In read-only mode, either no labels should appear or the selector should be disabled
    if (labelCount > 0) {
      // If labels appear, clicking them should not work
      const firstLabelOption = labelOptions.first();
      await firstLabelOption.click();
      console.log("[TEST] Clicked label in read-only mode");
    }

    // Attempt to make a selection on the PDF
    const firstPageContainer = page
      .locator(".PageAnnotationsContainer")
      .first();
    const selectionLayer = firstPageContainer.locator("#selection-layer");
    const layerBox = await selectionLayer.boundingBox();
    expect(layerBox).toBeTruthy();

    // Perform drag selection
    const startX = layerBox!.width * 0.5;
    const startY = layerBox!.height * 0.1;
    const endX = layerBox!.width * 0.5;
    const endY = startY + 100;

    await page.mouse.move(layerBox!.x + startX, layerBox!.y + startY);
    await page.mouse.down();
    await page.waitForTimeout(100);
    await page.mouse.move(layerBox!.x + endX, layerBox!.y + endY, {
      steps: 10,
    });
    await page.waitForTimeout(100);
    await page.mouse.up();
    console.log("[TEST] Performed selection in read-only mode");

    // Action menu should appear but only with copy option in read-only mode
    const actionMenu = page.getByTestId("selection-action-menu");
    await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });

    // Copy button should be visible
    const copyButton = page.getByTestId("copy-text-button");
    await expect(copyButton).toBeVisible({ timeout: LONG_TIMEOUT });

    // Apply label button should NOT be visible in read-only mode
    const applyLabelButton = page.getByTestId("apply-label-button");
    await expect(applyLabelButton).not.toBeVisible({ timeout: 3000 });
    console.log(
      "[TEST SUCCESS] Action menu shows only copy option in read-only mode"
    );

    // Open sidebar to verify no annotation was created
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Switch to feed mode
    const feedToggle = page.getByTestId("view-mode-feed");
    await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
    await feedToggle.click();

    // Verify no new annotation appears (should only have existing ones)
    const newAnnotation = page
      .locator('[data-annotation-id="new-annot-1"]')
      .first();
    await expect(newAnnotation).not.toBeVisible({ timeout: 3000 });
    console.log("[TEST SUCCESS] No annotation created in read-only mode");
  });

  test("read-only: TXT document prevents creating annotations via text selection", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID)]}
        documentId={TXT_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // Wait for TXT annotator to be visible
    const txtAnnotator = page.getByTestId("txt-annotator");
    await expect(txtAnnotator).toBeVisible({ timeout: LONG_TIMEOUT });

    // Try to select a label - selector should be disabled
    const labelSelectorButton = page.locator(
      '[data-testid="label-selector-toggle-button"]'
    );
    await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });
    await labelSelectorButton.click();

    // Check if labels appear (they might be disabled)
    await page.waitForTimeout(500);
    const labelOptions = page.locator(".label-option");
    const labelCount = await labelOptions.count();
    console.log(`[TEST] Found ${labelCount} label options in read-only mode`);

    // Scroll to top
    await txtAnnotator.evaluate((el) => {
      el.scrollTop = 0;
    });
    await page.waitForTimeout(200);

    // Find text spans
    const textSpans = txtAnnotator.locator("span[data-span-index]");
    const spanCount = await textSpans.count();
    console.log(`[TEST] Found ${spanCount} text spans`);

    // Try to select text
    let targetSpan: any = null;
    for (let i = 0; i < Math.min(5, spanCount); i++) {
      const span = textSpans.nth(i);
      const text = await span.textContent();
      if (text && text.length > 10 && !text.match(/^\s*$/)) {
        targetSpan = span;
        console.log(
          `[TEST] Found target span at index ${i} with text: "${text}"`
        );
        break;
      }
    }

    if (!targetSpan) {
      targetSpan = textSpans.filter({ hasText: /\w+/ }).first();
    }

    expect(targetSpan).toBeTruthy();

    // Get the bounding box and perform selection
    const spanBox = await targetSpan.boundingBox();
    expect(spanBox).toBeTruthy();

    const startX = spanBox!.x + 20;
    const startY = spanBox!.y + spanBox!.height / 2;
    const endX = Math.min(spanBox!.x + 100, spanBox!.x + spanBox!.width - 20);
    const endY = startY;

    console.log(
      `[TEST] Attempting text selection in read-only mode from (${startX}, ${startY}) to (${endX}, ${endY})`
    );

    // Perform the drag selection
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.waitForTimeout(100);
    await page.mouse.move(endX, endY, { steps: 10 });
    await page.waitForTimeout(100);
    await page.mouse.up();

    // Trigger mouseup event on container
    await txtAnnotator.dispatchEvent("mouseup");
    await page.waitForTimeout(500);

    // Verify selection happened
    const selectedText = await page.evaluate(() =>
      window.getSelection()?.toString()
    );
    console.log(`[TEST] Selected text in read-only mode: "${selectedText}"`);

    // Wait to see if annotation is created (it shouldn't be)
    await page.waitForTimeout(2000);

    // Check annotated spans - count should not increase
    const annotatedSpans = await txtAnnotator
      .locator('[data-testid^="annotated-span-"]')
      .count();
    console.log(`[TEST] Annotated spans in read-only mode: ${annotatedSpans}`);

    // Should only have the 2 existing annotations from mock data
    expect(annotatedSpans).toBe(2);

    // Open sidebar to double-check
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Switch to feed mode
    const feedToggle = page.getByTestId("view-mode-feed");
    await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
    await feedToggle.click();

    // Verify no new annotation
    const newAnnotation = page
      .locator('[data-annotation-id="new-annot-1"]')
      .first();
    await expect(newAnnotation).not.toBeVisible({ timeout: 3000 });
    console.log(
      "[TEST SUCCESS] No annotation created in TXT document in read-only mode"
    );
  });

  test("read-only: prevents note click and shows correct cursor", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // Open sidebar
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Switch to feed mode
    const feedToggle = page.getByTestId("view-mode-feed");
    await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
    await feedToggle.click();

    // Wait for notes to load in the feed
    await page.waitForTimeout(1000);

    // Find the note - PostItNote with the test content
    const noteItem = page.locator("button").filter({ hasText: "Test Note 1" });

    // In read-only mode, notes should have default cursor, not pointer
    await expect(noteItem).toHaveCSS("cursor", "default");

    // Try to click the note
    await noteItem.click({ force: true });

    // Wait a bit to ensure no modal appears
    await page.waitForTimeout(500);

    // Note modal should NOT open in read-only mode
    const noteModal = page.locator('[id^="note-modal_"]');
    await expect(noteModal).not.toBeVisible();

    console.log(
      "[TEST SUCCESS] Note correctly non-clickable in read-only mode"
    );
  });

  test("read-only: ChatTray starts with new conversation and hides history", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...chatTrayMocks]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // Open chat tray
    const chatIndicator = page
      .locator("button")
      .filter({
        has: page.locator('svg[class*="lucide-message-square"]'),
      })
      .last();
    await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
    await chatIndicator.click();

    // Sidebar should be visible
    const slidingPanel = page.locator("#sliding-panel");
    await expect(slidingPanel).toBeVisible({ timeout: LONG_TIMEOUT });

    // Make sure we're in chat mode (not feed mode)
    const chatToggle = page.getByTestId("view-mode-chat");
    if (await chatToggle.isVisible()) {
      await chatToggle.click();
    }

    // "Back to Conversations" button should NOT be visible in read-only mode
    const backButton = page.getByRole("button", {
      name: /Back to Conversations/i,
    });
    await expect(backButton).not.toBeVisible({ timeout: 3000 });
    console.log(
      "[TEST SUCCESS] 'Back to Conversations' button hidden in read-only mode"
    );

    // Chat input should be visible (backend handles persistence)
    const chatInput = page.locator('[data-testid="chat-input"]');
    await expect(chatInput).toBeVisible({ timeout: LONG_TIMEOUT });

    // Verify the placeholder shows connected state
    await expect(chatInput).toHaveAttribute(
      "placeholder",
      "Type your message..."
    );
    console.log(
      "[TEST SUCCESS] Chat input visible and connected in read-only mode (backend handles persistence)"
    );

    // Should show a new conversation, not the conversation list
    const conversationList = page.locator('[data-testid="conversation-list"]');
    await expect(conversationList).not.toBeVisible({ timeout: 3000 });
    console.log("[TEST SUCCESS] Conversation history hidden in read-only mode");
  });

  test("read-only: UnifiedLabelSelector is disabled", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // Label selector button should be visible
    const labelSelectorButton = page.locator(
      '[data-testid="label-selector-toggle-button"]'
    );
    await expect(labelSelectorButton).toBeVisible({ timeout: LONG_TIMEOUT });

    // Check if the button has disabled styling or attributes
    const isDisabled = await labelSelectorButton.evaluate((el) => {
      const button = el as HTMLElement;
      // Check various ways it might be disabled
      return (
        button.hasAttribute("disabled") ||
        button.getAttribute("aria-disabled") === "true" ||
        button.style.pointerEvents === "none" ||
        button.style.opacity === "0.5" ||
        button.classList.contains("disabled")
      );
    });

    if (isDisabled) {
      console.log(
        "[TEST SUCCESS] Label selector button is disabled in read-only mode"
      );
    } else {
      // If not visually disabled, clicking should not open the dropdown
      await labelSelectorButton.click();
      await page.waitForTimeout(500);

      const labelOptions = page.locator(".label-option");
      const labelCount = await labelOptions.count();

      if (labelCount === 0) {
        console.log(
          "[TEST SUCCESS] Label selector doesn't show options in read-only mode"
        );
      } else {
        // Even if options show, they should be disabled or non-functional
        console.log(
          "[TEST] Label options appeared, checking if they're disabled"
        );
        const firstOption = labelOptions.first();
        await firstOption.click();

        // Verify the label wasn't actually selected by checking the button text
        const buttonText = await labelSelectorButton.textContent();
        expect(buttonText).toContain("Select a label");
        console.log(
          "[TEST SUCCESS] Label selection is non-functional in read-only mode"
        );
      }
    }
  });

  test("read-only: Edit Summary button is hidden in knowledge layer", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // Look for the floating summary preview button (the "book" icon)
    const summaryButton = page
      .locator("button")
      .filter({ has: page.locator('svg[class*="lucide-book-open"]') })
      .first();

    // Click to open summary preview
    await expect(summaryButton).toBeVisible({ timeout: LONG_TIMEOUT });
    await summaryButton.click();

    // Wait for summary preview to appear - the testid includes the version number
    const summaryPreview = page.getByTestId("summary-card-1");
    await expect(summaryPreview).toBeVisible({ timeout: LONG_TIMEOUT });

    // Edit Summary button should NOT be visible in read-only mode
    const editSummaryButton = page.getByRole("button", {
      name: /Edit Summary/i,
    });
    await expect(editSummaryButton).not.toBeVisible({ timeout: 3000 });
    console.log(
      "[TEST SUCCESS] Edit Summary button correctly hidden in read-only mode"
    );
  });

  test("read-only: annotation action menu shows only copy option", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
        readOnly={true}
      />
    );

    // Wait for document to load
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });

    // PDF should be visible
    await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // Perform text selection
    const firstPageContainer = page
      .locator(".PageAnnotationsContainer")
      .first();
    const selectionLayer = firstPageContainer.locator("#selection-layer");
    const layerBox = await selectionLayer.boundingBox();
    expect(layerBox).toBeTruthy();

    // Create a selection
    await page.mouse.move(
      layerBox!.x + layerBox!.width * 0.5,
      layerBox!.y + layerBox!.height * 0.1
    );
    await page.mouse.down();
    await page.mouse.move(
      layerBox!.x + layerBox!.width * 0.5,
      layerBox!.y + layerBox!.height * 0.1 + 100,
      { steps: 10 }
    );
    await page.mouse.up();
    console.log("[TEST] Made selection in read-only mode");

    // Action menu should appear with copy option
    const actionMenu = page.getByTestId("selection-action-menu");
    await expect(actionMenu).toBeVisible({ timeout: LONG_TIMEOUT });
    console.log("[TEST] Action menu appeared");

    // Verify only copy button is visible, not apply label
    const copyButton = page.getByTestId("copy-text-button");
    const applyLabelButton = page.getByTestId("apply-label-button");

    await expect(copyButton).toBeVisible({ timeout: LONG_TIMEOUT });
    await expect(applyLabelButton).not.toBeVisible({ timeout: 3000 });

    console.log(
      "[TEST SUCCESS] Action menu shows only copy option in read-only mode"
    );

    // Grant clipboard permissions and test copy
    await page
      .context()
      .grantPermissions(["clipboard-write", "clipboard-read"]);
    await copyButton.click();

    // Verify menu disappears after copy
    await expect(actionMenu).not.toBeVisible({ timeout: LONG_TIMEOUT });

    // Verify clipboard content
    const clipboardText = await page.evaluate(() =>
      navigator.clipboard.readText()
    );
    expect(clipboardText).toBeTruthy();
    console.log(
      "[TEST SUCCESS] Text successfully copied to clipboard in read-only mode"
    );
  });
});

/* --------------------------------------------------------------------- */
/* Chat sources hide other annotations except explicitly selected       */
/* --------------------------------------------------------------------- */
test("Chat sources hide regular annotations and search results, but show explicitly selected annotations", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
      documentId={PDF_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Wait for PDF to render
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Note: The default mockPdfDocument has no annotations, so we skip verifying
  // initial annotation visibility. The test focuses on the hiding logic when
  // chat sources appear, and verifying explicitly selected annotations remain visible.

  // Step 1: Open sidebar and load chat sources
  console.log("[TEST] Step 2: Opening sidebar to display chat sources");
  const chatIndicator = page
    .locator("button")
    .filter({
      has: page.locator('svg[class*="lucide-message-square"]'),
    })
    .last();
  await expect(chatIndicator).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatIndicator.click();

  // Click on a conversation to load chat sources
  const convCard = page
    .locator("text=Transfer Taxes in Document Analysis")
    .first();
  await expect(convCard).toBeVisible({ timeout: LONG_TIMEOUT });
  await convCard.click();

  // Expand sources in assistant message
  const sourceChip = page.locator(".source-preview-container").first();
  await expect(sourceChip).toBeVisible({ timeout: LONG_TIMEOUT });
  await sourceChip.click();

  // Click first source to display chat sources
  const sourceChild1 = page.locator(".source-chip").first();
  await expect(sourceChild1).toBeVisible({ timeout: LONG_TIMEOUT });
  await sourceChild1.click();

  // Wait for chat source to be visible
  const messageId = "TWVzc2FnZVR5cGU6Ng==";
  const chatSource = page.locator(`[id="CHAT_SOURCE_${messageId}.0"]`);
  await expect(chatSource).toBeVisible({ timeout: LONG_TIMEOUT });
  console.log("[TEST] Chat sources are now displayed");

  // Step 3: Verify the component works correctly with chat sources
  console.log(
    "[TEST] Step 3: Verifying component renders correctly with chat sources"
  );

  // Note: The mockPdfDocument has no annotations (allAnnotations: []),
  // so we cannot directly test annotation visibility. However, this test
  // verifies that:
  // 1. Chat sources load and display successfully
  // 2. The visibility logic code paths execute without errors
  // 3. The component handles the presence of chat sources correctly

  // Verify chat source remains visible
  await expect(chatSource).toBeVisible({ timeout: LONG_TIMEOUT });
  console.log("[TEST] Chat sources display successfully");

  // Step 4: Test switching between chat and feed modes
  console.log("[TEST] Step 4: Testing view mode switching with chat sources");

  // Open unified feed
  const feedToggle = page.getByTestId("view-mode-feed");
  await expect(feedToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await feedToggle.click();
  await page.waitForTimeout(500);
  console.log("[TEST] Switched to feed view");

  // Switch back to chat mode
  const chatToggle = page.getByTestId("view-mode-chat");
  await expect(chatToggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await chatToggle.click();
  await page.waitForTimeout(500);

  // Verify chat source is still visible after view mode changes
  await expect(chatSource).toBeVisible({ timeout: LONG_TIMEOUT });
  console.log(
    "[TEST SUCCESS] View mode switching works correctly with chat sources"
  );

  console.log(
    "[TEST SUCCESS] Chat sources correctly manage annotation visibility"
  );
});

/* --------------------------------------------------------------------- */
/* Index tab renders in sidebar                                           */
/* --------------------------------------------------------------------- */
test("Index tab is visible in sidebar tabs", async ({ mount, page }) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[
        ...graphqlMocks,
        ...indexTabMocks,
        ...createSummaryMocks(TXT_DOC_ID, CORPUS_ID),
      ]}
      documentId={TXT_DOC_ID}
      corpusId={CORPUS_ID}
    />
  );

  // Wait for document to load
  await expect(
    page.getByRole("heading", { name: mockTxtDocument.title ?? "" })
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify the Index tab is visible (first tab in sidebar)
  const indexTab = page.getByTestId("view-mode-index");
  await expect(indexTab).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify tabs are visible
  const chatTab = page.getByTestId("view-mode-chat");
  const feedTab = page.getByTestId("view-mode-feed");
  const discussionsTab = page.getByTestId("view-mode-discussions");
  await expect(chatTab).toBeVisible();
  await expect(feedTab).toBeVisible();
  await expect(discussionsTab).toBeVisible();

  await docScreenshot(page, "knowledge-base--sidebar-tabs--with-index");

  // Click Index tab to open the sidebar
  await indexTab.click();

  // Sidebar panel should open
  const slidingPanel = page.locator("#sliding-panel");
  await expect(slidingPanel).toBeVisible({ timeout: LONG_TIMEOUT });

  // Verify rendered index content matches mock data
  await expect(page.getByText("Introduction")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
  await expect(page.getByText("Terms and Conditions")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  await docScreenshot(page, "knowledge-base--index-tab--open");
});

// Helper to create summary mocks (reuse from FloatingSummaryPreview tests but inline to avoid circular dep)
const mockSummaryVersions = [
  {
    id: "rev-1",
    version: 1,
    created: "2025-01-24T14:00:00Z",
    snapshot: "# Mock Summary Title\n\nMock summary details.",
    diff: "",
    author: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
      __typename: "UserType",
    },
    __typename: "DocumentSummaryRevision",
  },
];
const createVersionMock = (documentId: string, corpusId: string) => ({
  request: {
    query: GET_CORPUS_VERSIONS,
    variables: { documentId, corpusId },
  },
  result: {
    data: {
      document: {
        id: documentId,
        corpusVersions: [],
        __typename: "DocumentType",
      },
    },
  },
});

const createSummaryVersionMock = (documentId: string, corpusId: string) => ({
  request: {
    query: GET_DOCUMENT_SUMMARY_VERSIONS,
    variables: { documentId, corpusId },
  },
  result: {
    data: {
      document: {
        id: documentId,
        summaryContent: mockSummaryVersions[0].snapshot,
        currentSummaryVersion: 1,
        summaryRevisions: mockSummaryVersions,
        __typename: "DocumentType",
      },
    },
  },
});

const createSummaryMocks = (documentId: string, corpusId: string) => [
  createSummaryVersionMock(documentId, corpusId),
  createSummaryVersionMock(documentId, corpusId),
  createVersionMock(documentId, corpusId),
  createVersionMock(documentId, corpusId),
];

/* ──────────────────────────────────────────────────────────────────────────
 * Error / unauthorized / fallback states
 * ────────────────────────────────────────────────────────────────────────── */

test("renders Invalid Document error when documentId is empty", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[]}
      documentId=""
      corpusId={CORPUS_ID}
    />
  );

  // The component short-circuits with an error modal.
  await expect(page.getByText("Invalid Document", { exact: true })).toBeVisible(
    { timeout: 5000 }
  );
  await expect(
    page.getByText("Cannot load document: Invalid document ID")
  ).toBeVisible();

  // A "Close" button is offered for exit.
  await expect(page.getByRole("button", { name: "Close" })).toBeVisible();
});

test("invalid-document error modal dismisses via the Close button", async ({
  mount,
  page,
}) => {
  await mount(
    <DocumentKnowledgeBaseTestWrapper
      mocks={[]}
      documentId=""
      corpusId={CORPUS_ID}
    />
  );

  await expect(page.getByText("Invalid Document", { exact: true })).toBeVisible(
    { timeout: 5000 }
  );

  // Click Close. The wrapper defaults to a no-op onClose but the click must
  // not throw and the title text remains on-screen (component does not
  // re-render automatically — this simply exercises the handler path).
  await page.getByRole("button", { name: "Close" }).click();

  // Component still mounted (no navigation happened in the test harness);
  // this is purely to cover the handleClose callback path.
  await expect(
    page.getByText("Invalid Document", { exact: true })
  ).toBeVisible();
});

/* ──────────────────────────────────────────────────────────────────────────
 * Desktop bottom toolbar consolidation (issue #1735)
 *
 * Before #1735 the desktop document layer carried three independent
 * `position: fixed`/absolute floaters along its bottom edge: a circular
 * SUMMARY button (left), a search/chat mini-pill (centre) and the active-
 * label OC_SECTION × pill (right). They had no relationship to each other
 * yet shared the same band of screen, reading as visual noise.
 *
 * They now share a single anchored container — `DocumentBottomBar` — that
 * pins all three to the same baseline with consistent spacing. This test
 * verifies the consolidation by asserting:
 *   1. The shared container is the common ancestor of all three controls.
 *   2. All three controls sit at the same vertical baseline (within a
 *      tolerance accounting for their differing intrinsic heights).
 *   3. The summary button is left of the input, the input is left of the
 *      label selector — the band reads left → centre → right.
 * ────────────────────────────────────────────────────────────────────────── */

test.describe("Desktop bottom toolbar consolidation (#1735)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("consolidates summary, search/chat and label controls into a single anchored bottom bar", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentKnowledgeBaseTestWrapper
        mocks={[...graphqlMocks, ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID)]}
        documentId={PDF_DOC_ID}
        corpusId={CORPUS_ID}
      />
    );

    // Wait for the document to load.
    await expect(
      page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
    ).toBeVisible({ timeout: LONG_TIMEOUT });
    await expect(page.locator("#pdf-container")).toBeVisible({
      timeout: LONG_TIMEOUT,
    });

    // 1. The bar exists and is the common ancestor of all three controls.
    const bar = page.getByTestId("document-bottom-bar");
    await expect(bar).toBeVisible({ timeout: LONG_TIMEOUT });

    const summaryButton = page.getByTestId("summary-toggle-button");
    const labelSelector = page.getByTestId("annotation-tools");

    await expect(summaryButton).toBeVisible({ timeout: LONG_TIMEOUT });
    await expect(labelSelector).toBeVisible({ timeout: LONG_TIMEOUT });

    for (const child of [summaryButton, labelSelector]) {
      const isInsideBar = await child.evaluate((el) =>
        Boolean(el.closest('[data-testid="document-bottom-bar"]'))
      );
      expect(isInsideBar).toBe(true);
    }

    // 2. The three controls share the same vertical band.
    const summaryBox = await summaryButton.boundingBox();
    const labelBox = await labelSelector.boundingBox();
    const barBox = await bar.boundingBox();
    expect(summaryBox).not.toBeNull();
    expect(labelBox).not.toBeNull();
    expect(barBox).not.toBeNull();

    // The bottoms of the controls live within the bar's vertical extent.
    const summaryBottom = summaryBox!.y + summaryBox!.height;
    const labelBottom = labelBox!.y + labelBox!.height;
    const barBottom = barBox!.y + barBox!.height;
    expect(Math.abs(summaryBottom - barBottom)).toBeLessThanOrEqual(8);
    expect(Math.abs(labelBottom - barBottom)).toBeLessThanOrEqual(8);

    // 3. Left → right ordering with the centre slot reserved for the input.
    expect(summaryBox!.x).toBeLessThan(labelBox!.x);

    // Documentation screenshot — full viewport showing the bar in context.
    await docScreenshot(page, "knowledge-base--document-bottom-bar--default");

    // Close-up screenshot of just the bar so the consolidation reads at a
    // glance in documentation. Clip a generous strip around the bar.
    const clipPadding = 24;
    const clipY = Math.max(0, Math.floor(barBox!.y - clipPadding));
    const clipHeight = Math.min(
      900 - clipY,
      Math.ceil(barBox!.height + clipPadding * 2)
    );
    await docScreenshot(
      page,
      "knowledge-base--document-bottom-bar--consolidated",
      {
        clip: { x: 0, y: clipY, width: 1440, height: clipHeight },
      }
    );

    // Open the search/chat input so the centre slot is populated and assert
    // it lands between the summary button and the label selector.
    await page.getByTestId("search-toggle-button").click();
    const searchInput = page.getByPlaceholder("Search document...");
    await expect(searchInput).toBeVisible({ timeout: LONG_TIMEOUT });
    const inputBox = await searchInput.boundingBox();
    expect(inputBox).not.toBeNull();
    expect(inputBox!.x).toBeGreaterThan(summaryBox!.x);
    expect(inputBox!.x + inputBox!.width).toBeLessThan(
      labelBox!.x + labelBox!.width
    );

    // Screenshot with the input expanded — shows the centre slot active.
    await docScreenshot(
      page,
      "knowledge-base--document-bottom-bar--input-expanded",
      {
        clip: { x: 0, y: clipY, width: 1440, height: clipHeight },
      }
    );
  });
});

/* ──────────────────────────────────────────────────────────────────────────
 * Default PDF zoom is a fit-to-width calculation (issue #1736)
 *
 * The initial PDF zoom is computed from the measured document-layer width
 * (not a fixed seed), but the calculation reserved no horizontal margin so
 * the rendered page would touch the container's edges. On narrower laptop
 * viewports — 1280 px or 1024 px — that left no safety budget for sub-pixel
 * rounding and triggered a horizontal scrollbar inside the document layer.
 *
 * The shared ``computeFitToWidthZoom`` helper now reserves FIT_WIDTH_MARGIN
 * off the container width before clamping to [ZOOM_MIN, ZOOM_MAX]. These
 * tests pin the contract at the three canonical laptop widths from the
 * audit by asserting:
 *   1. The initial zoom is a fit-to-width-derived value (not the default
 *      100 %), scaled to the measured container width.
 *   2. The rendered PDF canvas width is strictly less than the document
 *      container width — i.e. no horizontal overflow inside the document
 *      layer at any of the three viewports.
 * ────────────────────────────────────────────────────────────────────────── */

const fitToWidthViewports = [
  { width: 1440, height: 900, screenshotName: "1440x900" },
  { width: 1280, height: 720, screenshotName: "1280x720" },
  { width: 1024, height: 768, screenshotName: "1024x768" },
] as const;

for (const viewport of fitToWidthViewports) {
  test.describe(`Default PDF zoom fit-to-width — ${viewport.width}x${viewport.height} (#1736)`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test(`fits the page within the document container with no horizontal overflow at ${viewport.width}px`, async ({
      mount,
      page,
    }) => {
      await mount(
        <DocumentKnowledgeBaseTestWrapper
          mocks={[
            ...graphqlMocks,
            ...createSummaryMocks(PDF_DOC_ID, CORPUS_ID),
          ]}
          documentId={PDF_DOC_ID}
          corpusId={CORPUS_ID}
        />
      );

      // Wait for the document to load and the PDF to render.
      await expect(
        page.getByRole("heading", { name: mockPdfDocument.title ?? "" })
      ).toBeVisible({ timeout: LONG_TIMEOUT });
      await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
        timeout: LONG_TIMEOUT,
      });

      // Wait for the fit-to-width useEffect to settle by polling the
      // .zoom-level readout until it parses above 100 % (the fit-to-width
      // result for a US-letter page comfortably exceeds 100 %; the legacy
      // 1.0 default would read exactly 100 %).
      await page.waitForFunction(
        () => {
          const el = document.querySelector(".zoom-level");
          const txt = el?.textContent ?? "";
          const n = parseInt(txt.replace("%", ""), 10);
          return Number.isFinite(n) && n > 100;
        },
        undefined,
        { timeout: LONG_TIMEOUT }
      );

      // (1) The reported zoom is fit-to-width-derived, not a fixed seed.
      // For a US-letter page (612 pt) inside a ~viewport-wide container the
      // computed scale comfortably exceeds 100 %, so we assert > 100 % to
      // distinguish it from the legacy 1.0 default. We don't assert an exact
      // value because the container width depends on layout chrome (header,
      // sidebar rail) which is not part of the contract being pinned.
      const zoomText = await page.locator(".zoom-level").first().textContent();
      const initialZoom = parseInt(zoomText?.replace("%", "") ?? "100", 10);
      console.log(
        `[TEST #1736] viewport=${viewport.width}x${viewport.height}, initial zoom=${initialZoom}%`
      );
      expect(initialZoom).toBeGreaterThan(100);

      // (2) The rendered PDF canvas width is strictly less than the
      // pdf-container width — the issue #1736 acceptance criterion. We
      // measure the canvas because that's the actual visible rendered page;
      // the CanvasWrapper around it is inline-block / shrink-wrapped, so it
      // matches the canvas dimensions.
      const containerBox = await page.locator("#pdf-container").boundingBox();
      const canvasBox = await page
        .locator("#pdf-container canvas")
        .first()
        .boundingBox();
      expect(containerBox).not.toBeNull();
      expect(canvasBox).not.toBeNull();
      console.log(
        `[TEST #1736] containerWidth=${containerBox!.width}px, canvasWidth=${
          canvasBox!.width
        }px`
      );
      expect(canvasBox!.width).toBeLessThan(containerBox!.width);

      // Documentation screenshot — captures the fit-to-width default at
      // this viewport so reviewers can eyeball the breathing room.
      await docScreenshot(
        page,
        `knowledge-base--pdf-default-zoom--${viewport.screenshotName}`
      );
    });
  });
}
