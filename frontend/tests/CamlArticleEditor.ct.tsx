/**
 * Playwright component tests for the CamlArticleEditor.
 *
 * Tests cover:
 * 1. New article mode (template loaded, "Create Article" button)
 * 2. Editor pane with CAML source
 * 3. Preview pane with rendered output
 * 4. Unsaved changes indicator
 * 5. Extract picker keyboard navigation (Arrow keys, Home/End, Escape, Enter)
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { CamlArticleEditorTestWrapper } from "./CamlArticleEditorTestWrapper";

test.describe("CamlArticleEditor - New Article", () => {
  test("should render editor with template for new article", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    // Modal header should be visible ("Create Article" appears in header + save button)
    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Editor pane should have CAML source header
    await expect(page.getByText("CAML Source")).toBeVisible();

    // Preview pane should show rendered content
    await expect(page.getByText("Preview")).toBeVisible();

    // Template content should be in the editor textarea
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible();
    const value = await textarea.inputValue();
    expect(value).toContain("hero:");
    expect(value).toContain("version:");

    await docScreenshot(page, "caml--editor--new-article");

    await component.unmount();
  });
});

test.describe("CamlArticleEditor - Live Preview", () => {
  test("should update preview when editor content changes", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    // Wait for editor to load
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible({ timeout: 10000 });

    // Clear and type new CAML content (simple structure — no YAML list for title)
    await textarea.fill(`::: chapter {#test}
## Test Chapter

Hello from the preview!
:::`);

    // Wait for preview to update
    await page.waitForTimeout(500);

    // Preview should show the rendered chapter heading
    await expect(
      page.getByRole("heading", { name: "Test Chapter" })
    ).toBeVisible({ timeout: 5000 });

    // Should show unsaved changes badge
    await expect(page.getByText("Unsaved changes")).toBeVisible();

    await docScreenshot(page, "caml--editor--live-preview");

    await component.unmount();
  });
});

test.describe("CamlArticleEditor - Close Behavior", () => {
  test("should show close button", async ({ mount, page }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    // Close button should be present in action bar
    const closeButton = page.locator("button").filter({ hasText: "Close" });
    await expect(closeButton).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("mobile modal should cover app nav and stay inside viewport", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
      const nav = document.createElement("div");
      nav.id = "mobile-nav-z-index-regression";
      Object.assign(nav.style, {
        position: "fixed",
        top: "0",
        left: "0",
        right: "0",
        height: "60px",
        zIndex: "1100",
      });
      document.body.appendChild(nav);
    });

    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    const overlay = page.locator(".caml-article-editor-overlay");
    const modal = page.locator(".caml-article-editor-modal");
    await expect(overlay).toBeVisible();
    await expect(modal).toBeVisible();
    await page.waitForTimeout(100);

    const overlayZIndex = await overlay.evaluate((el) =>
      Number(window.getComputedStyle(el).zIndex)
    );
    expect(overlayZIndex).toBeGreaterThan(1100);

    const viewport = page.viewportSize()!;
    const modalBox = await modal.boundingBox();
    expect(modalBox).not.toBeNull();
    expect(modalBox!.x).toBeGreaterThanOrEqual(-2);
    expect(modalBox!.y).toBeGreaterThanOrEqual(-2);
    expect(modalBox!.width).toBeLessThanOrEqual(viewport.width + 2);
    expect(modalBox!.height).toBeLessThanOrEqual(viewport.height + 2);

    await component.unmount();
  });
});

test.describe("CamlArticleEditor - Extract Picker Keyboard Navigation", () => {
  test("should open picker and navigate with arrow keys", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    // Wait for editor to load
    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Click the "Insert Extract Grid" button to open the picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await expect(triggerBtn).toBeVisible({ timeout: 5000 });
    await triggerBtn.click();

    // Dropdown should appear with extract options
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Contract Key Terms")).toBeVisible();
    await expect(page.getByText("Compliance Tracker")).toBeVisible();
    await expect(page.getByText("Risk Assessment")).toBeVisible();

    // ArrowDown should highlight the first item. The active option is
    // tracked on the combobox trigger via aria-activedescendant (the
    // ARIA-correct mechanism for a pick-to-execute listbox), not via
    // aria-selected on the options themselves — aria-selected is reserved
    // for the actually-selected option in a stateful listbox, which this
    // dropdown doesn't have.
    await page.keyboard.press("ArrowDown");
    const firstOption = page.locator('[role="option"]').first();
    const firstOptionId = await firstOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      firstOptionId ?? ""
    );

    // ArrowDown again should move to second item
    await page.keyboard.press("ArrowDown");
    const secondOption = page.locator('[role="option"]').nth(1);
    const secondOptionId = await secondOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      secondOptionId ?? ""
    );

    // ArrowUp should go back to first item
    await page.keyboard.press("ArrowUp");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      firstOptionId ?? ""
    );

    await component.unmount();
  });

  test("should wrap around at list boundaries", async ({ mount, page }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Open picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // ArrowUp from initial state (-1) should wrap to the last item
    await page.keyboard.press("ArrowUp");
    const lastOption = page.locator('[role="option"]').last();
    const lastOptionId = await lastOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      lastOptionId ?? ""
    );

    // ArrowDown from last item should wrap to first
    await page.keyboard.press("ArrowDown");
    const firstOption = page.locator('[role="option"]').first();
    const firstOptionId = await firstOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      firstOptionId ?? ""
    );

    await component.unmount();
  });

  test("should close picker with Escape and return focus to trigger", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Open picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // Press Escape
    await page.keyboard.press("Escape");

    // Dropdown should close
    await expect(page.getByRole("listbox")).not.toBeVisible({ timeout: 3000 });

    // Focus should return to the trigger button
    await expect(triggerBtn).toBeFocused();

    await component.unmount();
  });

  test("should use Home and End keys to jump to boundaries", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Open picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // End should jump to last option
    await page.keyboard.press("End");
    const lastOption = page.locator('[role="option"]').last();
    const lastOptionId = await lastOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      lastOptionId ?? ""
    );

    // Home should jump to first option
    await page.keyboard.press("Home");
    const firstOption = page.locator('[role="option"]').first();
    const firstOptionId = await firstOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      firstOptionId ?? ""
    );

    await component.unmount();
  });

  test("should not insert when Enter is pressed with no item focused", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Capture initial textarea content
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible({ timeout: 5000 });
    const initialValue = await textarea.inputValue();

    // Open picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // Press Enter WITHOUT navigating to any item (activeExtractIndex is -1).
    // This should NOT insert anything — the Enter guard checks that
    // activeExtractIndex is a valid index before acting.
    await page.keyboard.press("Enter");

    // Give time for any potential state changes
    await page.waitForTimeout(300);

    // Textarea content should be unchanged
    const afterValue = await textarea.inputValue();
    expect(afterValue).toBe(initialValue);

    await component.unmount();
  });

  test("ArrowDown then Enter inserts the extract-grid component marker", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible({ timeout: 5000 });
    const initialValue = await textarea.inputValue();

    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // Navigate to the first option and select it via keyboard.
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    // The textarea should now contain a [component:extract-grid ...] token.
    await expect(textarea).not.toHaveValue(initialValue, { timeout: 5000 });
    const afterValue = await textarea.inputValue();
    expect(afterValue).toContain("[component:extract-grid");

    // Picker should close after Enter selection.
    await expect(page.getByRole("listbox")).not.toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("should highlight item on mouse enter for seamless keyboard/mouse interaction", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // Open picker
    const triggerBtn = page.getByRole("combobox", {
      name: "Insert extract grid table",
    });
    await triggerBtn.click();
    await expect(page.getByRole("listbox")).toBeVisible({ timeout: 5000 });

    // Hover over the second option to trigger onMouseEnter
    const secondOption = page.locator('[role="option"]').nth(1);
    await secondOption.hover();

    // The second option should become the activedescendant via onMouseEnter
    // (the combobox's aria-activedescendant now points at the hovered
    // option's id — this is the ARIA mechanism for a pick-to-execute
    // listbox; aria-selected is reserved for actually-selected options).
    const secondOptionId = await secondOption.getAttribute("id");
    await expect(triggerBtn).toHaveAttribute(
      "aria-activedescendant",
      secondOptionId ?? "",
      { timeout: 3000 }
    );

    await component.unmount();
  });
});

test.describe("CamlArticleEditor - New Block Types in Template", () => {
  test("should render map and case-history blocks in preview from template", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlArticleEditorTestWrapper hasExistingArticle={false} />
    );

    // Wait for editor to load
    await expect(page.getByText("Create Article").first()).toBeVisible({
      timeout: 10000,
    });

    // The textarea should contain the new block types
    const textarea = page.locator("textarea");
    const value = await textarea.inputValue();
    expect(value).toContain("case-history");
    expect(value).toContain("map {type: us}");

    // Preview pane should render these blocks
    // Case history title - use testId to avoid matching the raw textarea content
    await expect(page.getByTestId("case-history-title")).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "caml--editor--full-template", {
      fullPage: true,
    });

    await component.unmount();
  });
});
