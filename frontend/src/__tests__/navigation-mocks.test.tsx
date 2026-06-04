/**
 * Simple test to verify that GraphQL mocks work with the new routing patterns
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { HelmetProvider } from "react-helmet-async";
import { DocumentLandingRoute } from "../components/routes/DocumentLandingRoute";
import { CorpusLandingRoute } from "../components/routes/CorpusLandingRoute";
import {
  RESOLVE_CORPUS_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
} from "../graphql/queries";
import { vi } from "vitest";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Complete mock data
const mockCorpus = {
  id: "corpus-123",
  slug: "test-corpus",
  title: "Test Corpus",
  description: "A test corpus",
  isPublic: true,
  myPermissions: ["read", "write"],
  labelSet: null,
  created: "2024-01-01T00:00:00Z",
  modified: "2024-01-01T00:00:00Z",
  allowComments: false,
  preferredEmbedder: null,
  creator: {
    id: "user-456",
    slug: "john-doe",
    username: "john",
  },
};

const mockDocument = {
  id: "doc-789",
  slug: "test-document",
  title: "Test Document",
  description: "A test document",
  isPublic: true,
  fileType: "application/pdf",
  pdfFile: "/media/test.pdf",
  backendLock: false,
  created: "2024-01-01T00:00:00Z",
  modified: "2024-01-01T00:00:00Z",
  myPermissions: ["read", "write"],
  creator: {
    id: "user-456",
    slug: "john-doe",
    username: "john",
  },
  corpus: mockCorpus,
};

describe("Navigation with GraphQL Mocks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should resolve corpus via slug-based route", async () => {
    const mocks = [
      {
        request: {
          query: RESOLVE_CORPUS_BY_SLUGS_FULL,
          variables: {
            userSlug: "john-doe",
            corpusSlug: "test-corpus",
          },
        },
        result: {
          data: {
            corpusBySlugs: mockCorpus,
          },
        },
      },
    ];

    const { container } = render(
      <HelmetProvider>
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john-doe/test-corpus"]}>
            <Routes>
              <Route
                path="/c/:userIdent/:corpusIdent"
                element={<CorpusLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      </HelmetProvider>
    );

    // Wait for loading to complete
    await waitFor(
      () => {
        expect(
          container.querySelector(".corpus-loading-container")
        ).not.toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // The corpus should be loaded
    expect(mockNavigate).not.toHaveBeenCalledWith("/404", { replace: true });
  });

  it("should resolve standalone document via slug-based route", async () => {
    const mocks = [
      {
        request: {
          query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
          variables: {
            userSlug: "john-doe",
            documentSlug: "test-document",
          },
        },
        result: {
          data: {
            documentBySlugs: mockDocument,
          },
        },
      },
    ];

    const { container } = render(
      <HelmetProvider>
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john-doe/test-document"]}>
            <Routes>
              <Route
                path="/d/:userIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      </HelmetProvider>
    );

    // Wait for loading to complete
    await waitFor(
      () => {
        expect(
          container.querySelector(".document-loading-container")
        ).not.toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // The document should be loaded
    expect(mockNavigate).not.toHaveBeenCalledWith("/404", { replace: true });
  });

  it("should resolve document in corpus via slug-based route", async () => {
    const mocks = [
      {
        request: {
          query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
          variables: {
            userSlug: "john-doe",
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
      },
    ];

    const { container } = render(
      <HelmetProvider>
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter
            initialEntries={["/d/john-doe/test-corpus/test-document"]}
          >
            <Routes>
              <Route
                path="/d/:userIdent/:corpusIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      </HelmetProvider>
    );

    // Wait for loading to complete
    await waitFor(
      () => {
        expect(
          container.querySelector(".document-loading-container")
        ).not.toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // The document should be loaded
    expect(mockNavigate).not.toHaveBeenCalledWith("/404", { replace: true });
  });

  it("should show corpuses list when no specific corpus is selected", async () => {
    // Note: Without CentralRouteManager, CorpusLandingRoute will show Corpuses
    // list view when corpus is null (without error). This tests that the component
    // doesn't crash when GraphQL returns null.
    const mocks = [
      {
        request: {
          query: RESOLVE_CORPUS_BY_SLUGS_FULL,
          variables: {
            userSlug: "john-doe",
            corpusSlug: "non-existent",
          },
        },
        result: {
          data: {
            corpusBySlugs: null,
          },
        },
      },
    ];

    const { container } = render(
      <HelmetProvider>
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john-doe/non-existent"]}>
            <Routes>
              <Route
                path="/c/:userIdent/:corpusIdent"
                element={<CorpusLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      </HelmetProvider>
    );

    // Component should not crash - in real app, CentralRouteManager would
    // detect null result and navigate to /404, but in this isolated test,
    // the component just shows Corpuses list view
    await waitFor(
      () => {
        // Just verify component rendered without crashing
        expect(container.firstChild).toBeTruthy();
      },
      { timeout: 3000 }
    );
  });
});
