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
import { GET_BULK_DOCUMENT_UPLOAD_STATUS } from "../src/graphql/queries";

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

    // While the HTTP request is pending, the archive has not yet been accepted
    // and the modal should clearly distinguish upload from background import.
    await expect(
      page.getByRole("heading", { name: "Uploading Archive..." })
    ).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText(
        "The archive is being transferred and staged for import.",
        {
          exact: true,
        }
      )
    ).toBeVisible();

    // Progress percentage should be visible
    await expect(page.getByText(/% uploaded$/)).toBeVisible();

    // Close button should be hidden during progress
    await expect(page.locator('button:has-text("Cancel")')).not.toBeVisible();
    await expect(page.locator('button:has-text("Back")')).not.toBeVisible();

    await docScreenshot(page, "corpus--bulk-import-modal--progress-step");

    // Release the parked request so unmount doesn't deadlock cleanup.
    resolveRoute?.();
    await component.unmount();
  });

  test("keeps the modal open while the accepted import job is running", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/zip-to-corpus/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "test-job-queued",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <BulkImportTestWrapper
        mocks={[
          {
            // The modal polls this query until it is unmounted, so keep the
            // queued response available for every polling request.
            maxUsageCount: Number.POSITIVE_INFINITY,
            request: {
              query: GET_BULK_DOCUMENT_UPLOAD_STATUS,
              variables: { jobId: "test-job-queued" },
            },
            result: {
              data: {
                bulkDocumentUploadStatus: {
                  jobId: "test-job-queued",
                  success: false,
                  completed: false,
                  totalFiles: 0,
                  processedFiles: 0,
                  skippedFiles: 0,
                  errorFiles: 0,
                  errors: ["Task is still running"],
                },
              },
            },
          },
        ]}
      >
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    try {
      await page.locator('button:has-text("Continue")').click();
      const fileInput = page.locator('input[type="file"][accept=".zip"]');
      await fileInput.setInputFiles({
        name: "queued.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("PK\x03\x04dummy-zip-content"),
      });
      await page.locator('button:has-text("Start Import")').click();

      await expect(
        page.getByText(
          /The archive was uploaded\. Documents are being processed/i
        )
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: test-job-queued", { exact: true })
      ).toBeVisible();
      await expect(page.locator('button:has-text("Close")')).toBeVisible();
      await expect(page.locator("text=Bulk Import Documents")).toBeVisible();
    } finally {
      // Stop polling even when an assertion fails, so the mock is not reused
      // by a still-mounted component during test cleanup or retries.
      await component.unmount();
    }
  });

  test("shows the completion summary once the import job succeeds and closes cleanly", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/zip-to-corpus/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "test-job-done",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <BulkImportTestWrapper
        mocks={[
          {
            maxUsageCount: Number.POSITIVE_INFINITY,
            request: {
              query: GET_BULK_DOCUMENT_UPLOAD_STATUS,
              variables: { jobId: "test-job-done" },
            },
            result: {
              data: {
                bulkDocumentUploadStatus: {
                  jobId: "test-job-done",
                  success: true,
                  completed: true,
                  totalFiles: 5,
                  processedFiles: 3,
                  skippedFiles: 2,
                  errorFiles: 0,
                  errors: [],
                },
              },
            },
          },
        ]}
      >
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    try {
      await page.locator('button:has-text("Continue")').click();
      const fileInput = page.locator('input[type="file"][accept=".zip"]');
      await fileInput.setInputFiles({
        name: "done.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("PK\x03\x04dummy-zip-content"),
      });
      await page.locator('button:has-text("Start Import")').click();

      // Completion summary reflects the polled task result, including the
      // skipped-file count.
      await expect(
        page.getByRole("heading", { name: "Import Complete" })
      ).toBeVisible();
      await expect(
        page.getByText("Processed 3 of 5 files; skipped 2.")
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: test-job-done", { exact: true })
      ).toBeVisible();
      await expect(page.locator("text=Import status")).toBeVisible();

      // Close resets all state (including the completed job id) and hides
      // the modal.
      await page.locator('button:has-text("Close")').click();
      await expect(
        page.locator("text=Bulk Import Documents")
      ).not.toBeVisible();
    } finally {
      await component.unmount();
    }
  });

  test("surfaces job errors when the import job completes with failures", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/zip-to-corpus/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "test-job-failed",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <BulkImportTestWrapper
        mocks={[
          {
            maxUsageCount: Number.POSITIVE_INFINITY,
            request: {
              query: GET_BULK_DOCUMENT_UPLOAD_STATUS,
              variables: { jobId: "test-job-failed" },
            },
            result: {
              data: {
                bulkDocumentUploadStatus: {
                  jobId: "test-job-failed",
                  success: false,
                  completed: true,
                  totalFiles: 4,
                  processedFiles: 1,
                  skippedFiles: 0,
                  errorFiles: 3,
                  errors: ["Unsupported file type: notes.exe"],
                },
              },
            },
          },
        ]}
      >
        <BulkImportModal />
      </BulkImportTestWrapper>
    );

    try {
      await page.locator('button:has-text("Continue")').click();
      const fileInput = page.locator('input[type="file"][accept=".zip"]');
      await fileInput.setInputFiles({
        name: "failed.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("PK\x03\x04dummy-zip-content"),
      });
      await page.locator('button:has-text("Start Import")').click();

      await expect(
        page.getByRole("heading", { name: "Import Completed with Errors" })
      ).toBeVisible();
      await expect(
        page.getByText("Processed 1 of 4 files; 3 failed.")
      ).toBeVisible();
      // The per-file error detail from the job is surfaced in the modal.
      await expect(page.locator("text=Import details")).toBeVisible();
      await expect(
        page.locator("text=Unsupported file type: notes.exe")
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: test-job-failed", { exact: true })
      ).toBeVisible();
    } finally {
      await component.unmount();
    }
  });
});
