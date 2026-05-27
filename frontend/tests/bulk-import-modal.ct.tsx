// Playwright Component Test for BulkImportModal
//
// Tests the bulk ZIP import modal styling and step navigation.
// Uses docScreenshot to capture the visual state of each step.
//
// The modal posts directly to ``POST /api/imports/zip-to-corpus/`` via
// ``fetch``; the progress test stubs ``window.fetch`` so the upload
// resolves without an actual network request. (Previously this used an
// Apollo MockedProvider mock for the now-removed ``IMPORT_ZIP_TO_CORPUS``
// GraphQL mutation.)
import React from "react";
import { test, expect } from "./utils/coverage";
import { BulkImportModal } from "../src/components/widgets/modals/BulkImportModal";
import { BulkImportTestWrapper } from "./wrappers/BulkImportTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("BulkImportModal", () => {
  test("should render confirm step with warning and info alerts", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    // Check header
    await expect(page.locator("text=Bulk Import Documents")).toBeVisible();
    await expect(
      page.locator("text=Review import details before proceeding")
    ).toBeVisible();

    // Step indicator should show all three steps
    await expect(page.locator("text=Confirm")).toBeVisible();
    await expect(page.locator("text=Select File")).toBeVisible();
    await expect(page.getByText("Import", { exact: true })).toBeVisible();

    // Warning alert should be visible
    await expect(
      page.locator("text=Important: Bulk Import Cannot Be Easily Undone")
    ).toBeVisible();

    // Info alert should be visible
    await expect(page.locator("text=Supported Format")).toBeVisible();

    // Footer buttons
    await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
    await expect(page.locator('button:has-text("Continue")')).toBeVisible();

    await docScreenshot(page, "corpus--bulk-import-modal--confirm-step");

    await component.unmount();
  });

  test("should navigate to upload step when Continue is clicked", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    // Wait for confirm step to be visible
    await expect(
      page.locator("text=Important: Bulk Import Cannot Be Easily Undone")
    ).toBeVisible();

    // Click Continue
    await page.locator('button:has-text("Continue")').click();

    // Should now show upload step
    await expect(
      page.locator("text=Drag & drop a ZIP file here")
    ).toBeVisible();
    await expect(page.locator('button:has-text("Browse Files")')).toBeVisible();

    // Footer should show Back and Start Import
    await expect(page.locator('button:has-text("Back")')).toBeVisible();
    await expect(page.locator('button:has-text("Start Import")')).toBeVisible();

    await docScreenshot(page, "corpus--bulk-import-modal--upload-step");

    await component.unmount();
  });

  test("should navigate back from upload to confirm step", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    // Go to upload step
    await page.locator('button:has-text("Continue")').click();
    await expect(
      page.locator("text=Drag & drop a ZIP file here")
    ).toBeVisible();

    // Click Back
    await page.locator('button:has-text("Back")').click();

    // Should be back on confirm step
    await expect(
      page.locator("text=Important: Bulk Import Cannot Be Easily Undone")
    ).toBeVisible();

    await component.unmount();
  });

  test("should have Start Import button disabled when no file is selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    // Navigate to upload step
    await page.locator('button:has-text("Continue")').click();
    await expect(
      page.locator("text=Drag & drop a ZIP file here")
    ).toBeVisible();

    // Start Import should be disabled when no file is selected
    const startImportButton = page.locator('button:has-text("Start Import")');
    await expect(startImportButton).toBeVisible();
    await expect(startImportButton).toBeDisabled();

    await component.unmount();
  });

  test("should enable Start Import after file selection and show file info", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    // Navigate to upload step
    await page.locator('button:has-text("Continue")').click();
    await expect(
      page.locator("text=Drag & drop a ZIP file here")
    ).toBeVisible();

    // Programmatically set a file via the hidden input to simulate selection
    const fileInput = page.locator('input[type="file"][accept=".zip"]');
    const zipBuffer = Buffer.from("PK\x03\x04dummy-zip-content");
    await fileInput.setInputFiles({
      name: "test-documents.zip",
      mimeType: "application/zip",
      buffer: zipBuffer,
    });

    // File should now be shown in the drop zone
    await expect(page.locator("text=test-documents.zip")).toBeVisible();

    // "Choose Different File" button should appear
    await expect(
      page.locator('button:has-text("Choose Different File")')
    ).toBeVisible();

    // Start Import should now be enabled
    const startImportButton = page.locator('button:has-text("Start Import")');
    await expect(startImportButton).toBeEnabled();

    await docScreenshot(page, "corpus--bulk-import-modal--file-selected");

    await component.unmount();
  });

  test("should show progress step with spinner and progress bar during import", async ({
    mount,
    page,
  }) => {
    // Intercept the multipart upload to /api/imports/zip-to-corpus/ at the
    // network layer so the progress UI has time to render. We delay the
    // fulfilment well past the test's 30s timeout window — the test only
    // needs to observe the in-flight state, not the success state.
    let resolveRoute: (() => void) | undefined;
    const routePending = new Promise<void>((resolve) => {
      resolveRoute = resolve;
    });
    await page.route("**/api/imports/zip-to-corpus/", async (route) => {
      // Park the request until the test releases it on teardown so the
      // progress step stays visible for every assertion below.
      await routePending;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "test-job-123",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <BulkImportTestWrapper>
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    const zipBuffer = Buffer.from("PK\x03\x04dummy-zip-content");

    // Navigate to upload step
    await page.locator('button:has-text("Continue")').click();
    await expect(
      page.locator("text=Drag & drop a ZIP file here")
    ).toBeVisible();

    // Select a file
    const fileInput = page.locator('input[type="file"][accept=".zip"]');
    await fileInput.setInputFiles({
      name: "progress-test.zip",
      mimeType: "application/zip",
      buffer: zipBuffer,
    });
    await expect(page.locator("text=progress-test.zip")).toBeVisible();

    // Click Start Import to trigger the progress step
    await page.locator('button:has-text("Start Import")').click();

    // Progress step should show spinner, heading, and progress bar
    await expect(page.locator("text=Importing Documents...")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator("text=This may take a few moments")
    ).toBeVisible();

    // Progress percentage should be visible
    await expect(page.locator("text=%")).toBeVisible();

    // Close button should be hidden during progress
    await expect(page.locator('button:has-text("Cancel")')).not.toBeVisible();
    await expect(page.locator('button:has-text("Back")')).not.toBeVisible();

    await docScreenshot(page, "corpus--bulk-import-modal--progress-step");

    // Release the parked request so unmount doesn't deadlock cleanup.
    resolveRoute?.();
    await component.unmount();
  });
});
