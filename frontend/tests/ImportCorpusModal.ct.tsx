// Playwright Component Test for ImportCorpusModal
// Verifies the multi-step import flow and screenshots key states.
// Mount happens in the browser, so the reactive-var seed lives in the wrapper.
import React from "react";
import {
  ImportCorpusModalHiddenWrapper,
  ImportCorpusModalVisibleWrapper,
} from "./ImportCorpusModalTestWrapper";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ImportCorpusModal", () => {
  test("renders confirm step with import warnings when visible", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ImportCorpusModalVisibleWrapper />);

    await expect(page.getByText("Import Corpus")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByText("Importing creates a new corpus")
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();

    await docScreenshot(page, "corpus--import-modal--confirm-step");

    await component.unmount();
  });

  test("does not render when reactive var is false", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ImportCorpusModalHiddenWrapper />);

    await expect(page.getByText("Import Corpus")).not.toBeVisible();

    await component.unmount();
  });

  test("advances to upload step after Continue", async ({ mount, page }) => {
    const component = await mount(<ImportCorpusModalVisibleWrapper />);

    await page.getByRole("button", { name: "Continue" }).click();

    await expect(
      page.getByText("Drag & drop a corpus export ZIP here")
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Start Import/ })
    ).toBeDisabled();

    await docScreenshot(page, "corpus--import-modal--upload-step");

    await component.unmount();
  });

  test("rejects non-zip uploads with a clear error", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ImportCorpusModalVisibleWrapper />);

    await page.getByRole("button", { name: "Continue" }).click();

    await page.locator('input[type="file"]').setInputFiles({
      name: "not-a-zip.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hello"),
    });

    await expect(page.getByText("Please select a ZIP file.")).toBeVisible();

    await component.unmount();
  });

  test("accepts a valid ZIP and enables Start Import", async ({
    mount,
    page,
  }) => {
    const component = await mount(<ImportCorpusModalVisibleWrapper />);

    await page.getByRole("button", { name: "Continue" }).click();

    await page.locator('input[type="file"]').setInputFiles({
      name: "tiny.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK" + "\0".repeat(18)),
    });

    await expect(page.getByText("tiny.zip")).toBeVisible({ timeout: 5000 });
    await expect(
      page.getByRole("button", { name: /Start Import/ })
    ).toBeEnabled();

    await component.unmount();
  });
});
