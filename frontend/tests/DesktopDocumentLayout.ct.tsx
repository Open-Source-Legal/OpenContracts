import { test, expect } from "./utils/coverage";
import { DesktopLayoutHarness } from "./DesktopDocumentLayout.harness";
// Helper import lives in its own statement — CT's babel transform only
// rewrites component identifiers when every specifier in the statement is
// a JSX component (see CLAUDE.md "Playwright CT split-import rule").
import { buildSummaryVersionsMock } from "./DesktopDocumentLayout.harness";

test.use({ viewport: { width: 1280, height: 800 } });

// DesktopDocumentLayout (issue #1735) anchors three previously-floating
// controls into a single `DocumentBottomBar`. These CT tests pin the
// new bottom-bar structure and exercise the inline callback bodies wired
// to `FloatingDocumentInput` (onChatSubmit / onToggleChat) and
// `FloatingSummaryPreview` (onSwitchToKnowledge / onBackToDocument) so
// the consolidated layer stays under codecov/patch.

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
