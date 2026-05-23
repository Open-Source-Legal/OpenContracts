import { test, expect } from "./utils/coverage";
import { DesktopLayoutHarness } from "./DesktopDocumentLayout.harness";

test.use({ viewport: { width: 1280, height: 800 } });

// DesktopDocumentLayout renders the unified RightEdgeRail (issue #1734) when
// the right panel is closed. These CT tests pin that branch (and the
// panel-open variant where the rail is absent) so the rail's introduction
// stays under coverage.

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
