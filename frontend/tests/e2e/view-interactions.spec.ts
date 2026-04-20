/**
 * E2E integration test: view interactions and admin routes.
 *
 * This spec exercises interactive features on each list view (modals,
 * filters, search) and navigates admin routes. It runs AFTER
 * corpus-workflow.spec.ts (alphabetical order) so the database already
 * contains a corpus and document created by that spec.
 *
 * Each test.describe block targets one view to keep failures isolated.
 */

import { test, expect } from "./fixtures";
import {
  TEST_USER,
  ADMIN_VIEWS,
  loginViaUI,
  spaNavigate,
  expectViewVisible,
} from "./helpers";

test.describe("View interactions", () => {
  test("exercises interactive features across all views", async ({ page }) => {
    await loginViaUI(page, TEST_USER.username, TEST_USER.password);

    // ── Corpuses: search and grid/list toggle ──────────────────────
    await test.step("corpuses — search and view toggle", async () => {
      await spaNavigate(page, "/corpuses");
      await expectViewVisible(page, { kind: "text", text: /Your\s+corpuses/i });

      // Use the search input
      const search = page.getByPlaceholder(/Search/i);
      if (await search.isVisible().catch(() => false)) {
        await search.fill("E2E Test");
        await page.waitForTimeout(500);
        await search.clear();
      }
    });

    // ── Documents: search filter ───────────────────────────────────
    await test.step("documents — search", async () => {
      await spaNavigate(page, "/documents");
      await expectViewVisible(page, {
        kind: "text",
        text: /Your\s+documents/i,
      });

      const search = page.getByPlaceholder(/Search/i);
      if (await search.isVisible().catch(() => false)) {
        await search.fill("E2E");
        await page.waitForTimeout(500);
        await search.clear();
      }
    });

    // ── Label Sets: open create modal and close ────────────────────
    await test.step("label sets — open create modal", async () => {
      await spaNavigate(page, "/label_sets");
      await expectViewVisible(page, {
        kind: "text",
        text: /Organize your\s+labels/i,
      });

      // Try to open the create modal via the Add button
      const addButton = page.getByLabel("Add");
      if (await addButton.isVisible().catch(() => false)) {
        await addButton.click();
        // Look for a "Create" option in the dropdown
        const createOption = page.getByText(/Create Label/i);
        if (await createOption.isVisible().catch(() => false)) {
          await createOption.click();
          // Close the modal by pressing Escape
          await page.keyboard.press("Escape");
          await page.waitForTimeout(500);
        } else {
          // Close the dropdown
          await page.keyboard.press("Escape");
        }
      }
    });

    // ── Extracts: check for create button ──────────────────────────
    await test.step("extracts — interact with create button", async () => {
      await spaNavigate(page, "/extracts");
      await expectViewVisible(page, {
        kind: "text",
        text: /Extract\s+structured data/i,
      });

      // Look for the "New Extract" or "Create Your First Extract" button
      const newExtractBtn = page.getByRole("button", {
        name: /New Extract|Create Your First Extract/i,
      });
      if (
        await newExtractBtn
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        await newExtractBtn.first().click();
        // The create extract modal should appear — close it
        await page.waitForTimeout(1000);
        await page.keyboard.press("Escape");
        await page.waitForTimeout(500);
      }
    });

    // ── Annotations: search controls ───────────────────────────────
    await test.step("annotations — search", async () => {
      await spaNavigate(page, "/annotations");
      await expectViewVisible(page, {
        kind: "text",
        text: /Browse\s+annotations/i,
      });

      const search = page.getByPlaceholder(/Search/i);
      if (await search.isVisible().catch(() => false)) {
        await search.fill("test");
        await page.waitForTimeout(500);
        await search.clear();
      }
    });

    // ── Discussions: verify page renders ───────────────────────────
    await test.step("discussions — verify rendering", async () => {
      await spaNavigate(page, "/discussions");
      await expectViewVisible(page, {
        kind: "anyText",
        texts: [/^Discussions$/i, /Search discussions/i],
      });
    });

    // ── Discovery landing: interact with sections ──────────────────
    await test.step("landing page — browse sections", async () => {
      await spaNavigate(page, "/");
      await expectViewVisible(page, {
        kind: "anyText",
        texts: [
          /Featured Collections/i,
          /Recent Activity/i,
          /Top Contributors/i,
        ],
      });
      // Scroll down to trigger lazy-loaded sections
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(1000);
    });

    // ── Admin routes ───────────────────────────────────────────────
    for (const view of ADMIN_VIEWS) {
      await test.step(`admin — ${view.name}`, async () => {
        await spaNavigate(page, view.path);
        await expectViewVisible(page, view.matcher, 15_000);
      });
    }
  });
});
