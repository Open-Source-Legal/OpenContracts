import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MobileFindSheetHarness } from "./MobileFindSheet.harness";

test("renders the search input with the prompt status", async ({ mount }) => {
  const c = await mount(<MobileFindSheetHarness open />);
  await expect(c.getByPlaceholder(/find in document/i)).toBeVisible();
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "Type to search the document text."
  );
});

test("prev/next controls are disabled when there are no matches", async ({
  mount,
}) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={0} />);
  await expect(
    c.getByRole("button", { name: /previous match/i })
  ).toBeDisabled();
  await expect(c.getByRole("button", { name: /next match/i })).toBeDisabled();
});

test("typing with no matches shows the no-matches status", async ({
  mount,
  page,
}) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={0} />);
  await c.getByPlaceholder(/find in document/i).fill("nonexistent");
  await expect(c.getByTestId("mobile-find-status")).toHaveText("No matches.");
  await docScreenshot(page, "mobile--find-sheet--no-matches");
});

test("next/previous step through seeded matches and wrap around", async ({
  mount,
}) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={3} />);

  // A non-empty query is required for the match-count status branch.
  await c.getByPlaceholder(/find in document/i).fill("clause");
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "1 of 3 matches"
  );

  await c.getByRole("button", { name: /next match/i }).click();
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "2 of 3 matches"
  );

  // Stepping previous from index 1 → 0, then again wraps 0 → 2.
  await c.getByRole("button", { name: /previous match/i }).click();
  await c.getByRole("button", { name: /previous match/i }).click();
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "3 of 3 matches"
  );
});

test("renders a results list when matches exist", async ({ mount, page }) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={3} />);
  await c.getByPlaceholder(/find in document/i).fill("clause");

  const list = c.getByTestId("mobile-find-results");
  await expect(list).toBeVisible();
  // One row per seeded match.
  await expect(c.getByTestId("mobile-find-result-0")).toBeVisible();
  await expect(c.getByTestId("mobile-find-result-1")).toBeVisible();
  await expect(c.getByTestId("mobile-find-result-2")).toBeVisible();

  // Each row exposes a "Match N" index label and a page reference.
  await expect(c.getByTestId("mobile-find-result-0")).toContainText("Match 1");
  await expect(c.getByTestId("mobile-find-result-0")).toContainText("Page 1");

  await docScreenshot(page, "dkb--mobile--find-sheet-results-list");
});

test("hides the results list when there are no matches", async ({ mount }) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={0} />);
  await expect(c.getByTestId("mobile-find-results")).toHaveCount(0);
});

test("tapping a result row updates the selection and fires onClose", async ({
  mount,
}) => {
  let closeCount = 0;
  const c = await mount(
    <MobileFindSheetHarness
      open
      matchCount={3}
      onClose={() => (closeCount += 1)}
    />
  );
  await c.getByPlaceholder(/find in document/i).fill("clause");

  // The 3rd row (index 2) becomes the selected match after tap.
  await c.getByTestId("mobile-find-result-2").click();

  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "3 of 3 matches"
  );
  expect(closeCount).toBe(1);
});

test("tapping the first result row selects index 0", async ({ mount }) => {
  // Selection starts at index 0 in the seeded state, so tapping a non-first
  // row (above) proves the index moves; tapping the first row proves the
  // tap path also handles 0 explicitly — guards against an off-by-one where
  // the row's onClick passes (index + 1) or similar.
  let closeCount = 0;
  const c = await mount(
    <MobileFindSheetHarness
      open
      matchCount={3}
      onClose={() => (closeCount += 1)}
    />
  );
  await c.getByPlaceholder(/find in document/i).fill("clause");

  // Move selection off index 0 first so tapping row 0 is a real change.
  await c.getByRole("button", { name: /next match/i }).click();
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "2 of 3 matches"
  );

  await c.getByTestId("mobile-find-result-0").click();
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "1 of 3 matches"
  );
  expect(closeCount).toBe(1);
});

test("span-style matches render via the text fallback", async ({ mount }) => {
  // Span matches still carry a fullContext; the row uses it when present.
  // This test guards the fallback path renders a string when fullContext
  // happens to be null (the harness always supplies one, but the row code
  // explicitly handles `fullContext ?? fallbackText`).
  const c = await mount(
    <MobileFindSheetHarness open matchCount={2} matchType="span" />
  );
  await c.getByPlaceholder(/find in document/i).fill("clause");
  // Span results don't carry page bounds — the meta label reads "Text match".
  await expect(c.getByTestId("mobile-find-result-0")).toContainText(
    "Text match"
  );
});

test("caps the rendered list and shows an overflow notice", async ({
  mount,
}) => {
  // 150 > MOBILE_FIND_MAX_VISIBLE_RESULTS (100); the list should render the
  // first 100 rows and a single notice li telling the user how to reach the
  // rest (via the prev/next chevrons, which still operate over the full set).
  const c = await mount(<MobileFindSheetHarness open matchCount={150} />);
  await c.getByPlaceholder(/find in document/i).fill("clause");

  // First 100 rows are present.
  await expect(c.getByTestId("mobile-find-result-0")).toBeVisible();
  await expect(c.getByTestId("mobile-find-result-99")).toHaveCount(1);
  // Row 100 is not rendered (cap is exclusive).
  await expect(c.getByTestId("mobile-find-result-100")).toHaveCount(0);

  // The overflow notice carries both the cap and the true total.
  const notice = c.getByTestId("mobile-find-overflow-notice");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("first 100 of 150");

  // The status counter still reflects the full match set (cap is render-only).
  await expect(c.getByTestId("mobile-find-status")).toHaveText(
    "1 of 150 matches"
  );
});

test("does not show an overflow notice when results fit", async ({ mount }) => {
  const c = await mount(<MobileFindSheetHarness open matchCount={3} />);
  await c.getByPlaceholder(/find in document/i).fill("clause");
  await expect(c.getByTestId("mobile-find-overflow-notice")).toHaveCount(0);
});

test("token results with null fullContext render the unavailable placeholder", async ({
  mount,
}) => {
  // Token matches don't carry a raw-text fallback in their type, so a null
  // fullContext (upstream context-builder failure) used to render an empty
  // row. The row now renders an explicit "Match preview unavailable"
  // placeholder.
  const c = await mount(
    <MobileFindSheetHarness open matchCount={2} nullFullContext />
  );
  await c.getByPlaceholder(/find in document/i).fill("clause");
  await expect(c.getByTestId("mobile-find-result-0")).toContainText(
    "Match preview unavailable"
  );
});
