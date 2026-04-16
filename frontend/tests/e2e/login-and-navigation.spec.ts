/**
 * End-to-end integration test: password login + base navigation.
 *
 * This spec exercises the full Vite + Django + Postgres stack. It is the
 * counterpart to the component tests under `frontend/tests/*.ct.tsx` —
 * those test individual components in isolation; this spec verifies that
 *
 *   1. The login form authenticates against a real backend.
 *   2. Every routed view in `src/views/` mounts and renders its top-level
 *      hero/header copy on a freshly migrated database with NO data.
 *
 * The test runs with `COVERAGE=true` in CI so that vite-plugin-istanbul
 * instruments the source. Each test's `__coverage__` is dumped to
 * `coverage/e2e/.nyc_output/` by the fixture in `./fixtures.ts` and later
 * merged into an lcov report uploaded to Codecov by the workflow in
 * `.github/workflows/frontend-e2e.yml`.
 *
 * Why a single integration spec rather than per-view files?
 *   - Spinning up the docker stack + vite is expensive; running every
 *     route in one Playwright session amortises that cost.
 *   - The navigation walk via `spaNavigate` keeps the in-memory authToken
 *     alive across routes, which a per-test login would have to repeat.
 */

import { test, expect } from "./fixtures";
import {
  VIEWS,
  TEST_USER,
  loginViaUI,
  spaNavigate,
  expectViewVisible,
} from "./helpers";

test.describe("Frontend integration", () => {
  /* ─────────────────────────────────────────────────────────────────────
   * Anonymous coverage pass.
   *
   * Hits every public view via a real `page.goto` (full reload). This is
   * the simplest possible smoke test — no auth, no SPA tricks — and it
   * is also the highest-value coverage contribution because every route
   * triggers a fresh mount of `App.tsx`, `AuthGate`, `CentralRouteManager`,
   * the `NavMenu`, and the view component.
   * ────────────────────────────────────────────────────────────────── */
  test.describe("anonymous user", () => {
    for (const view of VIEWS.filter((v) => !v.requiresAuth)) {
      test(`renders ${view.name} (${view.path})`, async ({ page }) => {
        // Note: Playwright does not fail on console errors by default.
        // Many views log GraphQL "could not fetch X" warnings when the
        // database has no data — this is expected. The only failure
        // signal we care about is the view itself never rendering.
        await page.goto(view.path);
        await expectViewVisible(page, view.matcher);
      });
    }

    test("renders the Login form", async ({ page }) => {
      await page.goto("/login");
      // The form renders three controls: username, password, submit.
      await expect(page.getByPlaceholder("Username")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByPlaceholder("Password")).toBeVisible();
      await expect(
        page.getByRole("button", { name: /^login$/i })
      ).toBeVisible();
    });

    test("rejects invalid credentials without crashing", async ({ page }) => {
      await page.goto("/login");
      await page.getByPlaceholder("Username").fill("not-a-real-user");
      await page.getByPlaceholder("Password").fill("not-a-real-password");
      await page.getByRole("button", { name: /^login$/i }).click();

      // The Login view shows a toast "ERROR! Could not log you in!" when
      // the GraphQL mutation returns an error. Wait for the form to be
      // re-enabled (submit button clickable) as the stable signal that
      // the failed mutation has completed, then verify we stayed on /login.
      await expect(page.getByRole("button", { name: /^login$/i })).toBeEnabled({
        timeout: 10_000,
      });
      await expect(page).toHaveURL(/\/login(\?.*)?$/);
    });
  });

  /* ─────────────────────────────────────────────────────────────────────
   * Authenticated walk.
   *
   * One serial test that:
   *   1. Logs in via the UI.
   *   2. SPA-navigates to every view in VIEWS in order.
   *
   * SPA navigation (history.pushState + popstate dispatch) preserves the
   * in-memory `authToken` set by the Login component's onCompleted
   * handler. A `page.goto` would tear down the React tree and lose it.
   * ────────────────────────────────────────────────────────────────── */
  test.describe("authenticated user", () => {
    test("logs in via password and walks every view", async ({ page }) => {
      await loginViaUI(page, TEST_USER.username, TEST_USER.password);

      // Verify we have an authenticated session by checking that the
      // discover landing page shows one of its sentinels.
      const landing = VIEWS.find((v) => v.path === "/")!;
      await expectViewVisible(page, landing.matcher);

      for (const view of VIEWS) {
        if (view.path === "/") continue; // already verified above
        await test.step(`navigate to ${view.name}`, async () => {
          await spaNavigate(page, view.path, view.redirects);
          await expectViewVisible(page, view.matcher);
        });
      }
    });
  });
});
