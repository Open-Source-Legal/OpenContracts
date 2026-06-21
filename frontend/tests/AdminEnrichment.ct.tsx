/**
 * Component tests for the AdminEnrichment page shell.
 *
 * Covers the three top-level branches of AdminEnrichment that the
 * EnrichmentRunner suite (which mounts the inner panel directly) never reaches:
 *   - currentUser === null → renders nothing (auth not yet resolved)
 *   - non-superuser → "Access Denied" warning
 *   - superuser → full shell (back link, title, corpus picker) + back nav
 *
 * Each JSX-component import is in its own import statement (Playwright CT
 * split-import rule, CLAUDE.md #16).
 */
import { test, expect } from "./utils/coverage";

import { AdminEnrichmentWrapper } from "./AdminEnrichmentWrapper";

import { GET_CORPUSES } from "../src/graphql/queries";

// CorpusDropdown fires GET_CORPUSES with {} on mount, then refetches with
// {textSearch: ""} from its search effect. Mock both so the superuser shell
// renders without an unmatched-mock error. maxUsageCount guards re-renders.
const CORPUSES_RESULT = { data: { corpuses: { edges: [] } } };
const CORPUSES_MOCKS = [
  {
    request: { query: GET_CORPUSES, variables: {} },
    result: CORPUSES_RESULT,
    maxUsageCount: 10,
  },
  {
    request: { query: GET_CORPUSES, variables: { textSearch: "" } },
    result: CORPUSES_RESULT,
    maxUsageCount: 10,
  },
];

test.describe("AdminEnrichment", () => {
  test("renders nothing until the current user resolves", async ({
    mount,
    page,
  }) => {
    const component = await mount(<AdminEnrichmentWrapper user={null} />);
    // Neither the page shell nor the access-denied warning should appear.
    await expect(page.locator('[data-testid="admin-enrichment"]')).toHaveCount(
      0
    );
    await expect(page.getByText("Access Denied")).toHaveCount(0);
    await component.unmount();
  });

  test("shows Access Denied to a non-superuser", async ({ mount, page }) => {
    const component = await mount(
      <AdminEnrichmentWrapper user={{ isSuperuser: false }} />
    );
    await expect(page.getByText("Access Denied")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Only administrators can access the enrichment runner.")
    ).toBeVisible();
    // The runner shell must NOT render for a non-superuser.
    await expect(page.locator('[data-testid="admin-enrichment"]')).toHaveCount(
      0
    );
    await component.unmount();
  });

  test("renders the full shell for a superuser and supports back nav", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <AdminEnrichmentWrapper
        user={{ isSuperuser: true }}
        mocks={CORPUSES_MOCKS}
      />
    );

    const shell = page.locator('[data-testid="admin-enrichment"]');
    await expect(shell).toBeVisible({ timeout: 10000 });
    await expect(shell).toContainText("Enrichment Runner");
    await expect(shell).toContainText(
      "Select a corpus to run reference-enrichment"
    );
    await expect(shell).toContainText("Corpus");

    // Clicking the back link invokes navigate("/admin/settings"). The page is
    // mounted directly (not inside <Routes>), so navigation is a visual no-op
    // here — the click still exercises the BackLink onClick handler without
    // throwing, and the shell remains mounted.
    await page.getByText("Back to Admin Settings").click();
    await expect(shell).toBeVisible();

    await component.unmount();
  });
});
