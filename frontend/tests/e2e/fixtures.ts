/**
 * E2E Playwright fixtures.
 *
 * Extends the base @playwright/test runtime with:
 *   1. Istanbul coverage collection from a real (non-CT) browser session.
 *   2. A small set of helpers that are useful across the navigation specs.
 *
 * The coverage collection mirrors the pattern used by the component-test
 * fixture in `tests/utils/coverage.ts` but is separate because the imports
 * differ (`@playwright/test` here vs `@playwright/experimental-ct-react`
 * there) and the temp directory is also distinct so the two coverage
 * streams can be merged or reported on independently.
 *
 * Coverage data is dumped to `frontend/coverage/e2e/.nyc_output/<uuid>.json`
 * after every test (best-effort — failures here never fail the test).
 */

import { test as baseTest, expect } from "@playwright/test";
import fs from "fs";
import path from "path";
import crypto from "crypto";

export { expect };

const COVERAGE_DIR = path.resolve(__dirname, "../../coverage/e2e/.nyc_output");

/**
 * Ensure the coverage output directory exists (idempotent).
 */
function ensureCoverageDir(): void {
  fs.mkdirSync(COVERAGE_DIR, { recursive: true });
}

/**
 * Read the Istanbul `__coverage__` global from the page and persist it
 * to disk under a unique filename. No-op when COVERAGE is not set.
 */
async function dumpPageCoverage(page: import("@playwright/test").Page) {
  if (!process.env.COVERAGE) return;
  try {
    const coverage = await page.evaluate(() => {
      return (window as unknown as { __coverage__?: unknown }).__coverage__;
    });
    if (!coverage) return;
    ensureCoverageDir();
    const id = crypto.randomUUID();
    const filePath = path.join(COVERAGE_DIR, `coverage-${id}.json`);
    fs.writeFileSync(filePath, JSON.stringify(coverage));
  } catch (err) {
    // Coverage collection is best-effort; never fail a test on it.
    // eslint-disable-next-line no-console
    console.warn("[e2e/coverage] failed to collect coverage data:", err);
  }
}

/**
 * The Django backend URL. Apollo sends GraphQL requests directly here
 * (cross-origin from the Vite dev server), so we need to handle CSRF.
 */
const DJANGO_URL =
  process.env.REACT_APP_API_ROOT_URL || "http://127.0.0.1:8000";

/**
 * Fetch a CSRF token from Django by hitting /admin/login/ (always
 * available) and extracting the csrftoken cookie from the response.
 */
async function fetchCsrfToken(): Promise<string | null> {
  try {
    const resp = await fetch(`${DJANGO_URL}/admin/login/`);
    const cookies = resp.headers.get("set-cookie") || "";
    const match = cookies.match(/csrftoken=([^;]+)/);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

/**
 * Extended test with automatic coverage collection on every page after each
 * test. Tests should `import { test, expect } from "./fixtures"`.
 */
export const test = baseTest.extend({
  page: async ({ page }, use) => {
    // Dismiss the cookie-consent modal before any navigation so it
    // doesn't block interactions. The CookieConsent component in App.tsx
    // checks localStorage("oc_cookieAccepted") on mount.
    await page.addInitScript(() => {
      localStorage.setItem("oc_cookieAccepted", "true");
    });

    // When Vite serves the frontend (not Django), the browser never gets
    // a csrftoken cookie. Apollo sends GraphQL requests directly to
    // Django (cross-origin), so session-auth requests fail with 403.
    //
    // route.continue() with modified headers does NOT work for cross-
    // origin requests in Playwright. Instead, we intercept, manually
    // fetch with CSRF headers via Node fetch(), and fulfill the response.
    const csrfToken = await fetchCsrfToken();
    // Playwright's route.continue() silently drops modified headers for
    // cross-origin requests (page on :5173, Django on :8000). Work around
    // this by intercepting ALL GraphQL requests and re-issuing them via
    // Node fetch() with the correct headers.
    await page.route(`${DJANGO_URL}/graphql/`, async (route) => {
      const request = route.request();
      const headers = { ...request.headers() };

      // Inject CSRF cookie+header for unauthenticated requests.
      // Authenticated requests (Bearer token) skip CSRF in Django,
      // but we still need to proxy them for header forwarding.
      if (!headers["authorization"] && csrfToken) {
        headers["x-csrftoken"] = csrfToken;
        headers["cookie"] = `csrftoken=${csrfToken}`;
      }

      try {
        const response = await fetch(request.url(), {
          method: request.method(),
          headers,
          body: request.postData(),
        });
        const body = await response.text();
        await route.fulfill({
          status: response.status,
          contentType:
            response.headers.get("content-type") || "application/json",
          body,
        });
      } catch {
        await route.abort();
      }
    });

    await use(page);
    await dumpPageCoverage(page);
  },
});
