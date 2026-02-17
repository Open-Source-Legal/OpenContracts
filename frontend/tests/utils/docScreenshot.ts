import type { Locator, Page } from "@playwright/test";
import { existsSync, mkdirSync } from "fs";
import { join, resolve } from "path";

/**
 * Directory where auto-generated documentation screenshots are saved.
 * These PNGs are committed to the repo and referenced from markdown docs.
 */
const SCREENSHOTS_DIR = resolve(
  __dirname,
  "../../../docs/assets/images/screenshots/auto"
);

const RELEASES_DIR = resolve(
  __dirname,
  "../../../docs/assets/images/screenshots/releases"
);

// Ensure output directory exists on module load.
mkdirSync(SCREENSHOTS_DIR, { recursive: true });

/**
 * Capture a documentation screenshot during a Playwright component test.
 *
 * ## Naming Convention
 *
 * Use `--` (double-dash) to separate hierarchical segments:
 *
 *   {area}--{component}--{state}.png
 *
 * - **area**: feature area (e.g. "landing", "badges", "corpus", "versioning")
 * - **component**: specific component or view (e.g. "hero-section", "celebration-modal")
 * - **state**: visual state captured (e.g. "anonymous", "with-data", "empty")
 *
 * Use single hyphens within segments for multi-word names.
 * At least two segments are required; three are recommended.
 *
 * ## Examples
 *
 * ```ts
 * await docScreenshot(page, "landing--hero-section--anonymous");
 * await docScreenshot(page, "badges--celebration-modal--auto-award");
 * await docScreenshot(page, "corpus--list-view--with-items");
 * ```
 *
 * ## Referencing in Markdown
 *
 * ```md
 * ![Hero Section](../assets/images/screenshots/auto/landing--hero-section--anonymous.png)
 * ```
 *
 * Screenshots are automatically updated on every PR via CI.
 */
export async function docScreenshot(
  page: Page,
  name: string,
  options?: {
    /** Clip a specific region of the page. */
    clip?: { x: number; y: number; width: number; height: number };
    /** Capture the full scrollable page instead of the viewport. */
    fullPage?: boolean;
    /** Capture only this element's bounding box instead of the full viewport. */
    element?: Locator;
  }
): Promise<void> {
  const segments = name.split("--");
  if (segments.length < 2) {
    throw new Error(
      `docScreenshot name "${name}" must use convention: ` +
        `{area}--{component}--{state} (at least 2 segments separated by --). ` +
        `Got ${segments.length} segment(s).`
    );
  }

  // Validate each segment is non-empty and uses only lowercase + hyphens + digits.
  for (const seg of segments) {
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(seg)) {
      throw new Error(
        `docScreenshot segment "${seg}" in "${name}" is invalid. ` +
          `Segments must be lowercase alphanumeric with single-hyphen separators ` +
          `(e.g. "hero-section", "with-data").`
      );
    }
  }

  const filePath = join(SCREENSHOTS_DIR, `${name}.png`);

  if (options?.element) {
    await options.element.screenshot({ path: filePath });
  } else {
    await page.screenshot({
      path: filePath,
      fullPage: options?.fullPage ?? false,
      ...(options?.clip ? { clip: options.clip } : {}),
    });
  }
}

/**
 * Capture a point-in-time screenshot for release documentation.
 *
 * Unlike `docScreenshot` (which CI overwrites on every PR), release screenshots
 * are **write-once**: if the file already exists the call is a no-op. This keeps
 * release notes "locked in amber" — they always show the UI as it was at that release.
 *
 * ## Output
 *
 * `docs/assets/images/screenshots/releases/{version}/{name}.png`
 *
 * ## Usage
 *
 * ```ts
 * await releaseScreenshot(page, "v3.0.0.b3", "landing-page", { fullPage: true });
 * ```
 *
 * ## Referencing in Markdown
 *
 * ```md
 * ![Landing Page](../assets/images/screenshots/releases/v3.0.0.b3/landing-page.png)
 * ```
 */
export async function releaseScreenshot(
  page: Page,
  version: string,
  name: string,
  options?: {
    /** Clip a specific region of the page. */
    clip?: { x: number; y: number; width: number; height: number };
    /** Capture the full scrollable page instead of the viewport. */
    fullPage?: boolean;
    /** Capture only this element's bounding box instead of the full viewport. */
    element?: Locator;
  }
): Promise<void> {
  if (!/^v\d+\.\d+\.\d+/.test(version)) {
    throw new Error(
      `releaseScreenshot version "${version}" is invalid. ` +
        `Must start with v{major}.{minor}.{patch} (e.g. "v3.0.0.b3").`
    );
  }

  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)) {
    throw new Error(
      `releaseScreenshot name "${name}" is invalid. ` +
        `Must be lowercase alphanumeric with single-hyphen separators.`
    );
  }

  const versionDir = join(RELEASES_DIR, version);
  const filePath = join(versionDir, `${name}.png`);

  // Write-once guard: never overwrite existing release screenshots.
  if (existsSync(filePath)) {
    return;
  }

  mkdirSync(versionDir, { recursive: true });

  if (options?.element) {
    await options.element.screenshot({ path: filePath });
  } else {
    await page.screenshot({
      path: filePath,
      fullPage: options?.fullPage ?? false,
      ...(options?.clip ? { clip: options.clip } : {}),
    });
  }
}
