import { test, expect } from "./utils/coverage";
import { DesktopLayoutHarness } from "./DesktopDocumentLayout.harness";

test.use({ viewport: { width: 1280, height: 800 } });

// DesktopDocumentLayout renders the unified RightEdgeRail (issue #1734) when
// the right panel is closed. These CT tests pin that branch (and the
// panel-open variant where the rail is absent) and exercise the inline
// action-button callbacks for both corpus-present and corpus-absent paths,
// so the new right-edge consolidation logic stays under coverage.

test("renders the unified right-edge rail when the panel is closed", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={false} />);

  // The RightEdgeRail wrapper sits at the viewport's right edge with the
  // navigation tabs above the document tool buttons.
  await expect(page.getByTestId("right-edge-rail")).toBeVisible();
  await expect(page.getByTestId("view-mode-index")).toBeVisible();
  await expect(page.getByTestId("view-mode-chat")).toBeVisible();
  await expect(page.getByTestId("view-mode-feed")).toBeVisible();
  await expect(page.getByTestId("view-mode-discussions")).toBeVisible();
});

test("hides the right-edge rail when the panel is open", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={true} />);

  // When the panel is open the rail isn't rendered — the sidebar tabs
  // anchor to the panel's left edge inside SlidingPanel instead, and the
  // floating controls keep their own bottom-right placement.
  await expect(page.getByTestId("right-edge-rail")).toHaveCount(0);
});

test("clicking the analyses button in the rail opens the FloatingAnalysesPanel when a corpus is present", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={false} />);

  await expect(page.getByTestId("right-edge-rail")).toBeVisible();
  await page.getByTestId("analyses-button").click();

  // The panel uses "Document Analyses" as its title.
  await expect(page.getByText("Document Analyses")).toBeVisible();
});

test("clicking the extracts button in the rail opens the FloatingExtractsPanel when a corpus is present", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={false} />);

  await expect(page.getByTestId("right-edge-rail")).toBeVisible();
  await page.getByTestId("extracts-button").click();

  // The extracts panel uses "Document Extracts" as its title.
  await expect(page.getByText("Document Extracts")).toBeVisible();
});

test("clicking the analyses button in the rail opens the add-to-corpus modal when no corpus is set", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={false} corpusId="" />);

  await expect(page.getByTestId("right-edge-rail")).toBeVisible();
  await page.getByTestId("analyses-button").click();

  // Without a corpus, the layout fires toast.info() and opens the
  // AddToCorpusModal instead of toggling the analyses panel.
  await expect(page.getByTestId("add-to-corpus-modal")).toBeVisible();
});

test("clicking the extracts button in the rail opens the add-to-corpus modal when no corpus is set", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness showRightPanel={false} corpusId="" />);

  await expect(page.getByTestId("right-edge-rail")).toBeVisible();
  await page.getByTestId("extracts-button").click();

  await expect(page.getByTestId("add-to-corpus-modal")).toBeVisible();
});

test("clicking the analyses button while the panel is open uses the open-panel callback branch", async ({
  mount,
  page,
}) => {
  // sidebarViewMode="feed" so the open-panel FloatingDocumentControls keeps
  // its document-tool FABs visible (they're hidden when the chat tray is on
  // top of the same controls).
  await mount(
    <DesktopLayoutHarness showRightPanel={true} sidebarViewMode="feed" />
  );

  // When the panel is open the action buttons render in their bottom-right
  // FAB cluster (not the rail). Clicking still toggles the analyses panel.
  await expect(page.getByTestId("right-edge-rail")).toHaveCount(0);
  await page.getByTestId("analyses-button").click();
  await expect(page.getByText("Document Analyses")).toBeVisible();
});

test("clicking the extracts button while the panel is open with no corpus opens the add-to-corpus modal", async ({
  mount,
  page,
}) => {
  await mount(
    <DesktopLayoutHarness
      showRightPanel={true}
      corpusId=""
      sidebarViewMode="feed"
    />
  );

  await expect(page.getByTestId("right-edge-rail")).toHaveCount(0);
  await page.getByTestId("extracts-button").click();
  await expect(page.getByTestId("add-to-corpus-modal")).toBeVisible();
});
