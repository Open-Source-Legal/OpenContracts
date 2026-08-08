/**
 * Component tests for the Markdown document body.
 *
 * The behaviour that matters: a markdown document is *rendered* by default
 * rather than shown as its own source, and the escape hatch to the source is
 * present and discoverable. Markdown is a ``text/…`` subtype, so the routing
 * assertion below is the real regression guard — reorder the filetype checks
 * and every saved answer silently goes back to displaying `# Heading`.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
// Split-import rule (CLAUDE.md pitfall #16): mounted components get their own
// import statement, apart from helper/constant imports.
import { MarkdownDocumentViewerTestWrapper } from "./MarkdownDocumentViewerTestWrapper";
import { DocumentViewerTestWrapper } from "./DocumentViewerTestWrapper";
import { ViewState } from "../src/components/types";

const SAMPLE = [
  "# ERCOT July 10 vs July 11, 2026 transition",
  "",
  "- **Corpus:** ERCOT Current Large-Load Rules",
  "- **Saved from chat:** 2026-07-27",
  "",
  "---",
  "",
  "The legacy LLIS process applied through July 10.",
].join("\n");

test.describe("MarkdownDocumentViewer", () => {
  test("renders the markdown instead of showing its source", async ({
    mount,
    page,
  }) => {
    await mount(<MarkdownDocumentViewerTestWrapper docText={SAMPLE} />);

    await expect(page.getByTestId("markdown-rendered-surface")).toBeVisible({
      timeout: 20000,
    });

    // The heading text is present as a real heading...
    await expect(
      page.getByRole("heading", {
        name: "ERCOT July 10 vs July 11, 2026 transition",
      })
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("The legacy LLIS process")).toBeVisible();

    // ...and the markdown source markers are gone.
    const body = await page.textContent("body");
    expect(body).not.toContain("# ERCOT July 10");
    expect(body).not.toContain("**Corpus:**");
  });

  test("defaults to rendered and offers a raw view", async ({
    mount,
    page,
  }) => {
    await mount(<MarkdownDocumentViewerTestWrapper docText={SAMPLE} />);

    const rendered = page.getByTestId("markdown-view-rendered");
    const raw = page.getByTestId("markdown-view-raw");

    await expect(rendered).toBeVisible({ timeout: 20000 });
    await expect(raw).toBeVisible();
    // Reading is the common case, so rendered is the default.
    await expect(rendered).toHaveAttribute("aria-pressed", "true");
    await expect(raw).toHaveAttribute("aria-pressed", "false");
  });

  test("says where annotations are made when the user may edit", async ({
    mount,
    page,
  }) => {
    await mount(
      <MarkdownDocumentViewerTestWrapper docText={SAMPLE} canEdit={true} />
    );

    // Raw is not an arbitrary alternative view — span annotations need
    // character offsets into the source, so the affordance explains itself.
    await expect(page.getByTestId("markdown-view-raw")).toHaveAttribute(
      "title",
      /annotations are made here/
    );
  });

  test("handles a document with no text without crashing", async ({
    mount,
    page,
  }) => {
    await mount(<MarkdownDocumentViewerTestWrapper docText="" />);

    await expect(page.getByText("no text content")).toBeVisible({
      timeout: 20000,
    });
  });
});

test.describe("DocumentViewer filetype routing", () => {
  test("routes text/markdown to the markdown viewer, not the text branch", async ({
    mount,
    page,
  }) => {
    await mount(
      <DocumentViewerTestWrapper
        fileType="text/markdown"
        viewState={ViewState.LOADED}
      />
    );

    // Markdown is a text/… subtype: if isTextFileType is tested first this
    // mounts the plain-text annotator and the document renders as source.
    await expect(page.getByTestId("markdown-document-viewer")).toBeVisible({
      timeout: 20000,
    });
  });
});
