import React from "react";
import { test, expect } from "./utils/coverage";
import { DocumentViewerTestWrapper } from "./DocumentViewerTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { ViewState } from "../src/components/types";

test.describe("DocumentViewer (smoke)", () => {
  test("renders unsupported-file empty state for unknown filetypes", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentViewerTestWrapper
        fileType="application/x-foobar"
        viewState={ViewState.LOADED}
      />
    );

    await expect(page.getByText("Unsupported File")).toBeVisible();
    await expect(
      page.getByText("This document type can't be displayed.")
    ).toBeVisible();

    await docScreenshot(
      page,
      "knowledge-base--document-viewer--unsupported-file"
    );

    await component.unmount();
  });

  test("renders generic loading state for unknown filetype while loading", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <DocumentViewerTestWrapper
        fileType="application/x-foobar"
        viewState={ViewState.LOADING}
      />
    );

    await expect(page.getByText("Loading Document...")).toBeVisible();

    await docScreenshot(
      page,
      "knowledge-base--document-viewer--unsupported-loading"
    );

    await component.unmount();
  });
});
