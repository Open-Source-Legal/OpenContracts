import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MobileSectionsSheetHarness } from "./MobileSectionsSheet.harness";

const SECTIONS = [
  { id: "sec-1", rawText: "Introduction", page: 0 },
  { id: "sec-2", rawText: "Terms and Conditions", page: 2 },
  { id: "sec-3", rawText: "Signatures", page: 7 },
];

test("shows the empty state when the document has no sections", async ({
  mount,
}) => {
  const c = await mount(<MobileSectionsSheetHarness open sections={[]} />);
  await expect(c).toHaveText("No sections detected in this document.");
});

test("renders a tappable row per structural annotation", async ({
  mount,
  page,
}) => {
  const c = await mount(
    <MobileSectionsSheetHarness open sections={SECTIONS} />
  );
  await expect(c.getByText("Introduction")).toBeVisible();
  await expect(c.getByText("Terms and Conditions")).toBeVisible();
  // Page badge is 1-indexed (page + 1).
  await expect(c.getByText("p.3")).toBeVisible();
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
