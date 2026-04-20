/**
 * E2E integration test: corpus creation, document upload, and navigation.
 *
 * This spec exercises the primary user journey through the application:
 * create a corpus, upload a text document, verify it's processed, and
 * navigate through the corpus detail views. Each step builds on the
 * previous one, creating data that the view-interactions spec can reuse.
 *
 * The test document is a small .txt file processed by TxtParser (spacy).
 * CELERY_TASK_ALWAYS_EAGER ensures synchronous processing in the Django
 * process — no Celery worker or external parser containers are needed.
 */

import { test, expect } from "./fixtures";
import {
  TEST_USER,
  loginViaUI,
  spaNavigate,
  expectViewVisible,
  createCorpusViaUI,
  uploadDocumentViaUI,
} from "./helpers";

/** Small text document that TxtParser will split into sentence annotations. */
const TEST_DOCUMENT_CONTENT = [
  "OpenContracts is a document analytics platform for legal documents.",
  "It supports PDF and text-based document formats for analysis.",
  "Users can annotate documents and create structured data extracts.",
  "The platform uses machine learning models for document parsing.",
  "This is a test document for end-to-end integration coverage testing.",
].join("\n");

const CORPUS_TITLE = "E2E Test Corpus";
const CORPUS_DESCRIPTION = "Corpus created by the E2E workflow spec.";
const DOC_TITLE = "E2E Test Document";
const DOC_DESCRIPTION = "Text document for coverage testing.";

test.describe("Corpus workflow", () => {
  test("creates corpus, uploads document, and navigates detail views", async ({
    page,
  }) => {
    // ── Step 1: Login ──────────────────────────────────────────────
    await test.step("login", async () => {
      await loginViaUI(page, TEST_USER.username, TEST_USER.password);
    });

    // ── Step 2: Create corpus ──────────────────────────────────────
    await test.step("create corpus via UI", async () => {
      await createCorpusViaUI(page, CORPUS_TITLE, CORPUS_DESCRIPTION);
    });

    // ── Step 3: Upload document ────────────────────────────────────
    await test.step("upload text document via UI", async () => {
      await uploadDocumentViaUI(
        page,
        "test-document.txt",
        TEST_DOCUMENT_CONTENT,
        DOC_TITLE,
        DOC_DESCRIPTION,
        CORPUS_TITLE
      );
    });

    // ── Step 4: Verify document appears in list ────────────────────
    await test.step("verify document in document list", async () => {
      await spaNavigate(page, "/documents");
      await expect(page.getByText(DOC_TITLE).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    // ── Step 5: Navigate to corpus list, find our corpus ───────────
    await test.step("navigate to corpus and verify detail page", async () => {
      await spaNavigate(page, "/corpuses");
      await expect(page.getByText(CORPUS_TITLE).first()).toBeVisible({
        timeout: 15_000,
      });

      // Click the corpus card to navigate to its detail page
      await page.getByText(CORPUS_TITLE).first().click();

      // Wait for the corpus detail page to load — look for the corpus title
      // as a heading or the tab navigation
      await expect(page.getByText(/Documents/i).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    // ── Step 6: Browse corpus tabs ─────────────────────────────────
    await test.step("browse corpus detail tabs", async () => {
      // Click through the main tabs to exercise their rendering
      const tabs = ["Documents", "Annotations", "Extracts", "Settings"];
      for (const tabName of tabs) {
        const tab = page.getByRole("tab", { name: new RegExp(tabName, "i") });
        // Some tabs may not exist depending on corpus state — click if visible
        if (await tab.isVisible().catch(() => false)) {
          await tab.click();
          // Give the tab content time to render
          await page.waitForTimeout(1000);
        }
      }
    });

    // ── Step 7: Open document in knowledge base ─────────────────────
    await test.step("open document in knowledge base viewer", async () => {
      // Navigate back to corpus landing page
      await spaNavigate(page, "/corpuses");
      await page.getByText(CORPUS_TITLE).first().click();

      // The corpus landing page shows a home view. Click "Explore" to
      // switch to the power user view with full document list.
      const exploreBtn = page.getByRole("button", { name: /Explore/i });
      await expect(exploreBtn).toBeVisible({ timeout: 10_000 });
      await exploreBtn.click();
      await page.waitForTimeout(1000);

      // In Explore mode, look for the Documents tab and click it
      const docsTab = page.getByText(/Documents/i).first();
      if (await docsTab.isVisible().catch(() => false)) {
        await docsTab.click();
        await page.waitForTimeout(1000);
      }

      // Now look for and click the document
      await expect(page.getByText(DOC_TITLE).first()).toBeVisible({
        timeout: 15_000,
      });
      await page.getByText(DOC_TITLE).first().click();

      // Wait for the document viewer to render — the header shows the
      // document title and metadata, and the sidebar tabs appear
      await expect(page.getByText(DOC_TITLE).first()).toBeVisible({
        timeout: 20_000,
      });
      // Verify the knowledge base chrome loaded (sidebar tabs)
      await expect(page.getByText(/INDEX/i).first()).toBeVisible({
        timeout: 10_000,
      });
    });

    // ── Step 8: Exercise knowledge base sidebar tabs ───────────────
    await test.step("browse knowledge base sidebar tabs", async () => {
      // The sidebar tabs are vertical text labels on the right edge.
      // Click each by matching the tab label text.
      const tabLabels = ["FEED", "DISCUSSIONS", "INDEX"];

      for (const label of tabLabels) {
        const tab = page.getByText(label, { exact: true });
        if (await tab.isVisible().catch(() => false)) {
          await tab.click();
          await page.waitForTimeout(500);
          // Dismiss any unexpected modals
          if (
            await page
              .getByRole("button", { name: /Cancel/i })
              .isVisible()
              .catch(() => false)
          ) {
            await page.getByRole("button", { name: /Cancel/i }).click();
            await page.waitForTimeout(300);
          }
        }
      }

      // Click the CHAT tab separately — this exercises the chat tray
      const chatTab = page.getByText("CHAT", { exact: true });
      if (await chatTab.isVisible().catch(() => false)) {
        await chatTab.click();
        await page.waitForTimeout(1000);
        // Dismiss any "Add to Corpus" modal that may appear
        if (
          await page
            .getByRole("button", { name: /Cancel/i })
            .isVisible()
            .catch(() => false)
        ) {
          await page.getByRole("button", { name: /Cancel/i }).click();
          await page.waitForTimeout(300);
        }
      }
    });

    // ── Step 9: Interact with floating search/chat bar ─────────────
    await test.step("interact with floating search and chat bar", async () => {
      // The floating bar at the bottom has search (🔍) and chat (💬) icons
      // Try clicking each to expand them
      const floatingButtons = await page
        .locator('[class*="floating"] button, [class*="Floating"] button')
        .all();
      for (const btn of floatingButtons.slice(0, 2)) {
        if (await btn.isVisible().catch(() => false)) {
          await btn.click();
          await page.waitForTimeout(500);
        }
      }

      // Look for any expanded input (search or chat)
      const anyInput = page.getByPlaceholder(/Search document|Ask a question/i);
      if (await anyInput.isVisible().catch(() => false)) {
        await anyInput.fill("analytics platform");
        await page.waitForTimeout(500);
        await anyInput.clear();
      }

      // Press Escape to close any expanded floating bar
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
    });

    // ── Step 11: Visit extracts page ───────────────────────────────
    await test.step("visit extracts page with data", async () => {
      await spaNavigate(page, "/extracts");
      await expectViewVisible(page, {
        kind: "text",
        text: /Extract\s+structured data/i,
      });
    });

    // ── Step 12: Visit annotations page ────────────────────────────
    await test.step("visit annotations page with data", async () => {
      await spaNavigate(page, "/annotations");
      await expectViewVisible(page, {
        kind: "text",
        text: /Browse\s+annotations/i,
      });
    });
  });
});
