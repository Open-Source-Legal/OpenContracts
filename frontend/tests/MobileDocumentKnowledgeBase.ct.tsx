// tests/MobileDocumentKnowledgeBase.ct.tsx
//
// Mobile integration tests for DocumentKnowledgeBase.
//
// These tests mount the *real* DocumentKnowledgeBase (via MobileDKB, which
// wraps it in DocumentKnowledgeBaseTestWrapper) at a 390px viewport so the
// component renders MobileDocumentLayout — its `isMobile = width < 768` switch.
// Unlike MobileDocumentLayout.ct.tsx (a unit CT with stubbed props), this suite
// exercises the full data/GraphQL/viewer stack the mobile layout sits on top of.
//
// CRITICAL — Playwright CT split-import rule (CLAUDE.md pitfall #16):
// the JSX-component import (MobileDKB) stays in its own import statement,
// separate from the helper/mock imports below.

import { MobileDKB } from "./MobileDocumentKnowledgeBase.harness";

import React from "react";
import fs from "fs";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import type { Page } from "@playwright/test";
import type { MockedResponse } from "@apollo/client/testing";
import {
  CORPUS_ID,
  MOCK_PDF_URL_FOR_STRUCTURAL_TEST,
  PDF_DOC_ID_FOR_STRUCTURAL_TEST,
  TEST_PDF_PATH,
  TEST_PAWLS_PATH,
  graphqlMocks,
  mockPdfDocumentForStructuralTest,
  mockAnnotationNonStructural1,
} from "./mocks/DocumentKnowledgeBase.mocks";
import { GET_DOCUMENT_SUMMARY_VERSIONS } from "../src/components/knowledge_base/document/floating_summary_preview/graphql/documentSummaryQueries";
import {
  GET_CORPUS_VERSIONS,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
  GET_DOCUMENT_ANNOTATION_INDEX,
} from "../src/graphql/queries";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../src/assets/configurations/constants";

// 390px-wide phone viewport — below the 768px MobileDocumentLayout breakpoint.
test.use({ viewport: { width: 390, height: 844 } });
test.setTimeout(90_000);

const LONG_TIMEOUT = 60_000;

// The structural-test fixture document is used because — unlike the plain PDF
// fixture — it ships real annotations (mockAnnotationNonStructural1 +
// mockMultiPageAnnotation), required for the annotation-feed / detail-sheet
// tests to be meaningful.
const DOC_ID = PDF_DOC_ID_FOR_STRUCTURAL_TEST;

/**
 * Summary / version mocks. Mirrors `createSummaryMocks` from
 * DocumentKnowledgeBase.ct.tsx but with empty revision lists (the mobile suite
 * does not assert on summary version history). Each query is registered twice
 * to tolerate refetches, exactly like the desktop suite.
 */
const summaryVersionMock = (): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_SUMMARY_VERSIONS,
    variables: { documentId: DOC_ID, corpusId: CORPUS_ID },
  },
  result: {
    data: {
      document: {
        id: DOC_ID,
        summaryContent: "",
        currentSummaryVersion: 0,
        summaryRevisions: [],
        __typename: "DocumentType",
      },
    },
  },
});

const corpusVersionMock = (): MockedResponse => ({
  request: {
    query: GET_CORPUS_VERSIONS,
    variables: { documentId: DOC_ID, corpusId: CORPUS_ID },
  },
  result: {
    data: {
      document: {
        id: DOC_ID,
        corpusVersions: [],
        __typename: "DocumentType",
      },
    },
  },
});

/**
 * Augments a fixture annotation with the extra fields GET_DOCUMENT_ANNOTATIONS
 * _ONLY selects (`analysis`, `userFeedback`, `linkUrl`, `contentModalities`) so
 * Apollo does not drop the response as incomplete.
 */
const fullAnnotation = (ann: any) => ({
  ...ann,
  analysis: null,
  linkUrl: null,
  contentModalities: [],
  userFeedback: {
    __typename: "UserFeedbackTypeConnection",
    edges: [],
    totalCount: 0,
  },
});

/**
 * GET_DOCUMENT_ANNOTATIONS_ONLY mock returning the structural-test document's
 * *non-structural* annotations (the query selects `isStructural: false`).
 *
 * Without this, DocumentKnowledgeBaseTestWrapper's appended default for this
 * query returns an EMPTY annotation list — and because the mobile suite waits
 * for the PDF canvas (~seconds), that empty refetch lands and wipes the
 * annotation atom that GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS first populated.
 * Registered ahead of `graphqlMocks` so MockedProvider consumes it first, and
 * several times to tolerate the loader's refetches.
 */
const annotationsOnlyMock = (): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_ANNOTATIONS_ONLY,
    variables: { documentId: DOC_ID, corpusId: CORPUS_ID, analysisId: null },
  },
  result: {
    data: {
      document: {
        id: DOC_ID,
        // Non-structural annotations only (matches the query's isStructural:false).
        allAnnotations: (mockPdfDocumentForStructuralTest.allAnnotations ?? [])
          .filter((a) => !a.structural)
          .map(fullAnnotation),
        allRelationships: [],
        __typename: "DocumentType",
      },
    },
  },
});

/**
 * GET_DOCUMENT_ANNOTATION_INDEX mock for the mobile Sections sheet, which now
 * loads the document's OC_SECTION index (the same query the desktop "Index"
 * tab uses). The structural-test fixture carries no OC_SECTION entries, so the
 * sheet renders its empty state — which the Sections test explicitly accepts.
 * Registered twice to tolerate the sheet's open/refetch.
 */
const documentIndexMock = (): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_ANNOTATION_INDEX,
    variables: {
      documentId: DOC_ID,
      corpusId: CORPUS_ID,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
  },
  result: {
    data: {
      annotations: {
        totalCount: 0,
        edges: [],
        __typename: "AnnotationTypeConnection",
      },
    },
  },
});

// Assembled Node-side and threaded into the browser-bundled harness as props
// (the mocks fixture cannot be imported by the harness — see its header).
const mobileMocks: MockedResponse[] = [
  annotationsOnlyMock(),
  annotationsOnlyMock(),
  annotationsOnlyMock(),
  ...graphqlMocks,
  summaryVersionMock(),
  summaryVersionMock(),
  corpusVersionMock(),
  corpusVersionMock(),
  documentIndexMock(),
  documentIndexMock(),
];

/** Renders the harness with the assembled mocks. */
const mobileDkb = () => (
  <MobileDKB mocks={mobileMocks} documentId={DOC_ID} corpusId={CORPUS_ID} />
);

// PAWLs token geometry, read once at module load (same pattern as the desktop
// DocumentKnowledgeBase.ct.tsx suite).
let mockPawlsDataContent: unknown = null;
try {
  mockPawlsDataContent = JSON.parse(fs.readFileSync(TEST_PAWLS_PATH, "utf-8"));
} catch (err) {
  console.error(`[MOCK PREP ERROR] Failed to read ${TEST_PAWLS_PATH}:`, err);
}

/**
 * Registers the REST routes the document viewer needs: the PDF binary, the
 * PAWLs token JSON and the markdown summary. Mirrors the desktop suite's
 * `registerRestMocks` but scoped to the structural-test fixture document the
 * mobile harness mounts.
 */
async function registerRestMocks(page: Page): Promise<void> {
  await page.route(
    `**/${mockPdfDocumentForStructuralTest.pawlsParseFile}`,
    (route) => {
      if (!mockPawlsDataContent) {
        return route.fulfill({ status: 500, body: "Mock PAWLS data missing" });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockPawlsDataContent),
      });
    }
  );

  await page.route(
    `**/${mockPdfDocumentForStructuralTest.mdSummaryFile}`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/markdown",
        body: "# Mock Summary Title\n\nMock summary details.",
      })
  );

  await page.route(MOCK_PDF_URL_FOR_STRUCTURAL_TEST, async (route) => {
    if (!fs.existsSync(TEST_PDF_PATH)) {
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
}

test.beforeEach(async ({ page }) => {
  await registerRestMocks(page);

  // Stub the chat WebSocket so RightPanelContent's chat mode mounts cleanly.
  await page.evaluate(() => {
    class StubSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      url: string;
      readyState = 1;
      onopen?: (e: unknown) => void;
      onmessage?: (e: unknown) => void;
      onclose?: (e: unknown) => void;
      constructor(url: string) {
        this.url = url;
        setTimeout(() => this.onopen && this.onopen({}), 0);
      }
      send() {}
      close() {
        this.readyState = 3;
        this.onclose && this.onclose({});
      }
      addEventListener() {}
      removeEventListener() {}
    }
    // @ts-ignore - intentional test stub
    window.WebSocket = StubSocket;
  });

  page.on("pageerror", (err) => console.error(`[PAGE ERROR] ${err.message}`));
  page.on("console", (msg) => {
    const t = msg.text();
    if (
      t.includes("No more mocked") ||
      t.includes("ApolloError") ||
      t.includes("KNOWLEDGE") ||
      t.includes("annotation")
    ) {
      console.log(`[BROWSER] ${t.slice(0, 200)}`);
    }
  });
});

/** Waits for the document viewer to finish its first PDF render. */
async function waitForDocumentReady(page: Page): Promise<void> {
  await expect(
    page.getByRole("heading", {
      name: mockPdfDocumentForStructuralTest.title ?? "",
    })
  ).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(page.locator("#pdf-container canvas").first()).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
}

/* ───────────────────────────────────────────────────────────────────────────
 * 1. Mobile layout renders; desktop floating UI does NOT
 * ─────────────────────────────────────────────────────────────────────────── */
test("renders the mobile layout, not the desktop floating UI", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());

  // Mobile chrome present: the tab bar (role="tablist" with 4 tabs) and the
  // persistent Ask bar.
  const tabBar = page.getByRole("tablist");
  await expect(tabBar).toBeVisible({ timeout: LONG_TIMEOUT });
  for (const name of ["Document", "Summary", "Annotations", "More"]) {
    await expect(page.getByRole("tab", { name })).toBeVisible();
  }
  await expect(page.getByPlaceholder(/ask anything/i)).toBeVisible();

  // The mobile Document surface wrapper is the active surface.
  await expect(page.getByTestId("mobile-surface-document")).toBeVisible();

  // Desktop-only floating UI must NOT render in the mobile layout.
  // FloatingDocumentControls (the desktop FAB cluster) and its buttons:
  await expect(page.getByTestId("settings-button")).toHaveCount(0);
  await expect(page.getByTestId("width-button")).toHaveCount(0);
  await expect(page.getByTestId("analyses-button")).toHaveCount(0);
  await expect(page.getByTestId("extracts-button")).toHaveCount(0);
  // FloatingDocumentInput (the desktop floating ask box) uses a distinct
  // placeholder; the mobile layout uses MobileAskBar instead.
  await expect(page.getByPlaceholder("Ask a question...")).toHaveCount(0);
});

/* ───────────────────────────────────────────────────────────────────────────
 * 2. No horizontal overflow at 390px
 * ─────────────────────────────────────────────────────────────────────────── */
test("has no horizontal overflow at 390px", async ({ mount, page }) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // Allow the PDF layout to settle before measuring.
  await page.waitForTimeout(1500);

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth
  );
  console.log(`[TEST] documentElement horizontal overflow: ${overflow}px`);
  expect(overflow).toBeLessThanOrEqual(1);

  // Documentation capture: the mobile Document surface at fit-to-width zoom.
  await docScreenshot(page, "knowledge-base--mobile--document");
});

/* ───────────────────────────────────────────────────────────────────────────
 * 3. Tab navigation swaps surfaces and reflects aria-selected
 * ─────────────────────────────────────────────────────────────────────────── */
test("tab navigation activates each surface", async ({ mount, page }) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // Document tab is the default-active surface.
  await expect(page.getByRole("tab", { name: "Document" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByTestId("mobile-surface-document")).toBeVisible();

  // Summary tab.
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByTestId("mobile-surface-summary")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Documentation capture: the mobile Summary surface, active.
  await docScreenshot(page, "knowledge-base--mobile--summary");

  // Annotations tab.
  await page.getByRole("tab", { name: "Annotations" }).click();
  await expect(page.getByRole("tab", { name: "Annotations" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByTestId("mobile-surface-annotations")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // More tab opens the More sheet (it is not a swappable surface).
  await page.getByRole("tab", { name: "More" }).click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
});

/* ───────────────────────────────────────────────────────────────────────────
 * 4a. Focusing the Ask bar no longer opens the Chat sheet (regression for the
 *    type-to-launch behavior — users type inline on the main view, the sheet
 *    appears only after submit or history tap).
 * ─────────────────────────────────────────────────────────────────────────── */
test("focusing the Ask bar does not open the Chat sheet", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  const ask = page.getByPlaceholder(/ask anything/i);
  await ask.click();
  // Type a character to confirm focus actually landed in the bar. If the
  // chat sheet had opened on focus it would have stolen focus (or covered
  // the bar entirely), and this fill would land in the wrong element or
  // fail. This replaces a brittle wall-clock waitForTimeout — the typed
  // value is the positive signal that focus stayed put.
  await ask.fill("x");
  await expect(ask).toHaveValue("x");

  // The chat sheet must NOT have opened on focus.
  await expect(page.getByTestId("mobile-surface-chat")).toHaveCount(0);

  // Clear the bar so other tests sharing the page start clean.
  await ask.fill("");
});

/* ───────────────────────────────────────────────────────────────────────────
 * 4b. Submitting from the Ask bar opens the Chat sheet directly in new-chat
 *    mode so the typed message starts a fresh conversation immediately,
 *    instead of being dropped on the conversation-list view.
 * ─────────────────────────────────────────────────────────────────────────── */
test("submitting from the Ask bar opens the Chat sheet in new-chat mode", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // Type and submit on the main view.
  const ask = page.getByPlaceholder(/ask anything/i);
  await ask.fill("what is the term length?");
  await ask.press("Enter");

  // The Chat sheet opens.
  await expect(page.getByTestId("mobile-surface-chat")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
  // The new-chat composer is on screen — its WebSocket-gated textarea uses one
  // of three placeholders depending on connection state. (The stub WebSocket
  // in beforeEach reports readyState=1, so we usually land on "Type your
  // message..." but allow the others to keep the assertion resilient.)
  await expect(
    page
      .getByPlaceholder(/type your message/i)
      .or(page.getByPlaceholder(/waiting for connection/i))
      .or(page.getByPlaceholder(/assistant is responding/i))
  ).toBeVisible({ timeout: LONG_TIMEOUT });
  // And NOT the conversation-list view (which carries the "Search by title…"
  // input). This is the distinguishing signal: new-chat mode skips the list.
  await expect(page.getByPlaceholder(/search by title/i)).toHaveCount(0);

  // Documentation capture: the mobile Chat sheet opened straight into a new chat.
  await docScreenshot(page, "dkb--mobile--chat-type-to-launch");
});

/* ───────────────────────────────────────────────────────────────────────────
 * 4c. The history affordance on the Ask bar opens the Chat sheet to the
 *    conversation list (the old focus-opens-sheet path, preserved behind an
 *    explicit control).
 * ─────────────────────────────────────────────────────────────────────────── */
test("tapping the history button opens the Chat sheet to the conversation list", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  await page
    .getByRole("button", { name: /open conversation history/i })
    .click();

  await expect(page.getByTestId("mobile-surface-chat")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Documentation capture: the mobile Chat sheet, opened to the conversation list.
  await docScreenshot(page, "dkb--mobile--chat-history-affordance");
});

/* ───────────────────────────────────────────────────────────────────────────
 * 5. Annotation review — the Annotations surface renders the unified feed with
 *    real annotation rows; tapping a row opens the "Annotation" detail sheet.
 *
 * MobileDocumentLayout opens the detail sheet when the URL-backed
 * `selectedAnnotations` selection is non-empty. In production CentralRouteManager
 * syncs the `?ann=` param into the `selectedAnnotationIds` reactive var; the CT
 * harness mounts a lightweight LocationWatcher that performs the same `ann`
 * sync (see DocumentKnowledgeBaseTestWrapper) so this flow is faithfully
 * exercised. (This is also the test that caught the AnnotationsSurface
 * zero-height layout bug — see the report.)
 * ─────────────────────────────────────────────────────────────────────────── */
test("the annotation feed renders rows and a row opens the detail sheet", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // Switch to the Annotations surface.
  await page.getByRole("tab", { name: "Annotations" }).click();
  await expect(page.getByTestId("mobile-surface-annotations")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // The unified feed renders the structural-test document's two non-structural
  // fixture annotations as HighlightItem rows (data-testid="highlight-item").
  const row = page
    .locator(`[data-annotation-id="${mockAnnotationNonStructural1.id}"]`)
    .first();
  await expect(row).toBeVisible({ timeout: LONG_TIMEOUT });
  await expect(
    page.locator('[data-annotation-id="multi-page-annotation-1"]').first()
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // The feed's virtualized viewport must have a non-zero measured height —
  // a regression guard for the AnnotationsSurface flex-context fix.
  const feedViewportHeight = await page
    .getByTestId("feed-viewport")
    .evaluate((el) => (el as HTMLElement).offsetHeight);
  console.log(`[TEST] feed-viewport height: ${feedViewportHeight}px`);
  expect(feedViewportHeight).toBeGreaterThan(0);

  // Documentation capture: the mobile Annotations surface with the feed rendered.
  await docScreenshot(page, "knowledge-base--mobile--annotations");

  // Tapping a row selects the annotation and opens the "Annotation" sheet.
  await row.click();
  await expect(page.getByText("Annotation", { exact: true })).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
  // The detail sheet renders the annotation's quoted text.
  await expect(
    page.getByText(mockAnnotationNonStructural1.rawText).first()
  ).toBeVisible({ timeout: LONG_TIMEOUT });

  // Mobile UX: the row tap also switches the active tab to Document so the
  // annotation is visible in the viewer the moment the detail sheet is
  // dismissed (instead of leaving the user on the Annotations feed).
  await expect(page.getByRole("tab", { name: "Document" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByRole("tab", { name: "Annotations" })).toHaveAttribute(
    "aria-selected",
    "false"
  );

  await docScreenshot(page, "dkb--mobile--annotations-tap-switches-tab");
});

/** Reads the document zoom percentage off the MobileDocToolbar "Fit width" chip. */
async function readZoomPercent(page: Page): Promise<number> {
  const chip = page.locator('[aria-label="Fit width"]');
  await expect(chip).toBeVisible({ timeout: LONG_TIMEOUT });
  const text = (await chip.textContent())?.trim() ?? "";
  const match = text.match(/(\d+)\s*%/);
  return match ? parseInt(match[1], 10) : NaN;
}

/* ───────────────────────────────────────────────────────────────────────────
 * 6. Pinch-zoom — replacement for the desktop-layout-at-mobile tests removed
 *    in Task 14.
 *
 * The pinch-to-zoom handlers (useZoomManager.handleTouchStart/Move/End) are
 * attached to `document` and gated on `activeLayer === "document"`. In the
 * mobile layout the Document tab keeps that layer active, so a faithful
 * two-finger TouchEvent simulation — the same technique the deleted tests used
 * — drives the zoom against MobileDocumentLayout's Document surface.
 *
 * SUBSTITUTION NOTE: the deleted desktop tests observed the result via the
 * `zoom-indicator` overlay, but that overlay is rendered only by
 * DesktopDocumentLayout — MobileDocumentLayout does not render it. The mobile
 * layout instead surfaces the live zoom in the MobileDocToolbar's "Fit width"
 * chip (`zoomPercent = zoomLevel * 100`), which this test reads. It also
 * asserts the useMobileFitToWidth mount behaviour: the document opens at a
 * fit-to-width zoom — below 100% for a letter-size page on a 390px viewport —
 * which is the baseline the pinch moves away from.
 * ─────────────────────────────────────────────────────────────────────────── */
test("pinch-zoom adjusts the document zoom in the mobile layout", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // The Document tab is active, so MobileDocumentLayout has already run
  // useMobileFitToWidth — the document opens at a fit-to-width zoom (well
  // below the desktop 1.0 default for a letter-size page on a 390px viewport).
  await page.waitForTimeout(2000);
  const fitZoom = await readZoomPercent(page);
  console.log(`[TEST] fit-to-width zoom on mount: ${fitZoom}%`);
  // useMobileFitToWidth shrinks an ~816px letter page to a ~390px viewport.
  expect(fitZoom).toBeGreaterThan(0);
  expect(fitZoom).toBeLessThan(100);

  const dispatchTouch = async (
    type: "touchstart" | "touchmove" | "touchend",
    distance: number
  ) => {
    await page.evaluate(
      ([t, dist]) => {
        const cx = 195;
        const cy = 420;
        const d = dist as number;
        const mkTouch = (id: number, x: number) =>
          new Touch({
            identifier: id,
            target: document.body,
            clientX: x,
            clientY: cy,
            pageX: x,
            pageY: cy,
          });
        const touches =
          t === "touchend"
            ? []
            : [mkTouch(0, cx - d / 2), mkTouch(1, cx + d / 2)];
        document.dispatchEvent(
          new TouchEvent(t as string, {
            bubbles: true,
            cancelable: true,
            touches,
            targetTouches: touches,
            changedTouches: touches,
          })
        );
      },
      [type, distance] as const
    );
    await page.waitForTimeout(120);
  };

  // Pinch OUT (zoom in): fingers start 120px apart, end ~330px apart (~2.7x),
  // which the pinch handler maps onto the zoom level.
  await dispatchTouch("touchstart", 120);
  await dispatchTouch("touchmove", 200);
  await dispatchTouch("touchmove", 280);
  await dispatchTouch("touchmove", 330);
  await dispatchTouch("touchend", 0);
  await page.waitForTimeout(500);

  // The toolbar's zoom chip reflects the new, larger zoom level.
  const zoomedIn = await readZoomPercent(page);
  console.log(`[TEST] zoom after pinch-out: ${zoomedIn}%`);
  expect(zoomedIn).toBeGreaterThan(fitZoom);

  // Pinch IN (zoom out): bring the fingers back together.
  await dispatchTouch("touchstart", 330);
  await dispatchTouch("touchmove", 220);
  await dispatchTouch("touchmove", 130);
  await dispatchTouch("touchend", 0);
  await page.waitForTimeout(500);

  const zoomedOut = await readZoomPercent(page);
  console.log(`[TEST] zoom after pinch-in: ${zoomedOut}%`);
  expect(zoomedOut).toBeLessThan(zoomedIn);
});

/* ───────────────────────────────────────────────────────────────────────────
 * 7. The document toolbar opens the Sections and Find sheets
 * ─────────────────────────────────────────────────────────────────────────── */
test("the document toolbar opens the Sections and Find sheets", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  // Sections — opens a MobileSheet over the structural index (the list, or the
  // empty state when the document carries no structural annotations).
  await page.getByRole("button", { name: /sections/i }).click();
  await expect(
    page
      .getByTestId("mobile-sections-list")
      .or(page.getByTestId("mobile-sections-empty"))
  ).toBeVisible({ timeout: LONG_TIMEOUT });
  await page.getByRole("button", { name: "Close" }).last().click();
  await page.waitForTimeout(500);

  // Find — opens the in-document text-search sheet.
  await page.getByRole("button", { name: /find/i }).click();
  await expect(page.getByTestId("mobile-find-sheet")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
});

/* ───────────────────────────────────────────────────────────────────────────
 * 8. The More sheet navigates through its Tier-2 sub-views
 * ─────────────────────────────────────────────────────────────────────────── */
test("the More sheet navigates through its sub-views", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  await page.getByRole("tab", { name: "More" }).click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // Documentation capture: the More sheet's Tier-2 surface menu.
  await docScreenshot(page, "knowledge-base--mobile--more-menu");

  // Discussions sub-view.
  await page.getByTestId("mobile-more-discussions").click();
  await expect(page.getByTestId("mobile-more-discussions-surface")).toBeVisible(
    { timeout: LONG_TIMEOUT }
  );
  await page.getByTestId("mobile-more-back").click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible();

  // Notes sub-view.
  await page.getByTestId("mobile-more-notes").click();
  await expect(page.getByTestId("mobile-more-notes-surface")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
  await page.getByTestId("mobile-more-back").click();
  await expect(page.getByTestId("mobile-more-menu")).toBeVisible();

  // Document info & versions — a mock-free read-only metadata view.
  await page.getByTestId("mobile-more-info").click();
  await expect(page.getByTestId("mobile-more-info-surface")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });
});

/* ───────────────────────────────────────────────────────────────────────────
 * 9. The annotations filter bar expands its compact controls
 * ─────────────────────────────────────────────────────────────────────────── */
test("the annotations filter bar expands its compact controls", async ({
  mount,
  page,
}) => {
  await mount(mobileDkb());
  await waitForDocumentReady(page);

  await page.getByRole("tab", { name: "Annotations" }).click();
  await expect(page.getByTestId("mobile-surface-annotations")).toBeVisible({
    timeout: LONG_TIMEOUT,
  });

  // The compact "Filter & sort" toggle reveals the full content-type and sort
  // control set inline (SidebarControlBar's compact branch).
  const toggle = page.getByTestId("compact-filter-sort-toggle");
  await expect(toggle).toBeVisible({ timeout: LONG_TIMEOUT });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
});
