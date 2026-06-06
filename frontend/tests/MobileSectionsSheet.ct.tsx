import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MobileSectionsSheetHarness } from "./MobileSectionsSheet.harness";

const SECTIONS = [
  { id: "sec-1", rawText: "Introduction", page: 1 },
  { id: "sec-2", rawText: "Terms and Conditions", page: 3 },
  { id: "sec-3", rawText: "Signatures", page: 8 },
];

test("shows the empty state when the document has no sections", async ({
  mount,
}) => {
  const c = await mount(<MobileSectionsSheetHarness open sections={[]} />);
  await expect(c).toHaveText("No sections detected in this document.");
});

test("shows a distinct error state when the index fetch fails", async ({
  mount,
}) => {
  // A network failure must not masquerade as "no sections" — the user should
  // see that loading failed, not that the document has no index.
  const c = await mount(<MobileSectionsSheetHarness open error />);
  // The error Empty state is the component root, so assert on its text
  // directly (mirrors the no-sections empty-state test above).
  await expect(c).toHaveText("Failed to load sections.");
});

test("renders a tappable row per OC_SECTION index entry", async ({
  mount,
  page,
}) => {
  const c = await mount(
    <MobileSectionsSheetHarness open sections={SECTIONS} />
  );
  await expect(c.getByText("Introduction")).toBeVisible();
  await expect(c.getByText("Terms and Conditions")).toBeVisible();
  // Page is rendered verbatim from the index (same as the desktop tab,
  // including the "p. " spacing).
  await expect(c.getByText("p. 3")).toBeVisible();
  await docScreenshot(page, "mobile--sections-sheet--list");
});

test("tapping a row fires onNavigate with the annotation id", async ({
  mount,
}) => {
  let navigatedTo = "";
  const c = await mount(
    <MobileSectionsSheetHarness
      open
      sections={SECTIONS}
      onNavigate={(id) => {
        navigatedTo = id;
      }}
    />
  );
  await c.getByText("Terms and Conditions").click();
  expect(navigatedTo).toBe("sec-2");
});
