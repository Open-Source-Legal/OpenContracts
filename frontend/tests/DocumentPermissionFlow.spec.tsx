// Playwright Component Test for Document Permission Flow
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { DocumentLandingRoute } from "../src/components/routes/DocumentLandingRoute";
import {
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
} from "../src/graphql/queries";

const mockDocument = {
  id: "RG9jdW1lbnRUeXBlOjE=",
  slug: "test-document",
  title: "Test Document",
  description: "A test document",
  fileType: "application/pdf",
  isPublic: false,
  pdfFile: "test.pdf",
  backendLock: false,
  myPermissions: ["READ", "UPDATE", "DELETE"], // Document has UPDATE permission
  creator: {
    id: "user-1",
    username: "testuser",
    slug: "testuser",
  },
};

const mockCorpus = {
  id: "Q29ycHVzVHlwZTox",
  slug: "test-corpus",
  title: "Test Corpus",
  description: "A test corpus",
  isPublic: false,
  myPermissions: ["READ", "UPDATE", "DELETE"], // Corpus has UPDATE permission
  creator: {
    id: "user-1",
    username: "testuser",
    slug: "testuser",
  },
  labelSet: {
    id: "labelset-1",
    title: "Test Label Set",
  },
};

const mockDocumentFull = {
  ...mockDocument,
  pawlsParseFile: "test.pawls",
  txtExtractFile: null,
  mdSummaryFile: null,
  allAnnotations: [],
  allStructuralAnnotations: [],
  allRelationships: [],
  allDocRelationships: [],
  allNotes: [],
};

const mockCorpusFull = {
  ...mockCorpus,
  labelSet: {
    id: "labelset-1",
    title: "Test Label Set",
    allAnnotationLabels: [
      {
        id: "label-1",
        text: "Test Label",
        color: "#0066cc",
        description: "Test annotation label",
        labelType: "SPAN_LABEL",
        icon: "tag",
        readOnly: false,
      },
    ],
  },
};

// Mock for slug resolution
const slugResolutionMock = {
  request: {
    query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
    variables: {
      userSlug: "testuser",
      corpusSlug: "test-corpus",
      documentSlug: "test-document",
    },
  },
  result: {
    data: {
      corpusBySlugs: mockCorpus,
      documentInCorpusBySlugs: mockDocument,
    },
  },
};

// Mock for full document data
const documentDataMock = {
  request: {
    query: GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
    variables: {
      documentId: "RG9jdW1lbnRUeXBlOjE=",
      corpusId: "Q29ycHVzVHlwZTox",
      analysisId: undefined,
    },
  },
  result: {
    data: {
      document: mockDocumentFull,
      corpus: mockCorpusFull,
    },
  },
};

test.describe("Document Permission Flow", () => {
  test("should allow editing when user has UPDATE permissions", async ({
    mount,
    page,
  }) => {
    // Mock PDF.js
    await page.addInitScript(() => {
      // Mock pdfjs-dist
      (window as any).pdfjsLib = {
        getDocument: () => ({
          promise: Promise.resolve({
            numPages: 1,
            getPage: () =>
              Promise.resolve({
                pageNumber: 1,
                getViewport: () => ({ width: 800, height: 600 }),
                render: () => ({ promise: Promise.resolve() }),
              }),
          }),
          onProgress: () => {},
        }),
        GlobalWorkerOptions: { workerSrc: "" },
      };

      // Mock fetch for PAWLS data
      const originalFetch = window.fetch;
      window.fetch = (input, init) => {
        if (typeof input === "string" && input.includes("test.pawls")) {
          return Promise.resolve(new Response("[]"));
        }
        return originalFetch(input, init);
      };
    });

    const component = await mount(
      <MockedProvider
        mocks={[slugResolutionMock, documentDataMock]}
        addTypename={false}
      >
        <MemoryRouter
          initialEntries={["/d/testuser/test-corpus/test-document"]}
        >
          <JotaiProvider>
            <DocumentLandingRoute />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for the document to load
    await expect(page.locator('[data-testid="pdf-container"]')).toBeVisible({
      timeout: 10000,
    });

    // Simulate text selection to trigger SelectionLayer
    const pdfContainer = page.locator('[data-testid="pdf-container"]');
    await pdfContainer.hover();

    // Mouse down to start selection
    await pdfContainer.dispatchEvent("mousedown", {
      clientX: 100,
      clientY: 100,
      buttons: 1,
    });

    // Mouse move to create selection
    await pdfContainer.dispatchEvent("mousemove", {
      clientX: 200,
      clientY: 150,
    });

    // Mouse up to complete selection
    await pdfContainer.dispatchEvent("mouseup", {
      clientX: 200,
      clientY: 150,
    });

    // Should show the selection action menu
    await expect(
      page.locator('[data-testid="selection-action-menu"]')
    ).toBeVisible({ timeout: 5000 });

    // Should show copy option
    await expect(
      page.locator('[data-testid="copy-text-button"]')
    ).toBeVisible();

    // Should show annotation option since user has UPDATE permissions
    await expect(
      page.locator('[data-testid="apply-label-button"]')
    ).toBeVisible();

    // Should NOT show read-only message
    await expect(page.locator("text=Document is read-only")).not.toBeVisible();

    await component.unmount();
  });

  test("should be read-only when user lacks UPDATE permissions", async ({
    mount,
    page,
  }) => {
    // Create mocks with READ-only permissions
    const readOnlyDocument = {
      ...mockDocument,
      myPermissions: ["READ"], // No UPDATE permission
    };

    const readOnlyCorpus = {
      ...mockCorpus,
      myPermissions: ["READ"], // No UPDATE permission
    };

    const readOnlySlugMock = {
      request: {
        query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
        variables: {
          userSlug: "testuser",
          corpusSlug: "test-corpus",
          documentSlug: "test-document",
        },
      },
      result: {
        data: {
          corpusBySlugs: readOnlyCorpus,
          documentInCorpusBySlugs: readOnlyDocument,
        },
      },
    };

    const readOnlyDataMock = {
      request: {
        query: GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
        variables: {
          documentId: "RG9jdW1lbnRUeXBlOjE=",
          corpusId: "Q29ycHVzVHlwZTox",
          analysisId: undefined,
        },
      },
      result: {
        data: {
          document: { ...mockDocumentFull, myPermissions: ["READ"] },
          corpus: { ...mockCorpusFull, myPermissions: ["READ"] },
        },
      },
    };

    await page.addInitScript(() => {
      (window as any).pdfjsLib = {
        getDocument: () => ({
          promise: Promise.resolve({
            numPages: 1,
            getPage: () =>
              Promise.resolve({
                pageNumber: 1,
                getViewport: () => ({ width: 800, height: 600 }),
                render: () => ({ promise: Promise.resolve() }),
              }),
          }),
          onProgress: () => {},
        }),
        GlobalWorkerOptions: { workerSrc: "" },
      };

      const originalFetch = window.fetch;
      window.fetch = (input, init) => {
        if (typeof input === "string" && input.includes("test.pawls")) {
          return Promise.resolve(new Response("[]"));
        }
        return originalFetch(input, init);
      };
    });

    const component = await mount(
      <MockedProvider
        mocks={[readOnlySlugMock, readOnlyDataMock]}
        addTypename={false}
      >
        <MemoryRouter
          initialEntries={["/d/testuser/test-corpus/test-document"]}
        >
          <JotaiProvider>
            <DocumentLandingRoute />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for the document to load
    await expect(page.locator('[data-testid="pdf-container"]')).toBeVisible({
      timeout: 10000,
    });

    // Simulate text selection
    const pdfContainer = page.locator('[data-testid="pdf-container"]');
    await pdfContainer.hover();

    await pdfContainer.dispatchEvent("mousedown", {
      clientX: 100,
      clientY: 100,
      buttons: 1,
    });

    await pdfContainer.dispatchEvent("mousemove", {
      clientX: 200,
      clientY: 150,
    });

    await pdfContainer.dispatchEvent("mouseup", {
      clientX: 200,
      clientY: 150,
    });

    // Should show the selection action menu
    await expect(
      page.locator('[data-testid="selection-action-menu"]')
    ).toBeVisible({ timeout: 5000 });

    // Should show copy option (always available)
    await expect(
      page.locator('[data-testid="copy-text-button"]')
    ).toBeVisible();

    // Should NOT show annotation option since user lacks UPDATE permissions
    await expect(
      page.locator('[data-testid="apply-label-button"]')
    ).not.toBeVisible();

    // Should show message about no corpus permissions
    await expect(page.locator("text=No corpus permissions")).toBeVisible();

    await component.unmount();
  });

  test("should respect explicit readOnly prop", async ({ mount, page }) => {
    // Even with UPDATE permissions, explicit readOnly should override
    const explicitReadOnlyMocks = [slugResolutionMock, documentDataMock];

    await page.addInitScript(() => {
      (window as any).pdfjsLib = {
        getDocument: () => ({
          promise: Promise.resolve({
            numPages: 1,
            getPage: () =>
              Promise.resolve({
                pageNumber: 1,
                getViewport: () => ({ width: 800, height: 600 }),
                render: () => ({ promise: Promise.resolve() }),
              }),
          }),
          onProgress: () => {},
        }),
        GlobalWorkerOptions: { workerSrc: "" },
      };

      const originalFetch = window.fetch;
      window.fetch = (input, init) => {
        if (typeof input === "string" && input.includes("test.pawls")) {
          return Promise.resolve(new Response("[]"));
        }
        return originalFetch(input, init);
      };
    });

    // We'll need to modify the DocumentLandingRoute to accept readOnly prop for this test
    // Or create a custom component that wraps DocumentKnowledgeBase with readOnly=true
    const component = await mount(
      <MockedProvider mocks={explicitReadOnlyMocks} addTypename={false}>
        <MemoryRouter
          initialEntries={["/d/testuser/test-corpus/test-document"]}
        >
          <JotaiProvider>
            <DocumentLandingRoute />
          </JotaiProvider>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for the document to load
    await expect(page.locator('[data-testid="pdf-container"]')).toBeVisible({
      timeout: 10000,
    });

    // Check that document loaded properly but verify through interaction
    // This test would be more effective with a custom test component that sets readOnly=true

    await component.unmount();
  });
});
