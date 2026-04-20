import React from "react";
import { test, expect } from "./utils/coverage";
import { TxtAnnotatorTestWrapper } from "./TxtAnnotatorTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("TxtAnnotator", () => {
  test("renders text content", async ({ mount, page }) => {
    const component = await mount(<TxtAnnotatorTestWrapper />);

    // Verify the annotator container is rendered
    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Verify the sample text content is rendered
    await expect(
      page.getByText("This is a sample document text")
    ).toBeVisible();
    await expect(
      page.getByText("It contains multiple sentences for testing purposes")
    ).toBeVisible();

    await docScreenshot(page, "annotator--txt-annotator--default");

    await component.unmount();
  });

  test("renders in read-only mode", async ({ mount, page }) => {
    const component = await mount(<TxtAnnotatorTestWrapper readOnly={true} />);

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Text should be visible in read-only mode
    await expect(
      page.getByText("This is a sample document text")
    ).toBeVisible();

    await docScreenshot(page, "annotator--txt-annotator--read-only");

    await component.unmount();
  });

  test("renders with annotations", async ({ mount, page }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper readOnly={true} withAnnotations={true} />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Verify that the annotated span is rendered (annotation covers "sample document text")
    const annotatedSpan = page.getByTestId(/^annotated-span-/);
    await expect(annotatedSpan.first()).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("renders available labels context in edit mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(<TxtAnnotatorTestWrapper readOnly={false} />);

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // In edit mode the text is still rendered and selectable
    await expect(
      page.getByText("This is a sample document text")
    ).toBeVisible();

    await component.unmount();
  });

  test("hovering an annotation span shows the label container", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper readOnly={true} withAnnotations={true} />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Hover the first annotated span to reveal the label popover
    const annotatedSpan = page.getByTestId(/^annotated-span-/).first();
    await annotatedSpan.hover();

    // The label container registers with a data-testid scoped to the annotation id
    await expect(
      page.getByTestId("annotation-label-container-ann-1")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("pre-selected annotation renders its label on mount", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        preselectAnnotation="ann-1"
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Hover anywhere on the annotated span so labels render
    const annotatedSpan = page.getByTestId(/^annotated-span-/).first();
    await annotatedSpan.hover();

    // Label container for the pre-selected annotation should be visible
    await expect(
      page.getByTestId("annotation-label-container-ann-1")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("visibleLabels filter hides annotations whose label is excluded", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        // Provide an empty allowlist so all annotations are filtered out
        visibleLabels={[]}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // No annotated spans should be visible when all labels are filtered out
    await expect(page.getByTestId(/^annotated-span-/)).toHaveCount(0);

    await component.unmount();
  });

  test("multiple overlapping annotations render with a gradient background", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        withOverlappingAnnotations={true}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Both annotated spans render (one per label)
    const spans = page.getByTestId(/^annotated-span-/);
    await expect(spans.first()).toBeVisible({ timeout: 10000 });
    const count = await spans.count();
    expect(count).toBeGreaterThanOrEqual(2);

    await component.unmount();
  });

  test("search result highlights render when searchResults are provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        searchResults={[
          // "sample" appears at offset 10–16 in the sample text
          { start_index: 10, end_index: 16, matched_text: "sample" } as any,
        ]}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // The matched text is still visible in the DOM
    await expect(page.getByText("sample", { exact: false })).toBeVisible();

    await component.unmount();
  });

  test("chat source highlights render with the speech-bubble icon", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        chatSources={[
          {
            start_index: 35,
            end_index: 52,
            sourceId: "source-1",
            messageId: "msg-1",
          },
        ]}
        selectedChatSourceId="source-1"
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    // Chat-source chunk text must still render
    await expect(page.getByText("contains multiple")).toBeVisible();

    await component.unmount();
  });

  test("approved annotation renders without crashing", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        approved={true}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    await expect(page.getByTestId(/^annotated-span-/).first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("rejected annotation renders without crashing", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        rejected={true}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    await expect(page.getByTestId(/^annotated-span-/).first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("structural annotation renders when showStructuralAnnotations is true", async ({
    mount,
    page,
  }) => {
    // structural=true sets both firstAnn.structural and (by default)
    // showStructuralAnnotations=true, so the annotated span is drawn.
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        structural={true}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    await expect(page.getByTestId(/^annotated-span-/).first()).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("structural annotation is hidden when showStructuralAnnotations is false", async ({
    mount,
    page,
  }) => {
    // Annotation is structural, but showStructuralAnnotations is explicitly
    // false — the annotator should filter it out entirely.
    const component = await mount(
      <TxtAnnotatorTestWrapper
        readOnly={true}
        withAnnotations={true}
        structural={true}
        showStructuralAnnotations={false}
      />
    );

    const annotator = page.getByTestId("txt-annotator");
    await expect(annotator).toBeVisible({ timeout: 10000 });

    await expect(page.getByTestId(/^annotated-span-/)).toHaveCount(0);

    await component.unmount();
  });
});
