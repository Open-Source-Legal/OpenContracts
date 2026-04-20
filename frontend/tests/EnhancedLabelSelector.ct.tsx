import React from "react";
import { test, expect } from "./utils/coverage";
import { EnhancedLabelSelectorTestWrapper } from "./EnhancedLabelSelectorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { LabelType } from "../src/types/graphql-api";

test.describe("EnhancedLabelSelector", () => {
  test("renders collapsed selector with tag icon", async ({ mount, page }) => {
    const component = await mount(<EnhancedLabelSelectorTestWrapper />);

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });

    // The collapsed toggle button should be visible
    const toggle = page.getByTestId("label-selector-toggle-button");
    await expect(toggle).toBeVisible();

    await docScreenshot(page, "annotator--enhanced-label-selector--collapsed");

    await component.unmount();
  });

  test("expands on hover and lists annotation labels", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnhancedLabelSelectorTestWrapper />);

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });

    // Hover to expand (desktop viewport = hover-driven)
    await selector.hover();

    const dropdown = page.getByTestId("label-selector-dropdown");
    await expect(dropdown).toBeVisible({ timeout: 5_000 });

    // All three span labels should render
    await expect(page.getByText("Important Clause")).toBeVisible();
    await expect(page.getByText("Definition")).toBeVisible();
    await expect(page.getByText("Risk")).toBeVisible();

    // Document Labels section present (corpus has docTypeLabels)
    await expect(page.getByText("Document Labels")).toBeVisible();
    await expect(page.getByText("Contract")).toBeVisible();

    await docScreenshot(page, "annotator--enhanced-label-selector--expanded");

    await component.unmount();
  });

  test("filters labels by search term (case-insensitive)", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnhancedLabelSelectorTestWrapper />);

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    const searchInput = page.getByPlaceholder("Search or create label...");
    await expect(searchInput).toBeVisible();

    await searchInput.fill("defi");

    // Only "Definition" should still be visible in the annotation section
    await expect(page.getByText("Definition")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Risk$/ })).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /^Important Clause$/ })
    ).toHaveCount(0);

    await component.unmount();
  });

  test("shows create-new-label button when search has no matches", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnhancedLabelSelectorTestWrapper />);

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    await page
      .getByPlaceholder("Search or create label...")
      .fill("zzz-no-match");

    // The create-button should appear offering to make the new label
    await expect(page.getByText(/^Create "zzz-no-match"$/)).toBeVisible();

    await component.unmount();
  });

  test("clicking a label selects it and shows active-label pill", async ({
    mount,
    page,
  }) => {
    const component = await mount(<EnhancedLabelSelectorTestWrapper />);

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    // Wait for dropdown content and click "Risk"
    await page.getByRole("button", { name: /^Risk$/ }).click();

    // The harness exposes the active label via data attribute for assertions
    const display = page.getByTestId("active-label-display");
    await expect(display).toHaveAttribute("data-active-id", "label-risk", {
      timeout: 5_000,
    });

    // Active label should show in the pill (inside the toggle button)
    await expect(
      page.getByTestId("label-selector-toggle-button").getByText("Risk")
    ).toBeVisible();

    await component.unmount();
  });

  test("clear-button (×) removes the active label", async ({ mount, page }) => {
    const component = await mount(
      <EnhancedLabelSelectorTestWrapper
        activeLabel={{
          id: "label-definition",
          text: "Definition",
          color: "#4ECDC4",
          labelType: LabelType.SpanLabel,
        }}
      />
    );

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });

    // Active label visible → confirm via harness
    const display = page.getByTestId("active-label-display");
    await expect(display).toHaveAttribute("data-active-id", "label-definition");

    // Click the clear (×) button inside the active-label-display
    await selector.locator(".clear-button").click();

    await expect(display).toHaveAttribute("data-active-id", "", {
      timeout: 5_000,
    });

    await component.unmount();
  });

  test("read-only mode shows lock icon and disables interactions", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnhancedLabelSelectorTestWrapper readOnly={true} />
    );

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await expect(selector).toHaveAttribute(
      "title",
      "Annotation tools are disabled in read-only mode"
    );

    // Hover should NOT expand the dropdown
    await selector.hover();
    await expect(page.getByTestId("label-selector-dropdown")).toHaveCount(0);

    await docScreenshot(page, "annotator--enhanced-label-selector--read-only");

    await component.unmount();
  });

  test("no-labelset state shows warning with create-one link", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnhancedLabelSelectorTestWrapper withLabelset={false} />
    );

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    await expect(page.getByText("No labelset configured")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create one" })
    ).toBeVisible();

    // Labels sections should be hidden when no labelset
    await expect(page.getByText("Annotation Labels")).toHaveCount(0);

    await component.unmount();
  });

  test("filters out doc-type labels already applied to the document", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EnhancedLabelSelectorTestWrapper withExistingDocTypeAnnotation={true} />
    );

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    // "Contract" is already applied so it should be excluded from choices
    await expect(page.getByText("Document Labels")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Contract$/ })).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("`labels` prop overrides corpus-provided label choices", async ({
    mount,
    page,
  }) => {
    const custom = [
      {
        id: "custom-1",
        text: "Custom Label A",
        color: "#123456",
        labelType: LabelType.SpanLabel,
      },
      {
        id: "custom-2",
        text: "Custom Label B",
        color: "#abcdef",
        labelType: LabelType.SpanLabel,
      },
    ];

    const component = await mount(
      <EnhancedLabelSelectorTestWrapper labelsProp={custom as any} />
    );

    const selector = page.getByTestId("annotation-tools");
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.hover();

    await expect(page.getByText("Custom Label A")).toBeVisible();
    await expect(page.getByText("Custom Label B")).toBeVisible();

    // Corpus labels should NOT appear
    await expect(
      page.getByRole("button", { name: /^Important Clause$/ })
    ).toHaveCount(0);

    await component.unmount();
  });
});
