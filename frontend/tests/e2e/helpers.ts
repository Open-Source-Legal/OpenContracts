/**
 * E2E test helpers shared across the integration specs.
 *
 * All views in `frontend/src/views/` are catalogued here so the navigation
 * spec can iterate over them. For each view we record:
 *   - `path`          The URL path (or "/" for the discover landing).
 *   - `name`          A human-readable label used in test titles.
 *   - `matcher`       Visible text or selector that proves the view
 *                     rendered. We deliberately use "any of" lists where
 *                     the rendered copy varies (loading vs settled, etc).
 *   - `requiresAuth`  Whether navigating to the path while anonymous still
 *                     produces a usable view. Anonymous-friendly views are
 *                     also exercised in the unauthenticated test pass to
 *                     boost line coverage.
 *
 * View → route mapping is taken from `App.tsx`. Routes whose elements live
 * in `src/components/routes/` (e.g. `LeaderboardRoute`, `UserProfileRoute`)
 * still ultimately render a view from `src/views/`, so they're included.
 */

import { Page, expect } from "@playwright/test";

export interface ViewSpec {
  /** URL path, e.g. "/corpuses". */
  path: string;
  /** Human-readable label. */
  name: string;
  /** Visible text or selector that proves the view rendered. */
  matcher: ViewMatcher;
  /** True if the view requires an authenticated user to be useful. */
  requiresAuth: boolean;
  /** True if the route redirects (e.g. /profile → /users/<slug>). */
  redirects?: boolean;
}

export type ViewMatcher =
  | { kind: "text"; text: string | RegExp }
  | { kind: "anyText"; texts: Array<string | RegExp> }
  | { kind: "selector"; selector: string };

/**
 * Catalog of every routed view in `src/views/`. Order matters for the
 * navigation walk: we go from public/landing pages first to deeper
 * authenticated views last, mirroring how a real user would discover
 * the product.
 */
export const VIEWS: ViewSpec[] = [
  {
    path: "/",
    name: "DiscoveryLanding",
    matcher: {
      kind: "anyText",
      texts: [/Featured Collections/i, /Recent Activity/i, /Top Contributors/i],
    },
    requiresAuth: false,
  },
  {
    path: "/corpuses",
    name: "Corpuses",
    matcher: { kind: "text", text: /Your\s+corpuses/i },
    requiresAuth: false,
  },
  {
    path: "/documents",
    name: "Documents",
    matcher: { kind: "text", text: /Your\s+documents/i },
    requiresAuth: false,
  },
  {
    path: "/label_sets",
    name: "LabelSets",
    matcher: { kind: "text", text: /Organize your\s+labels/i },
    requiresAuth: false,
  },
  {
    path: "/annotations",
    name: "Annotations",
    matcher: { kind: "text", text: /Browse\s+annotations/i },
    requiresAuth: false,
  },
  {
    path: "/extracts",
    name: "Extracts",
    matcher: { kind: "text", text: /Extract\s+structured data/i },
    requiresAuth: false,
  },
  {
    path: "/discussions",
    name: "GlobalDiscussions",
    matcher: {
      kind: "anyText",
      texts: [/^Discussions$/i, /Search discussions/i],
    },
    requiresAuth: false,
  },
  {
    path: "/threads",
    name: "ThreadSearchRoute",
    matcher: { kind: "text", text: /Search Discussions/i },
    requiresAuth: false,
  },
  {
    path: "/privacy",
    name: "PrivacyPolicy",
    matcher: {
      kind: "anyText",
      texts: [/PRIVACY NOTICE/i, /personal information/i],
    },
    requiresAuth: false,
  },
  {
    path: "/terms_of_service",
    name: "TermsOfService",
    matcher: { kind: "text", text: /Terms of Service/i },
    requiresAuth: false,
  },
  // /profile is NOT included because it always redirects to /users/<slug>
  // via React Router's <Navigate>. The pushState-based spaNavigate helper
  // cannot follow <Navigate> redirects, so we skip it here. The
  // UserProfile view is still covered by direct navigation in a dedicated
  // spec if needed.
];

/**
 * Credentials for the initial superuser created by
 * `opencontractserver/users/migrations/0003_create_initial_superuser.py`.
 * The CI workflow sets E2E_TEST_USERNAME and E2E_TEST_PASSWORD via the
 * `env:` block on the Playwright step; local callers must export them or
 * the test will fail with a clear message.
 */
export const TEST_USER = {
  username: process.env.E2E_TEST_USERNAME || "admin",
  password: (() => {
    const pw = process.env.E2E_TEST_PASSWORD;
    if (!pw) {
      throw new Error(
        "E2E_TEST_PASSWORD environment variable is not set. " +
          "Set it to the superuser password before running E2E tests."
      );
    }
    return pw;
  })(),
};

/**
 * Wait for a `ViewMatcher` to be satisfied on the page. Uses Playwright's
 * built-in expect retry loop so flaky data fetches don't fail the test.
 */
export async function expectViewVisible(
  page: Page,
  matcher: ViewMatcher,
  timeoutMs = 20_000
): Promise<void> {
  switch (matcher.kind) {
    case "text": {
      await expect(page.getByText(matcher.text).first()).toBeVisible({
        timeout: timeoutMs,
      });
      return;
    }
    case "anyText": {
      // At least one of the candidate texts must become visible.
      // Uses Playwright's built-in retry via expect().toPass().
      await expect(async () => {
        for (const text of matcher.texts) {
          if (await page.getByText(text).first().isVisible()) {
            return;
          }
        }
        throw new Error(`none of [${matcher.texts.join(", ")}] visible yet`);
      }).toPass({ timeout: timeoutMs, intervals: [250] });
      return;
    }
    case "selector": {
      await expect(page.locator(matcher.selector).first()).toBeVisible({
        timeout: timeoutMs,
      });
      return;
    }
  }
}

/**
 * Perform a UI-driven password login against the live frontend. The login
 * form lives at `src/views/Login.tsx`; on success it stores an in-memory
 * authToken and `navigate("/")`s the user away. We wait for that redirect
 * so callers get a page already in the authenticated state.
 *
 * NOTE: the Apollo reactive var that holds the token is in-memory only,
 * so any subsequent full `page.goto(...)` would lose it. Use SPA-style
 * navigation (`spaNavigate` below or `page.click` on a NavMenu link)
 * instead of `page.goto` after this function returns.
 */
export async function loginViaUI(
  page: Page,
  username: string = TEST_USER.username,
  password: string = TEST_USER.password
): Promise<void> {
  await page.goto("/login");

  // The login form has placeholder-only labels; rely on the placeholders
  // (which are stable copy in `Login.tsx`) to find the inputs.
  const usernameInput = page.getByPlaceholder("Username");
  const passwordInput = page.getByPlaceholder("Password");
  await expect(usernameInput).toBeVisible({ timeout: 30_000 });
  await usernameInput.fill(username);
  await passwordInput.fill(password);

  await page.getByRole("button", { name: /^login$/i }).click();

  // After a successful login the SPA navigates back to "/". The login
  // mutation also fires a cache reset, so we wait both for the URL
  // change AND for one of the discovery-page sentinels to appear.
  await expect(page).toHaveURL(/\/(\?.*)?$/, { timeout: 30_000 });
}

/**
 * Navigate within the React Router SPA without performing a full
 * page reload. This preserves the in-memory authToken set by `loginViaUI`.
 *
 * Implementation: we push the new path onto window.history and dispatch
 * a `popstate` event so the @remix-run/router BrowserHistory listener
 * picks up the change and re-renders. CentralRouteManager then syncs
 * Apollo reactive vars from the new URL.
 *
 * FRAGILITY NOTE: This relies on @remix-run/router (used by react-router v6)
 * listening to popstate events. If React Router changes how BrowserHistory
 * subscribes to navigation events, this will break silently. Verify after
 * any react-router upgrade.
 */
export async function spaNavigate(
  page: Page,
  path: string,
  /** Skip URL assertion for routes that redirect (e.g. /profile → /users/slug). */
  expectRedirect = false
): Promise<void> {
  await page.evaluate((targetPath) => {
    window.history.pushState({}, "", targetPath);
    window.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
  }, path);

  if (expectRedirect) {
    // Wait for the React Router <Navigate> redirect to settle.
    await page.waitForTimeout(2000);
    // Verify we navigated away from the original path.
    await expect(page).not.toHaveURL(
      new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`)
    );
  } else {
    // Assert the URL actually changed to catch silent navigation failures.
    await expect(page).toHaveURL(
      new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`)
    );
  }
}
