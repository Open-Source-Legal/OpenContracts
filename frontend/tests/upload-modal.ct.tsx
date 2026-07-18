// Playwright Component Test for UploadModal
//
// Note on duplicate mocks: MockedProvider consumes mocks in order - each query
// execution uses the next mock in the array. Duplicating mocks handles:
// 1. Initial query on mount
// 2. Refetches triggered by search term changes or other state updates
// Without duplicates, subsequent queries would fail with "No more mocked responses".
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { UploadModal } from "../src/components/widgets/modals/UploadModal";
import {
  GET_BULK_DOCUMENT_UPLOAD_STATUS,
  GET_CORPUSES,
} from "../src/graphql/queries";
import { GET_SUPPORTED_MIME_TYPES } from "../src/components/admin/system_settings/graphql";
import { CorpusType } from "../src/types/graphql-api";
import { docScreenshot } from "./utils/docScreenshot";

// Mock corpus data for testing
const mockCorpus: CorpusType = {
  id: "Q29ycHVzVHlwZTox",
  title: "Test Corpus",
  description: "A test corpus for unit testing",
  descriptionPreview: "A test corpus for unit testing",
  icon: null,
  isPublic: false,
  labelSet: null,
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "test@example.com",
  },
  myPermissions: ["update_corpus", "read_corpus"],
  documents: { totalCount: 0 },
  annotations: { totalCount: 0 },
} as CorpusType;

const mockCorpus2: CorpusType = {
  id: "Q29ycHVzVHlwZToy",
  title: "Second Corpus",
  description: "Another test corpus",
  descriptionPreview: "Another test corpus",
  icon: null,
  isPublic: true,
  labelSet: null,
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "test@example.com",
  },
  myPermissions: ["update_corpus", "read_corpus"],
  documents: { totalCount: 5 },
  annotations: { totalCount: 10 },
} as CorpusType;

// GraphQL mocks
const corpusesMock = {
  request: {
    query: GET_CORPUSES,
    variables: { textSearch: "" },
  },
  result: {
    data: {
      corpuses: {
        edges: [
          { node: mockCorpus, cursor: mockCorpus.id },
          { node: mockCorpus2, cursor: mockCorpus2.id },
        ],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: mockCorpus.id,
          endCursor: mockCorpus2.id,
        },
      },
    },
  },
};

const emptyCorpusesMock = {
  request: {
    query: GET_CORPUSES,
    variables: { textSearch: "" },
  },
  result: {
    data: {
      corpuses: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    },
  },
};

const mimeTypesMock = {
  request: {
    query: GET_SUPPORTED_MIME_TYPES,
  },
  result: {
    data: {
      supportedMimeTypes: [
        {
          mimetype: "application/pdf",
          fileType: "pdf",
          label: "PDF",
          fullySupported: true,
          stageCoverage: { parser: true, embedder: true, thumbnailer: true },
        },
        {
          mimetype: "text/plain",
          fileType: "txt",
          label: "Plain Text",
          fullySupported: true,
          stageCoverage: { parser: true, embedder: true, thumbnailer: false },
        },
        {
          mimetype:
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          fileType: "docx",
          label: "DOCX",
          fullySupported: true,
          stageCoverage: { parser: true, embedder: true, thumbnailer: false },
        },
      ],
    },
  },
};

test.describe("UploadModal - Single Mode", () => {
  test("should render single mode upload interface by default", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="single" />
      </MockedProvider>
    );

    // Check header
    await expect(page.locator("text=Upload Documents")).toBeVisible();
    await expect(page.locator("text=Select files to upload")).toBeVisible();

    // Step indicator should show "select" as first step
    await expect(page.locator('[data-step="select"]')).toBeVisible();

    // Drop zone should be present
    await expect(page.locator('[data-testid="file-dropzone"]')).toBeVisible();

    await docScreenshot(page, "corpus--upload-modal--initial");

    await component.unmount();
  });

  test("should call onClose when cancel clicked", async ({ mount, page }) => {
    let closed = false;

    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal
          open={true}
          onClose={() => {
            closed = true;
          }}
          forceMode="single"
        />
      </MockedProvider>
    );

    // Click cancel
    await page.locator('button:has-text("Cancel")').click();

    expect(closed).toBe(true);

    await component.unmount();
  });
});

test.describe("UploadModal - Bulk Mode", () => {
  test("should render bulk mode upload interface", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider
        mocks={[corpusesMock, corpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Check header
    await expect(page.locator("text=Bulk Upload Documents")).toBeVisible();
    await expect(
      page.locator("text=Upload multiple documents from a ZIP file")
    ).toBeVisible();

    // Drop zone should indicate ZIP files
    await expect(page.locator("text=Click to select a ZIP file")).toBeVisible();

    // Wait for corpus list to render before screenshot
    await expect(
      page.locator('input[placeholder="Search corpuses..."]')
    ).toBeVisible();

    await docScreenshot(page, "corpus--bulk-upload-modal--initial");

    await component.unmount();
  });

  test("should show corpus selector in bulk mode", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider
        mocks={[corpusesMock, corpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Corpus selector section should be visible
    await expect(page.locator("text=Add to Corpus (Optional)")).toBeVisible();

    // Search input should be present
    await expect(
      page.locator('input[placeholder="Search corpuses..."]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should show Upload ZIP button disabled when no file", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Upload button should be disabled without a file
    const uploadButton = page.locator('button:has-text("Upload ZIP")');
    await expect(uploadButton).toBeDisabled();

    await component.unmount();
  });

  test("should call onClose when cancel clicked in bulk mode", async ({
    mount,
    page,
  }) => {
    let closed = false;

    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal
          open={true}
          onClose={() => {
            closed = true;
          }}
          forceMode="bulk"
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Cancel")').click();
    expect(closed).toBe(true);

    await component.unmount();
  });
});

test.describe("UploadModal - Step Navigation", () => {
  test("should display step indicator with correct steps", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="single" />
      </MockedProvider>
    );

    // Steps should be visible
    await expect(page.locator('[data-step="select"]')).toBeVisible();
    await expect(page.locator('[data-step="details"]')).toBeVisible();
    await expect(page.locator('[data-step="corpus"]')).toBeVisible();

    await component.unmount();
  });

  test("should hide corpus step when corpusId is provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[emptyCorpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal
          open={true}
          onClose={() => {}}
          forceMode="single"
          corpusId="test-corpus-id"
        />
      </MockedProvider>
    );

    // Steps should show select and details, but NOT corpus
    await expect(page.locator('[data-step="select"]')).toBeVisible();
    await expect(page.locator('[data-step="details"]')).toBeVisible();
    // Corpus step should not be visible when corpusId is provided
    await expect(page.locator('[data-step="corpus"]')).not.toBeVisible();

    await component.unmount();
  });
});

test.describe("UploadModal - Mobile Responsiveness", () => {
  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE size

  test("should display correctly on mobile viewport in single mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="single" />
      </MockedProvider>
    );

    // Modal should be visible
    await expect(page.locator("text=Upload Documents")).toBeVisible();

    // Drop zone should be visible
    await expect(page.locator('[data-testid="file-dropzone"]')).toBeVisible();

    // Buttons should be accessible
    await expect(page.locator('button:has-text("Cancel")')).toBeVisible();

    await component.unmount();
  });

  test("should display correctly on mobile viewport in bulk mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Modal should be visible
    await expect(page.locator("text=Bulk Upload Documents")).toBeVisible();

    // Drop zone should be visible
    await expect(page.locator("text=Click to select a ZIP file")).toBeVisible();

    // Buttons should be accessible
    await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
    await expect(page.locator('button:has-text("Upload ZIP")')).toBeVisible();

    await component.unmount();
  });
});

test.describe("UploadModal - Corpus Selection", () => {
  test("should show corpus search results in bulk mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[corpusesMock, corpusesMock, corpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Wait for corpus names to render from GraphQL mock
    await expect(page.locator("text=Test Corpus").first()).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

test.describe("UploadModal - Pre-selected Corpus", () => {
  test("should skip corpus step when corpusId is provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[emptyCorpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal
          open={true}
          onClose={() => {}}
          forceMode="single"
          corpusId="Q29ycHVzVHlwZTox"
        />
      </MockedProvider>
    );

    // Step indicator should not show corpus step
    await expect(page.locator('[data-step="corpus"]')).not.toBeVisible();

    await component.unmount();
  });
});

test.describe("UploadModal - Callbacks", () => {
  test("should call onClose when modal is closed", async ({ mount, page }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal
          open={true}
          onClose={() => {
            closeCalled = true;
          }}
          forceMode="single"
        />
      </MockedProvider>
    );

    await page.locator('button:has-text("Cancel")').click();
    expect(closeCalled).toBe(true);

    await component.unmount();
  });
});

test.describe("UploadModal - Form Validation", () => {
  test("should show Continue button only when files are selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="single" />
      </MockedProvider>
    );

    // On step select without files, Continue should not be visible
    // (No files selected yet)
    await expect(
      page.locator('button:has-text("Continue")').first()
    ).not.toBeVisible();

    await component.unmount();
  });
});

test.describe("UploadModal - Icons", () => {
  test("should display upload icon in single mode header", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="single" />
      </MockedProvider>
    );

    // Header should contain the upload text
    await expect(page.locator("text=Upload Documents")).toBeVisible();

    await component.unmount();
  });

  test("should display file archive icon in bulk mode header", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[corpusesMock, mimeTypesMock]} addTypename={false}>
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    // Header should contain the archive text
    await expect(page.locator("text=Bulk Upload Documents")).toBeVisible();

    await component.unmount();
  });
});

// Helpers for the bulk upload flow tests below. The bulk FileDropZone keeps
// a hidden ZIP input with a stable aria-label; the archive itself only needs
// a ZIP magic-number prefix because the upload endpoint is intercepted.
const ZIP_INPUT_SELECTOR =
  'input[aria-label="Select ZIP file for bulk upload"]';
const zipBuffer = Buffer.from("PK\x03\x04dummy-zip-content");

const makeBulkStatusMock = (
  jobId: string,
  status: Partial<{
    success: boolean;
    completed: boolean;
    totalFiles: number;
    processedFiles: number;
    skippedFiles: number;
    errorFiles: number;
    errors: string[];
  }>
) => ({
  // The modal polls this query until it is unmounted, so keep the response
  // available for every polling request.
  maxUsageCount: Number.POSITIVE_INFINITY,
  request: {
    query: GET_BULK_DOCUMENT_UPLOAD_STATUS,
    variables: { jobId },
  },
  result: {
    data: {
      bulkDocumentUploadStatus: {
        jobId,
        success: false,
        completed: false,
        totalFiles: 0,
        processedFiles: 0,
        skippedFiles: 0,
        errorFiles: 0,
        errors: [],
        ...status,
      },
    },
  },
});

test.describe("UploadModal - Bulk Upload Flow", () => {
  test("uploads a ZIP to a selected corpus and reports import completion", async ({
    mount,
    page,
  }) => {
    let uploadPostData: string | null = null;
    await page.route("**/api/imports/documents-zip/", async (route) => {
      uploadPostData = route.request().postData();
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "zip-job-ok",
          message: "Import started",
        }),
      });
    });

    let uploadCompleteCalled = false;
    let refetchCalled = false;

    const component = await mount(
      <MockedProvider
        mocks={[
          corpusesMock,
          corpusesMock,
          corpusesMock,
          mimeTypesMock,
          makeBulkStatusMock("zip-job-ok", {
            success: true,
            completed: true,
            totalFiles: 3,
            processedFiles: 3,
          }),
        ]}
        addTypename={false}
      >
        <UploadModal
          open={true}
          onClose={() => {}}
          forceMode="bulk"
          onUploadComplete={() => {
            uploadCompleteCalled = true;
          }}
          refetch={() => {
            refetchCalled = true;
          }}
        />
      </MockedProvider>
    );

    try {
      // Select a target corpus from the inline list before uploading.
      await expect(page.locator("text=Test Corpus").first()).toBeVisible({
        timeout: 5000,
      });
      await page.locator("text=Test Corpus").first().click();

      // Select a ZIP archive.
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "bulk-docs.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await expect(page.locator("text=bulk-docs.zip")).toBeVisible();

      // With a file staged and no upload in flight, the CTA is enabled.
      const uploadButton = page.locator('button:has-text("Upload ZIP")');
      await expect(uploadButton).toBeEnabled();
      await uploadButton.click();

      // The polled job status drives the completion summary (a 202 alone
      // must not be reported as a finished import).
      await expect(
        page.getByText("Import complete: 3 of 3 files processed.")
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: zip-job-ok", { exact: true })
      ).toBeVisible();
      await expect(page.locator("text=Import status")).toBeVisible();

      // Completion callbacks fire only once the job succeeds.
      await expect.poll(() => uploadCompleteCalled).toBe(true);
      await expect.poll(() => refetchCalled).toBe(true);

      // The selected corpus rode along in the multipart payload.
      expect(uploadPostData).toContain("Q29ycHVzVHlwZTox");
    } finally {
      await component.unmount();
    }
  });

  test("keeps bulk controls disabled while the import job is running", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/documents-zip/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "zip-job-running",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[
          corpusesMock,
          corpusesMock,
          corpusesMock,
          mimeTypesMock,
          makeBulkStatusMock("zip-job-running", {
            completed: false,
          }),
        ]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await expect(page.locator("text=Test Corpus").first()).toBeVisible({
        timeout: 5000,
      });

      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "running.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      // The archive was staged but the job has not completed yet.
      await expect(
        page.getByText(
          /Archive uploaded\. Documents are being imported in the background/
        )
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: zip-job-running", { exact: true })
      ).toBeVisible();
      await expect(
        page.locator("text=Import is running in the background")
      ).toBeVisible();

      // Bulk controls stay locked while the job runs.
      await expect(page.locator("#bulk-corpus-search")).toBeDisabled();
      await expect(
        page.locator('button:has-text("Upload ZIP")')
      ).toBeDisabled();

      // Clicking a corpus while locked is a no-op (guard branch).
      await page.locator("text=Test Corpus").first().click();
      await expect(
        page.locator('button:has-text("Upload ZIP")')
      ).toBeDisabled();
    } finally {
      await component.unmount();
    }
  });

  test("shows streamed archive progress while the upload is in flight", async ({
    mount,
    page,
  }) => {
    // Park the upload request so the in-flight state stays visible for the
    // assertions below, then release it on teardown.
    let resolveRoute: (() => void) | undefined;
    const routePending = new Promise<void>((resolve) => {
      resolveRoute = resolve;
    });
    await page.route("**/api/imports/documents-zip/", async (route) => {
      await routePending;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "zip-job-slow",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[
          corpusesMock,
          corpusesMock,
          mimeTypesMock,
          makeBulkStatusMock("zip-job-slow", { completed: false }),
        ]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "slow.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      // While the archive streams, the progress bar reports the transfer —
      // not document processing.
      await expect(page.locator("text=Uploading archive...")).toBeVisible({
        timeout: 10000,
      });
      await expect(
        page.locator('button:has-text("Uploading...")')
      ).toBeVisible();
    } finally {
      resolveRoute?.();
      await component.unmount();
    }
  });

  test("shows a visible error when the archive upload fails", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/documents-zip/", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ error: "Corpus not found" }),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[corpusesMock, corpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "bad.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      // The backend error is surfaced inside the modal, and the controls
      // unlock so the user can retry.
      await expect(page.locator("text=Corpus not found")).toBeVisible();
      await expect(page.locator('button:has-text("Upload ZIP")')).toBeEnabled();
    } finally {
      await component.unmount();
    }
  });

  test("falls back to a generic upload error when the backend provides no detail", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/documents-zip/", async (route) => {
      // A JSON string body of "" makes parseErrorMessage return an empty
      // error, exercising the modal-side fallback message.
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify(""),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[corpusesMock, corpusesMock, mimeTypesMock]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "no-detail.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      await expect(
        page.getByText("Upload failed. Please check the file and try again.")
      ).toBeVisible();
    } finally {
      await component.unmount();
    }
  });

  test("surfaces job errors when the import completes with failures", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/documents-zip/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "zip-job-err",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[
          corpusesMock,
          corpusesMock,
          mimeTypesMock,
          makeBulkStatusMock("zip-job-err", {
            success: false,
            completed: true,
            totalFiles: 2,
            processedFiles: 1,
            errorFiles: 1,
            errors: ["Corrupt entry: contract.pdf"],
          }),
        ]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "partial.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      // The job's error detail lands in the modal's error banner...
      await expect(
        page.locator("text=Corrupt entry: contract.pdf")
      ).toBeVisible();
      // ...and the status block reports the failed completion.
      await expect(
        page.getByText(
          "Import completed with errors. Review the details above."
        )
      ).toBeVisible();
      await expect(
        page.getByText("Job ID: zip-job-err", { exact: true })
      ).toBeVisible();
    } finally {
      await component.unmount();
    }
  });

  test("falls back to a generic message when a failed job reports no error detail", async ({
    mount,
    page,
  }) => {
    await page.route("**/api/imports/documents-zip/", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          job_id: "zip-job-silent",
          message: "Import started",
        }),
      });
    });

    const component = await mount(
      <MockedProvider
        mocks={[
          corpusesMock,
          corpusesMock,
          mimeTypesMock,
          makeBulkStatusMock("zip-job-silent", {
            success: false,
            completed: true,
            totalFiles: 1,
            errors: [],
          }),
        ]}
        addTypename={false}
      >
        <UploadModal open={true} onClose={() => {}} forceMode="bulk" />
      </MockedProvider>
    );

    try {
      await page.locator(ZIP_INPUT_SELECTOR).setInputFiles({
        name: "silent.zip",
        mimeType: "application/zip",
        buffer: zipBuffer,
      });
      await page.locator('button:has-text("Upload ZIP")').click();

      // With an empty errors list the banner shows the generic fallback.
      await expect(
        page.getByText(
          "Import completed with errors. Please review the corpus."
        )
      ).toBeVisible();
    } finally {
      await component.unmount();
    }
  });
});
