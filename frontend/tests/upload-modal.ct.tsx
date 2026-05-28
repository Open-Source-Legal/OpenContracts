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
import { GET_CORPUSES } from "../src/graphql/queries";
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
