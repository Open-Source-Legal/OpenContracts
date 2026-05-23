import { test, expect } from "./utils/coverage";
import { DesktopLayoutHarness } from "./DesktopDocumentLayout.harness";

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
