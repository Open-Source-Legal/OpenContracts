import { test, expect } from "./utils/coverage";
import { DesktopLayoutHarness } from "./DesktopDocumentLayout.harness";
// Helper import lives in its own statement — CT's babel transform only
// rewrites component identifiers when every specifier in the statement is
// a JSX component (see CLAUDE.md "Playwright CT split-import rule").
import { buildSummaryVersionsMock } from "./DesktopDocumentLayout.harness";

test.use({ viewport: { width: 1280, height: 800 } });

// DesktopDocumentLayout pins two consolidation efforts:
//   - issue #1735 (DocumentBottomBar): the three previously-floating bottom
//     controls dock into a single anchored bar.
//   - issue #1734 (RightEdgeRail): the two right-edge control systems
//     (navigation tabs + document tool FABs) merge into one rail when the
//     right panel is closed.
// These CT tests pin both branches and exercise the inline callback bodies.

test("renders the consolidated DocumentBottomBar with all three slots", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness />);

  await expect(page.getByTestId("document-bottom-bar")).toBeVisible();
  // Summary toggle (left slot), search/chat input (centre slot), and the
  // EnhancedLabelSelector (right slot) all live inside the bar.
  await expect(page.getByTestId("summary-toggle-button")).toBeVisible();
});

test("submitting the chat input fires onChatSubmit + onToggleChat callbacks", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness />);

  await expect(page.getByTestId("document-bottom-bar")).toBeVisible();

  // Open the input (search icon toggle) then flip to chat mode.
  await page.getByTestId("search-toggle-button").click();
  await page.getByTestId("chat-toggle-button").click();

  // Type a question and press Enter — handleChatSubmit calls
  // onChatSubmit?.(text) and onToggleChat?.() which fire the layout's
  // inline callback bodies (setPendingChatMessage / setSidebarViewMode /
  // setShowRightPanel).
  const textarea = page.getByPlaceholder("Ask a question...");
  await expect(textarea).toBeVisible();
  await textarea.fill("hello world");
  await textarea.press("Enter");

  // The harness probe surfaces the layout-state writes.
  const probe = page.getByTestId("harness-probe");
  await expect(probe).toHaveAttribute(
    "data-pending-chat-message",
    "hello world"
  );
  await expect(probe).toHaveAttribute("data-show-right-panel", "true");
  await expect(probe).toHaveAttribute("data-sidebar-view-mode", "chat");
});

test("expanding then full-viewing the summary fires onSwitchToKnowledge", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness />);

  // Tap the collapsed summary button — expands the preview.
  await page.getByTestId("summary-toggle-button").click();

  // The expanded view has a "Full View" button (title="View Full Screen")
  // whose onClick fires onSwitchToKnowledge.
  await page.getByTitle("View Full Screen").click();

  // The layout's onSwitchToKnowledge callback flips activeLayer to
  // "knowledge", closes the right panel, and clears the summary
  // content selection.
  const probe = page.getByTestId("harness-probe");
  await expect(probe).toHaveAttribute("data-active-layer", "knowledge");
  await expect(probe).toHaveAttribute("data-show-right-panel", "false");
});

test("FloatingSummaryPreview is hidden when no corpus is present", async ({
  mount,
  page,
}) => {
  await mount(<DesktopLayoutHarness corpusId="" />);

  // The DocumentBottomBar still renders the three slots, but the left
  // slot is empty (FloatingSummaryPreview is corpus-gated).
  await expect(page.getByTestId("document-bottom-bar")).toBeVisible();
  await expect(page.getByTestId("summary-toggle-button")).toHaveCount(0);
});

test("back-to-document button fires onBackToDocument callback in knowledge layer", async ({
  mount,
  page,
}) => {
  // Mount in the knowledge layer — FloatingSummaryPreview renders its
  // BackButton variant when `isInKnowledgeLayer && isVisible`. Clicking
  // it fires onBackToDocument, exercising the layout's inline body
  // (setActiveLayer → "document", clear summary content, show right
  // panel, set sidebar mode → "chat").
  await mount(<DesktopLayoutHarness activeLayer="knowledge" />);

  const backButton = page.getByTestId("back-to-document-button");
  await expect(backButton).toBeVisible();
  await backButton.click();

  const probe = page.getByTestId("harness-probe");
  await expect(probe).toHaveAttribute("data-active-layer", "document");
  await expect(probe).toHaveAttribute("data-show-right-panel", "true");
  await expect(probe).toHaveAttribute("data-sidebar-view-mode", "chat");
  // After back-to-document, selectedSummaryContent is cleared back to null
  // (rendered as empty string by the probe).
  await expect(probe).toHaveAttribute("data-selected-summary-content", "");
});

test("selecting a version with content fires onSwitchToKnowledge with content arg", async ({
  mount,
  page,
}) => {
  // With a populated version stack, clicking the active (top) version
  // card calls onSwitchToKnowledge(currentContent || "") — with the mock
  // supplying `summaryContent`, the arg is non-empty and the layout
  // exercises the `if (content)` true branch (setSelectedSummaryContent
  // with the version text) rather than the else branch (set null).
  await mount(
    <DesktopLayoutHarness
      mocks={[buildSummaryVersionsMock("doc-1", "corpus-1")]}
    />
  );

  // Expand the summary preview so the version stack is rendered.
  await page.getByTestId("summary-toggle-button").click();

  // The current version card (v2 per the mock's `currentSummaryVersion`)
  // is the top/active card and the only one clickable when not fanned.
  // Its click handler fires handleVersionClick(2) → since
  // version === currentVersion, onSwitchToKnowledge(currentContent || "")
  // is called with the mock's "Current summary content." string.
  const currentVersionCard = page.getByTestId("summary-card-2");
  await expect(currentVersionCard).toBeVisible();
  await currentVersionCard.click();

  const probe = page.getByTestId("harness-probe");
  await expect(probe).toHaveAttribute("data-active-layer", "knowledge");
  await expect(probe).toHaveAttribute(
    "data-selected-summary-content",
    "Current summary content."
  );
  await expect(probe).toHaveAttribute("data-show-right-panel", "false");
});

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
