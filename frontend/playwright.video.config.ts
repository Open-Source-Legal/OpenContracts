import baseConfig from "./playwright.config";
import { defineConfig } from "@playwright/test";

/**
 * Playwright config override that forces video recording for every test.
 * Use only for capturing demo footage (`yarn playwright test -c playwright.video.config.ts ...`);
 * the default config keeps `video: "retain-on-failure"` to avoid bloat.
 */
export default defineConfig({
  ...baseConfig,
  use: {
    ...baseConfig.use,
    video: "on",
    viewport: { width: 1280, height: 800 },
  },
});
