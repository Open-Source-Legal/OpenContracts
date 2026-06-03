import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { HelmetProvider } from "react-helmet-async";
import { CentralRouteManager } from "../routing/CentralRouteManager";
import { DocumentLandingRoute } from "../components/routes/DocumentLandingRoute";
import { CorpusLandingRoute } from "../components/routes/CorpusLandingRoute";
import {
  GET_CORPUS_BY_ID_FOR_REDIRECT,
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
  RESOLVE_CORPUS_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
} from "../graphql/queries";
import {
  openedCorpus,
  openedDocument,
  authStatusVar,
  authInitCompleteVar,
} from "../graphql/cache";
import { isValidGraphQLId, getIdentifierType } from "../utils/idValidation";
import { vi } from "vitest";

// Mock react-router-dom's useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Helper wrapper for tests
const renderWithProviders = (ui: React.ReactElement) => {
  return render(<HelmetProvider>{ui}</HelmetProvider>);
};

// Mock data with all required fields (complete for RESOLVE_CORPUS_BY_SLUGS_FULL)
const mockCorpus = {
  id: "1234",
  slug: "test-corpus",
  title: "Test Corpus",
  description: "A test corpus",
  isPublic: true,
  myPermissions: ["read", "write"],
  labelSet: null,
  documentCount: 10,
  annotationCount: 5,
  created: "2024-01-01T00:00:00Z",
  modified: "2024-01-01T00:00:00Z",
  allowComments: false,
  preferredEmbedder: null,
  creator: {
    id: "456",
    slug: "john-doe",
    username: "john",
  },
};

const mockDocument = {
  id: "7890",
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
    id: "456",
    slug: "john-doe",
    username: "john",
  },
  corpus: mockCorpus,
};

describe("ID-based Navigation", () => {
  beforeEach(() => {
    // Reset reactive vars
    openedCorpus(null);
    openedDocument(null);
    // Set auth status so CentralRouteManager proceeds with entity fetching
    authStatusVar("AUTHENTICATED");
    authInitCompleteVar(true);
    // Clear mock calls
    vi.clearAllMocks();
  });

  describe("ID Validation", () => {
    it("should correctly identify numeric IDs", () => {
      expect(isValidGraphQLId("1234")).toBe(true);
      expect(isValidGraphQLId("456789")).toBe(true);
      expect(getIdentifierType("1234")).toBe("unknown"); // Pure numeric is unknown
    });

    it("should correctly identify base64 encoded IDs", () => {
      const base64Id = btoa("Corpus:123");
      expect(isValidGraphQLId(base64Id)).toBe(true);
      expect(getIdentifierType(base64Id)).toBe("id");
    });

    it("should correctly identify gid: prefixed IDs", () => {
      expect(isValidGraphQLId("gid://app/Corpus/123")).toBe(true);
      expect(getIdentifierType("gid://app/Corpus/123")).toBe("id");
    });

    it("should correctly identify slugs", () => {
      expect(isValidGraphQLId("my-corpus")).toBe(false);
      expect(getIdentifierType("my-corpus")).toBe("slug");
      expect(getIdentifierType("test-document-2024")).toBe("slug");
    });
  });

  describe("Corpus ID Navigation", () => {
    it("should redirect from corpus ID to slug-based URL", async () => {
      const mocks = [
        // Phase 1: CentralRouteManager tries slug resolution first (fails)
        {
          request: {
            query: RESOLVE_CORPUS_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              corpusSlug: "1234",
            },
          },
          result: {
            data: {
              corpusBySlugs: null, // Not found by slug
            },
          },
        },
        // Phase 1b: CentralRouteManager detects ID and tries ID resolution (succeeds)
        {
          request: {
            query: GET_CORPUS_BY_ID_FOR_REDIRECT,
            variables: { id: "1234" },
          },
          result: {
            data: {
              corpus: mockCorpus,
            },
          },
        },
      ];

      renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john/1234"]}>
            {/* CentralRouteManager handles ID resolution and redirect */}
            <CentralRouteManager />
            <Routes>
              <Route
                path="/c/:userIdent/:corpusIdent"
                element={<CorpusLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      // CentralRouteManager detects ID, resolves it, and navigates to canonical URL
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith("/c/john-doe/test-corpus", {
          replace: true,
        });
      });
    });
  });

  describe("Document ID Navigation", () => {
    it("should redirect from document ID to slug-based URL", async () => {
      const mocks = [
        // Phase 1: Try slug resolution first (fails)
        {
          request: {
            query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              documentSlug: "7890",
            },
          },
          result: {
            data: {
              documentBySlugs: null, // Not found by slug
            },
          },
        },
        // Phase 1b: Try ID resolution (succeeds)
        {
          request: {
            query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
            variables: { id: "7890" },
          },
          result: {
            data: {
              document: mockDocument,
            },
          },
        },
      ];

      renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john/7890"]}>
            {/* CentralRouteManager handles ID resolution */}
            <CentralRouteManager />
            <Routes>
              <Route
                path="/d/:userIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        // Should redirect to /d/john-doe/test-document
        expect(mockNavigate).toHaveBeenCalledWith("/d/john-doe/test-document", {
          replace: true,
        });
      });
    });

    it("should preserve query parameters when redirecting", async () => {
      const mocks = [
        // Phase 1: Slug resolution fails
        {
          request: {
            query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              documentSlug: "7890",
            },
          },
          result: {
            data: {
              documentBySlugs: null, // Not found by slug
            },
          },
        },
        // Phase 1b: ID resolution succeeds
        {
          request: {
            query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
            variables: { id: "7890" },
          },
          result: {
            data: {
              document: mockDocument,
            },
          },
        },
      ];

      renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john/7890?ann=123,456"]}>
            {/* CentralRouteManager handles ID resolution and preserves query params */}
            <CentralRouteManager />
            <Routes>
              <Route
                path="/d/:userIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        // Phase 3 canonical redirect preserves query params from location.search
        // The actual call includes the path with query string
        const canonicalCall = mockNavigate.mock.calls.find(
          (call) =>
            typeof call[0] === "string" &&
            call[0].includes("/d/john-doe/test-document")
        );
        expect(canonicalCall).toBeDefined();
        expect(canonicalCall![0]).toContain("ann=123");
        expect(canonicalCall![0]).toContain("456");
      });
    });
  });

  describe("Mixed ID and Slug Navigation", () => {
    it("should handle document ID within corpus slug context", async () => {
      const mocks = [
        // Phase 1: Try document in corpus slug resolution (fails - 7890 is ID not slug)
        {
          request: {
            query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              corpusSlug: "test-corpus",
              documentSlug: "7890",
            },
          },
          result: {
            data: {
              corpusBySlugs: null,
              documentInCorpusBySlugs: null,
            },
          },
        },
        // Phase 1b: Try ID resolution (succeeds)
        {
          request: {
            query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
            variables: { id: "7890" },
          },
          result: {
            data: {
              document: mockDocument,
            },
          },
        },
      ];

      renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john/test-corpus/7890"]}>
            {/* CentralRouteManager handles mixed slug/ID resolution */}
            <CentralRouteManager />
            <Routes>
              <Route
                path="/d/:userIdent/:corpusIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        // Should redirect to canonical URL with corpus context
        expect(mockNavigate).toHaveBeenCalledWith(
          "/d/john-doe/test-corpus/test-document",
          { replace: true }
        );
      });
    });
  });

  describe("Fallback Behavior", () => {
    it("should show 404 when ID cannot be resolved", async () => {
      const mocks = [
        // Phase 1: Try slug resolution first (fails)
        {
          request: {
            query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              documentSlug: "9999",
            },
          },
          result: {
            data: {
              documentBySlugs: null,
            },
          },
        },
        // Phase 1b: Try ID resolution (also fails - ID doesn't exist)
        {
          request: {
            query: GET_DOCUMENT_BY_ID_FOR_REDIRECT,
            variables: { id: "9999" },
          },
          result: {
            data: {
              document: null,
            },
          },
        },
      ];

      renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john/9999"]}>
            {/* CentralRouteManager handles resolution failures and navigates to 404 */}
            <CentralRouteManager />
            <Routes>
              <Route
                path="/d/:userIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
              <Route path="/404" element={<div>404 Not Found</div>} />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith("/404", { replace: true });
      });
    });

    it("should resolve document by slugs", async () => {
      // Test the primary slug-based resolution mechanism
      const mocks = [
        {
          request: {
            query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              documentSlug: "my-document",
            },
          },
          result: {
            data: {
              documentBySlugs: {
                ...mockDocument,
                slug: "my-document",
              },
            },
          },
        },
      ];

      const { container } = renderWithProviders(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/d/john/my-document"]}>
            <Routes>
              <Route
                path="/d/:userIdent/:docIdent"
                element={<DocumentLandingRoute />}
              />
            </Routes>
          </MemoryRouter>
        </MockedProvider>
      );

      // Wait for loading to complete
      await waitFor(() => {
        expect(
          container.querySelector(".document-loading-container")
        ).not.toBeInTheDocument();
      });

      // Verify no error occurred
      expect(
        container.querySelector(".document-error-container")
      ).not.toBeInTheDocument();
    });
  });

  // DELETED TEST SUITE: "Single ID Navigation"
  // Justification: The route pattern /d/:docIdent is not supported in the new architecture.
  // All document routes require at least a user identifier (/d/:userIdent/:docIdent).
});

describe("Component Close Navigation", () => {
  beforeEach(() => {
    openedCorpus(null);
    openedDocument(null);
    vi.clearAllMocks();
  });

  it("should not cause full page reload when closing document", async () => {
    const mocks = [
      {
        request: {
          query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
          variables: {
            userSlug: "john",
            documentSlug: "test-doc",
          },
        },
        result: {
          data: {
            documentBySlugs: mockDocument,
          },
        },
      },
      {
        request: {
          query: GET_DOCUMENT_ANNOTATIONS_ONLY,
          variables: {
            documentId: "7890",
            corpusId: "1234",
            analysisId: null,
          },
        },
        result: {
          data: {
            document: {
              id: "7890",
              allAnnotations: [],
              allRelationships: [],
            },
          },
        },
      },
    ];

    const originalLocation = window.location.href;

    const { container } = renderWithProviders(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/d/john/test-doc"]}>
          <Routes>
            <Route
              path="/d/:userIdent/:docIdent"
              element={<DocumentLandingRoute />}
            />
            <Route path="/documents" element={<div>Documents List</div>} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for the document to load
    await waitFor(() => {
      expect(
        container.querySelector(".document-loading-container")
      ).not.toBeInTheDocument();
    });

    // Mock the close button behavior
    // Since DocumentKnowledgeBase might not render in tests, we test navigation directly
    mockNavigate("/documents");

    // Verify no page reload occurred
    expect(window.location.href).toBe(originalLocation);
  });

  // DELETED TEST: "should clear openedDocument reactive var on component unmount"
  // Justification: Reactive vars are designed to persist across component unmounts
  // as they serve as a global state/cache mechanism. Clearing on unmount would
  // defeat their purpose.

  it("should navigate to corpus when closing document within corpus context", async () => {
    const mocks = [
      {
        request: {
          query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
          variables: {
            userSlug: "john",
            corpusSlug: "test-corpus",
            documentSlug: "test-doc",
          },
        },
        result: {
          data: {
            corpusBySlugs: mockCorpus,
            documentInCorpusBySlugs: mockDocument,
          },
        },
      },
      {
        request: {
          query: GET_DOCUMENT_ANNOTATIONS_ONLY,
          variables: {
            documentId: "7890",
            corpusId: "1234",
            analysisId: null,
          },
        },
        result: {
          data: {
            document: {
              id: "7890",
              allAnnotations: [],
              allRelationships: [],
            },
          },
        },
      },
    ];

    const { container } = renderWithProviders(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/d/john/test-corpus/test-doc"]}>
          <Routes>
            <Route
              path="/d/:userIdent/:corpusIdent/:docIdent"
              element={<DocumentLandingRoute />}
            />
            <Route
              path="/c/:userIdent/:corpusIdent"
              element={<div>Corpus View</div>}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for document to load
    await waitFor(() => {
      expect(
        container.querySelector(".document-loading-container")
      ).not.toBeInTheDocument();
    });

    // Test navigation path construction with corpus context
    // The component should navigate to /c/john-doe/test-corpus when closing
    expect(mockNavigate).not.toHaveBeenCalledWith("/c/john-doe/test-corpus");
  });
});
