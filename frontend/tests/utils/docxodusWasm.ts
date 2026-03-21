import { Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const WASM_DIR = path.resolve(
  __dirname,
  "../../node_modules/docxodus/dist/wasm"
);

const MIME_TYPES: Record<string, string> = {
  ".js": "application/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".dat": "application/octet-stream",
};

/**
 * Intercept /docxodus-wasm/** requests and serve files from node_modules.
 * Must be called BEFORE mounting any component that uses docxodus.
 *
 * In production, docxodus auto-detects its WASM path via import.meta.url.
 * In Playwright CT, the test bundle breaks auto-detection, so playwright/index.tsx
 * sets the base path to /docxodus-wasm/ and this route handler serves the files.
 */
export async function setupDocxodusWasm(page: Page): Promise<void> {
  await page.route("**/docxodus-wasm/**", async (route) => {
    const url = new URL(route.request().url());
    const relativePath = url.pathname.replace(/.*\/docxodus-wasm\//, "");
    const filePath = path.join(WASM_DIR, relativePath);

    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const ext = path.extname(filePath);
      const body = fs.readFileSync(filePath);
      await route.fulfill({
        status: 200,
        contentType: MIME_TYPES[ext] || "application/octet-stream",
        body,
      });
    } else {
      await route.fallback();
    }
  });
}
