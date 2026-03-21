import { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const FIXTURE_PATH = path.resolve(__dirname, "../fixtures/test.docx");

/**
 * Intercept /test-fixtures/test.docx requests and serve the test fixture
 * from disk. Must be called BEFORE mounting any component that fetches
 * the DOCX fixture.
 *
 * This avoids using Vite's ?url import suffix, which can't be resolved
 * by Playwright's Node.js test runner during test discovery.
 */
export async function setupDocxFixture(page: Page): Promise<void> {
  await page.route("**/test-fixtures/test.docx", async (route) => {
    if (fs.existsSync(FIXTURE_PATH)) {
      const body = fs.readFileSync(FIXTURE_PATH);
      await route.fulfill({
        status: 200,
        contentType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        body,
      });
    } else {
      await route.fulfill({
        status: 404,
        body: "Test fixture not found",
      });
    }
  });
}
