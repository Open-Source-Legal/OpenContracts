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
