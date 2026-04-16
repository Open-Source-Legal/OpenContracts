import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for full-stack E2E integration tests.
 *
 * Component tests live in `playwright-ct.config.ts` (mounted via
 * `@playwright/experimental-ct-react`). This config is for true E2E
 * tests that drive a real Vite dev server connected to a real Django
 * backend.
 *
 * Run locally:
 *   yarn test:e2e              # against an existing dev server
 *   yarn test:e2e:coverage     # boots an instrumented vite + collects istanbul coverage
 *
 * Tests that use this config must:
 *   - Live under `tests/e2e/` (or any other `*.spec.ts` file).
 *   - Import `test` and `expect` from `tests/e2e/fixtures.ts` so coverage
 *     is automatically collected after each test.
 */
export default defineConfig({
  testDir: "./tests",
  /* Match e2e specs only. Component tests use *.ct.tsx in playwright-ct.config.ts;
   * older `*.spec.tsx` files (DocumentPermissionFlow, route-state-sync-slug) run
   * inside the component-test runner via Vite, not here. */
  testMatch: ["e2e/**/*.spec.ts"],
  /* Tests within a file run sequentially to preserve in-memory auth state.
   * CI also pins to a single worker so the shared backend container is
   * not slammed with concurrent logins. */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only — the first run after `docker compose up` can be
   * slow for the JIT compile of vite-plugin-istanbul. */
  retries: process.env.CI ? 2 : 0,
  /* One worker on CI: tests share a backend, and parallel logins create
   * race conditions in the in-memory test cache backend. */
  workers: process.env.CI ? 1 : undefined,
  /* `list` is the human-readable reporter; `html` produces an artifact
   * for debugging failed runs in CI. */
  reporter: process.env.CI
    ? [
        ["list"],
        ["html", { open: "never", outputFolder: "playwright-report-e2e" }],
      ]
    : "list",
  /* Coverage instrumentation slows the first request meaningfully;
   * give the global run a generous ceiling. */
  globalTimeout: process.env.CI
    ? (process.env.COVERAGE ? 25 : 15) * 60 * 1000
    : undefined,
  /* Per-test timeout — coverage-instrumented vite is ~3x slower on
   * the first cold-load of a route. */
  timeout: process.env.CI ? 90 * 1000 : 60 * 1000,
  expect: {
    timeout: process.env.CI ? 20 * 1000 : 10 * 1000,
  },
  /* Shared settings for all the projects below. */
  use: {
    /* Base URL for `page.goto("/login")` etc. Points at the vite dev
     * server started by `webServer` below. */
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    /* Capture a trace + screenshot on failure to make CI failures
     * triageable from the uploaded HTML report. */
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    navigationTimeout: process.env.CI ? 60 * 1000 : 20 * 1000,
    actionTimeout: process.env.CI ? 20 * 1000 : 10 * 1000,
  },

  /* Single chromium project. We can add firefox/webkit later if cross-
   * browser regressions become a concern, but they triple CI time. */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Boot the Vite dev server before tests. Uses port 5173 (Vite default)
   * on a fixed host so the proxy to Django (localhost:8000) — configured
   * in `vite.config.ts` — works.
   *
   * COVERAGE=true is forwarded so vite-plugin-istanbul instruments the
   * frontend source. The fixture in `tests/e2e/fixtures.ts` then dumps
   * `window.__coverage__` to disk after each test.
   *
   * `reuseExistingServer: true` lets contributors leave their dev server
   * running locally and just run `yarn test:e2e`. */
  webServer: {
    command: "PORT=5173 yarn start",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 180 * 1000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      // Ensure password login is enabled (Auth0 disabled). The frontend
      // env loader (`scripts/env.js`) reads these REACT_APP_* values into
      // window._env_ so the runtime UseEnv hook sees USE_AUTH0=false.
      REACT_APP_USE_AUTH0: "false",
      REACT_APP_USE_ANALYZERS: "false",
      REACT_APP_ALLOW_IMPORTS: "false",
      REACT_APP_API_ROOT_URL: "http://127.0.0.1:8000",
      // Pass through coverage flag for vite-plugin-istanbul.
      ...(process.env.COVERAGE ? { COVERAGE: process.env.COVERAGE } : {}),
    },
  },
});
