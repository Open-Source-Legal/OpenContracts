import { defineConfig, devices } from "@playwright/test";

/**
 * Full-stack E2E Integration Tests Configuration
 *
 * These tests run against a live backend (Django + PostgreSQL) and real frontend.
 * They exercise complete user flows including authentication, document uploads,
 * folder management, and other integration scenarios.
 *
 * Prerequisites:
 * 1. Backend running: docker compose -f local.yml up
 * 2. Frontend dev server: yarn start (or this config will start it)
 *
 * Run tests:
 *   yarn test:e2e:integration
 *
 * Environment variables:
 *   E2E_BASE_URL - Base URL for tests (default: http://localhost:3000)
 *   E2E_API_URL - Backend API URL (default: http://localhost:8000)
 *   E2E_TEST_USER - Test user email (default: admin@example.com)
 *   E2E_TEST_PASSWORD - Test user password (default: admin)
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: ["**/*.e2e.ts"],

  /* Longer timeout for full-stack tests */
  timeout: 60000,
  expect: {
    timeout: 10000,
  },

  /* Run tests sequentially - they share database state */
  fullyParallel: false,
  workers: 1,

  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,

  /* Retry failed tests */
  retries: process.env.CI ? 2 : 1,

  /* Reporter configuration */
  reporter: [["list"], ["html", { outputFolder: "playwright-report-e2e" }]],

  /* Global setup/teardown for database seeding */
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",

  /* Shared settings for all the projects below */
  use: {
    /* Base URL for navigation */
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",

    /* Collect trace on failure */
    trace: "retain-on-failure",

    /* Screenshot on failure */
    screenshot: "only-on-failure",

    /* Video on failure (useful for debugging) */
    video: "retain-on-failure",

    /* Slow down actions for debugging (set via env var) */
    launchOptions: {
      slowMo: process.env.E2E_SLOW_MO ? parseInt(process.env.E2E_SLOW_MO) : 0,
    },
  },

  /* Configure projects - only Chromium for speed */
  projects: [
    /* Setup project - runs first to authenticate */
    {
      name: "setup",
      testMatch: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },

    /* Main test project - depends on setup */
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        /* Use stored auth state from setup */
        storageState: "./tests/e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },

    /* Mobile viewport tests */
    {
      name: "mobile",
      use: {
        ...devices["Pixel 5"],
        storageState: "./tests/e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],

  /*
   * Web server configuration
   *
   * For E2E integration tests, you should have both services running:
   *   1. Backend: docker compose -f local.yml up
   *   2. Frontend: yarn start:e2e (uses password auth, not Auth0)
   *
   * This config will reuse an existing frontend server if running.
   * If not running, it will start one with Auth0 disabled.
   */
  webServer: {
    command: "yarn start:e2e",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 180000, // 3 minutes for slow cold starts
    stdout: "pipe",
    stderr: "pipe",
  },
});
