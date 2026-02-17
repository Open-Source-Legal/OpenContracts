import { defineConfig, devices } from "@playwright/experimental-ct-react";
import { resolve } from "path";

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: "./",
  /* Add testMatch to specifically target component tests */
  testMatch: "**/*.ct.tsx",
  /* The base directory, relative to the config file, for snapshot files created with toMatchSnapshot and toHaveScreenshot. */
  snapshotDir: "./__snapshots__",
  /* Maximum time one test can run for. */
  timeout: 10 * 1000,
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only - 3 retries helps with flaky Vite dynamic import errors */
  retries: process.env.CI ? 3 : 0,
  /* Use 2 workers on CI for better balance of speed vs stability */
  workers: process.env.CI ? 2 : undefined,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: "html",
  /* Global timeout for the entire test run (10 minutes) */
  globalTimeout: process.env.CI ? 10 * 60 * 1000 : undefined,
  /* Expect timeout - give assertions more time on CI */
  expect: {
    timeout: process.env.CI ? 10 * 1000 : 5 * 1000,
  },
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: "on-first-retry",

    /* Port to use for Playwright component endpoint. */
    ctPort: 3100,

    /* Skip framer-motion animations so screenshots capture final state. */
    reducedMotion: "reduce",

    /* Navigation timeout - give Vite more time to serve dynamically imported modules */
    navigationTimeout: process.env.CI ? 30 * 1000 : 10 * 1000,

    /* Action timeout for clicks, fills, etc. */
    actionTimeout: process.env.CI ? 15 * 1000 : 5 * 1000,

    /* Vite config needed for component tests - JUST use the main config */
    ctViteConfig: {
      configFile: resolve(__dirname, "./vite.config.ts"),
    },
    /* Add this line to point to the directory containing index.tsx */
    ctTemplateDir: "./playwright",
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // { // Commenting out Firefox and Webkit for component tests initially for speed/simplicity
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],
});
