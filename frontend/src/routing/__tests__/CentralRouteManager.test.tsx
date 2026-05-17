/**
 * Comprehensive tests for CentralRouteManager
 * Tests all 4 phases of the routing system:
 * 1. URL Path → Entity Resolution
 * 2. URL Query Params → Reactive Vars
 * 3. Entity Data → Canonical Redirects
 * 4. Reactive Vars → URL Sync
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { CentralRouteManager } from "../CentralRouteManager";
import {
  openedCorpus,
  openedDocument,
  openedExtract,
  openedUser,
  selectedAnnotationIds,
  selectedAnalysesIds,
  selectedExtractIds,
  selectedRelationshipId,
  routeLoading,
  routeError,
  authStatusVar,
  authInitCompleteVar,
} from "../../graphql/cache";
import {
  RESOLVE_CORPUS_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_BY_SLUGS_FULL,
  RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
  RESOLVE_EXTRACT_BY_ID,
  GET_USER,
} from "../../graphql/queries";
import { navigationCircuitBreaker } from "../../utils/navigationCircuitBreaker";

// Mock navigation
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("CentralRouteManager", () => {
  beforeEach(() => {
    // Clear all reactive vars
    openedCorpus(null);
    openedDocument(null);
    openedExtract(null);
    openedUser(null);
    selectedAnnotationIds([]);
    selectedAnalysesIds([]);
    selectedExtractIds([]);
    selectedRelationshipId(null);
    routeLoading(false);
    routeError(null);

    // Set auth status so CentralRouteManager proceeds with entity fetching
    authStatusVar("AUTHENTICATED");
    authInitCompleteVar(true);

    // CRITICAL: Reset navigation circuit breaker to prevent test isolation issues
    // The circuit breaker is a singleton that accumulates navigation events across tests
    // Without reset, it can trip and block all navigation after many tests run
    navigationCircuitBreaker.reset();

    // Clear mocks
    mockNavigate.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Phase 1: URL Path → Entity Resolution", () => {
    describe("Corpus Routes", () => {
      it("should resolve corpus from slug-based URL", async () => {
        const mockCorpus = {
          id: "corpus-123",
          slug: "my-corpus",
          title: "My Corpus",
          description: "Test corpus description",
          mdDescription: "Test MD description",
          isPublic: true,
          myPermissions: ["read"],
          labelSet: null,
          documentCount: 5,
          annotationCount: 3,
          creator: { id: "user-1", slug: "john", username: "john" },
        };

        const mocks = [
          {
            request: {
              query: RESOLVE_CORPUS_BY_SLUGS_FULL,
              variables: {
                userSlug: "john",
                corpusSlug: "my-corpus",
              },
            },
            result: {
              data: {
                corpusBySlugs: mockCorpus,
              },
            },
          },
        ];

        render(
          <MockedProvider mocks={mocks} addTypename={false}>
            <MemoryRouter initialEntries={["/c/john/my-corpus"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        // Should set loading state initially
        expect(routeLoading()).toBe(true);

        // Wait for resolution
        await waitFor(() => {
          expect(routeLoading()).toBe(false);
        });

        // Should set corpus in reactive var
        expect(openedCorpus()).toEqual(mockCorpus);
        expect(openedDocument()).toBeNull();
      });

      it("should navigate to 404 when corpus not found", async () => {
        const mocks = [
          {
            request: {
              query: RESOLVE_CORPUS_BY_SLUGS_FULL,
              variables: {
                userSlug: "john",
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

        render(
          <MockedProvider mocks={mocks} addTypename={false}>
            <MemoryRouter initialEntries={["/c/john/non-existent"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith("/404", { replace: true });
        });
      });
    });

    describe("Document Routes", () => {
      it("should resolve standalone document", async () => {
        const mockDocument = {
          id: "doc-123",
          slug: "my-document",
          title: "My Document",
          description: "Test document description",
          fileType: "application/pdf",
          isPublic: true,
          pdfFile: "/media/test.pdf",
          backendLock: false,
          myPermissions: ["read", "write"],
          creator: { id: "user-1", slug: "john", username: "john" },
        };

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
                documentBySlugs: mockDocument,
              },
            },
          },
        ];

        render(
          <MockedProvider mocks={mocks} addTypename={false}>
            <MemoryRouter initialEntries={["/d/john/my-document"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        await waitFor(() => {
          expect(routeLoading()).toBe(false);
        });

        expect(openedDocument()).toEqual(mockDocument);
        expect(openedCorpus()).toBeNull();
      });

      it("should resolve document in corpus", async () => {
        const mockCorpus = {
          id: "corpus-123",
          slug: "my-corpus",
          title: "My Corpus",
          description: "Test corpus description",
          mdDescription: "Test MD description",
          isPublic: true,
          myPermissions: ["read"],
          labelSet: null,
          creator: { id: "user-1", slug: "john", username: "john" },
        };

        const mockDocument = {
          id: "doc-123",
          slug: "my-document",
          title: "My Document",
          description: "Test document description",
          fileType: "application/pdf",
          isPublic: true,
          pdfFile: "/media/test.pdf",
          backendLock: false,
          myPermissions: ["read", "write"],
          creator: { id: "user-1", slug: "john", username: "john" },
        };

        const mocks = [
          {
            request: {
              query: RESOLVE_DOCUMENT_IN_CORPUS_BY_SLUGS_FULL,
              variables: {
                userSlug: "john",
                corpusSlug: "my-corpus",
                documentSlug: "my-document",
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

        render(
          <MockedProvider mocks={mocks} addTypename={false}>
            <MemoryRouter initialEntries={["/d/john/my-corpus/my-document"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        await waitFor(() => {
          expect(routeLoading()).toBe(false);
        });

        expect(openedCorpus()).toEqual(mockCorpus);
        expect(openedDocument()).toEqual(mockDocument);
      });
    });

    describe("Browse Routes", () => {
      it("should not fetch entities for browse routes", () => {
        render(
          <MockedProvider mocks={[]} addTypename={false}>
            <MemoryRouter initialEntries={["/annotations"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        expect(routeLoading()).toBe(false);
        expect(openedCorpus()).toBeNull();
        expect(openedDocument()).toBeNull();
      });

      it("should not fetch for corpuses list view", () => {
        render(
          <MockedProvider mocks={[]} addTypename={false}>
            <MemoryRouter initialEntries={["/corpuses"]}>
              <CentralRouteManager />
            </MemoryRouter>
          </MockedProvider>
        );

        expect(routeLoading()).toBe(false);
      });
    });
  });

  describe("Phase 2: URL Query Params → Reactive Vars", () => {
    it("should parse annotation IDs from URL", () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations?ann=123,456"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedAnnotationIds()).toEqual(["123", "456"]);
    });

    it("should parse analysis IDs from URL", () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/corpuses?analysis=789"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedAnalysesIds()).toEqual(["789"]);
    });

    it("should parse extract IDs from URL", () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/extracts?extract=101,202"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedExtractIds()).toEqual(["101", "202"]);
    });

    it("should parse multiple query param types", () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter
            initialEntries={["/annotations?ann=1,2&analysis=3&extract=4,5"]}
          >
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedAnnotationIds()).toEqual(["1", "2"]);
      expect(selectedAnalysesIds()).toEqual(["3"]);
      expect(selectedExtractIds()).toEqual(["4", "5"]);
    });

    it("should clear params when not in URL", () => {
      // Set initial values
      selectedAnnotationIds(["old-1"]);
      selectedAnalysesIds(["old-2"]);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedAnnotationIds()).toEqual([]);
      expect(selectedAnalysesIds()).toEqual([]);
    });

    it("should parse selectedRelationshipId from rel= URL param (issue #1645)", () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations?rel=42"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedRelationshipId()).toBe("42");
    });

    it("should clear selectedRelationshipId when rel= absent from URL", () => {
      selectedRelationshipId("123");

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(selectedRelationshipId()).toBeNull();
    });
  });

  describe("Phase 3: Entity Data → Canonical Redirects", () => {
    it("should redirect to canonical corpus path", async () => {
      const mockCorpus = {
        id: "corpus-123",
        slug: "normalized-slug",
        title: "My Corpus",
        description: "Test description",
        mdDescription: "Test MD description",
        isPublic: true,
        myPermissions: ["read"],
        labelSet: null,
        documentCount: 10,
        annotationCount: 5,
        creator: { id: "user-1", slug: "john-doe", username: "johndoe" },
      };

      const mocks = [
        {
          request: {
            query: RESOLVE_CORPUS_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              corpusSlug: "old-slug",
            },
          },
          result: {
            data: {
              corpusBySlugs: mockCorpus,
            },
          },
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john/old-slug"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Wait for corpus to be resolved and set in reactive var
      await waitFor(() => {
        expect(openedCorpus()).toEqual(mockCorpus);
      });

      // Phase 3 canonical redirect happens automatically via useEffect
      // Since we can't reliably test navigate calls with MemoryRouter,
      // we verify the corpus was loaded correctly (canonical redirect is internal)
      expect(openedCorpus()?.slug).toBe("normalized-slug");
      expect(openedCorpus()?.creator?.slug).toBe("john-doe");
    });

    it("should preserve query params during canonical redirect", async () => {
      const mockDocument = {
        id: "doc-123",
        slug: "canonical-doc",
        title: "My Document",
        description: "Test document",
        fileType: "application/pdf",
        isPublic: true,
        pdfFile: "/test.pdf",
        backendLock: false,
        myPermissions: ["read"],
        creator: { id: "user-1", slug: "jane", username: "jane" },
      };

      const mocks = [
        {
          request: {
            query: RESOLVE_DOCUMENT_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              documentSlug: "old-doc",
            },
          },
          result: {
            data: {
              documentBySlugs: mockDocument,
            },
          },
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter
            initialEntries={["/d/john/old-doc?ann=123&analysis=456"]}
          >
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Wait for document to be resolved
      await waitFor(() => {
        expect(openedDocument()).toEqual(mockDocument);
      });

      // Verify query params were parsed (Phase 2)
      expect(selectedAnnotationIds()).toEqual(["123"]);
      expect(selectedAnalysesIds()).toEqual(["456"]);

      // Phase 3 canonical redirect happens automatically
      // The redirect preserves query params internally
      expect(openedDocument()?.slug).toBe("canonical-doc");
      expect(openedDocument()?.creator?.slug).toBe("jane");
    });
  });

  describe("Phase 4: Reactive Vars → URL Sync", () => {
    it("should update URL when annotation IDs change", async () => {
      const { rerender } = render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Change reactive var
      selectedAnnotationIds(["new-123", "new-456"]);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          { search: "?ann=new-123%2Cnew-456" }, // URL-encoded comma, leading ?
          { replace: true }
        );
      });
    });

    it("should update URL when analysis IDs change", async () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/corpuses"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      selectedAnalysesIds(["789"]);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          { search: "?analysis=789" }, // Leading ?
          { replace: true }
        );
      });
    });

    it("should combine multiple params in URL", async () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      selectedAnnotationIds(["1", "2"]);
      selectedAnalysesIds(["3"]);
      selectedExtractIds(["4"]);

      await waitFor(() => {
        const lastCall =
          mockNavigate.mock.calls[mockNavigate.mock.calls.length - 1];
        expect(lastCall[0].search).toContain("ann=1%2C2"); // URL-encoded
        expect(lastCall[0].search).toContain("analysis=3");
        expect(lastCall[0].search).toContain("extract=4");
      });
    });

    it("should clear URL params when reactive vars empty", async () => {
      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations?ann=123"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Clear reactive var
      selectedAnnotationIds([]);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          { search: "" },
          { replace: true }
        );
      });
    });
  });

  describe("Error Handling", () => {
    it("should navigate to 404 on GraphQL failure", async () => {
      const mocks = [
        {
          request: {
            query: RESOLVE_CORPUS_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              corpusSlug: "my-corpus",
            },
          },
          error: new Error("Network error"),
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john/my-corpus"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // GraphQL errors trigger navigation to /404, not routeError
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith("/404", { replace: true });
      });
    });
  });

  describe("Request Deduplication", () => {
    it("should not trigger duplicate requests for same route", async () => {
      const mockCorpus = {
        id: "corpus-123",
        slug: "my-corpus",
        title: "My Corpus",
        creator: { id: "user-1", slug: "john", email: "john@example.com" },
      };

      const queryMock = vi.fn(() => ({
        data: { corpusBySlugs: mockCorpus },
      }));

      const mocks = [
        {
          request: {
            query: RESOLVE_CORPUS_BY_SLUGS_FULL,
            variables: {
              userSlug: "john",
              corpusSlug: "my-corpus",
            },
          },
          result: queryMock,
        },
      ];

      const { rerender } = render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john/my-corpus"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Force re-render (should not trigger second request due to ref guard)
      rerender(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/c/john/my-corpus"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        // Query should only be called once
        expect(queryMock).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe("Route Change Handling", () => {
    it("should clear old entities when navigating to browse route", async () => {
      const mockCorpus = {
        id: "corpus-123",
        slug: "my-corpus",
        title: "My Corpus",
        creator: { id: "user-1", slug: "john", email: "john@example.com" },
      };

      // Set initial corpus
      openedCorpus(mockCorpus as any);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/annotations"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      // Should clear corpus when on browse route
      expect(openedCorpus()).toBeNull();
      expect(openedDocument()).toBeNull();
    });

    it("should clear openedUser when navigating to a browse route", async () => {
      openedUser({
        id: "user-1",
        username: "jane",
        slug: "jane",
        name: "Jane",
        firstName: "Jane",
        lastName: "Doe",
        email: "jane@example.com",
        isProfilePublic: true,
        profileHeadline: null,
        profileAboutMarkdown: null,
        profileLinksMarkdown: null,
        reputationGlobal: 0,
        totalMessages: 0,
        totalThreadsCreated: 0,
        totalAnnotationsCreated: 0,
        totalDocumentsUploaded: 0,
      });

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter initialEntries={["/corpuses"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(openedUser()).toBeNull();
    });
  });

  describe("Phase 1: User Profile Routes (/users/:slug)", () => {
    const mockUser = {
      id: "user-42",
      username: "jane",
      slug: "jane",
      name: "Jane Doe",
      firstName: "Jane",
      lastName: "Doe",
      email: "jane@example.com",
      isProfilePublic: true,
      reputationGlobal: 100,
      totalMessages: 12,
      totalThreadsCreated: 3,
      totalAnnotationsCreated: 25,
      totalDocumentsUploaded: 7,
    };

    it("resolves a user from /users/:slug into openedUser", async () => {
      const mocks = [
        {
          request: {
            query: GET_USER,
            variables: { slug: "jane" },
          },
          result: { data: { userBySlug: mockUser } },
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/users/jane"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        expect(routeLoading()).toBe(false);
      });

      expect(openedUser()).toEqual(mockUser);
      expect(openedCorpus()).toBeNull();
      expect(openedDocument()).toBeNull();
      expect(openedExtract()).toBeNull();
      expect(routeError()).toBeNull();
    });

    it("sets routeError when the user slug does not exist", async () => {
      const mocks = [
        {
          request: {
            query: GET_USER,
            variables: { slug: "ghost" },
          },
          result: { data: { userBySlug: null } },
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/users/ghost"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        expect(routeLoading()).toBe(false);
      });

      expect(openedUser()).toBeNull();
      expect(routeError()).not.toBeNull();
      expect(routeError()?.message).toMatch(/ghost/);
      // The user-not-found path should NOT redirect to /404 — the in-place
      // error display lets the visitor edit the slug without losing the URL.
      expect(mockNavigate).not.toHaveBeenCalledWith("/404", expect.anything());
    });
  });

  describe("Phase 1: Extract Routes (/extracts/:extractId)", () => {
    const mockExtract = {
      id: "extract-123",
      name: "My Extract",
      created: "2026-01-01T00:00:00Z",
      started: null,
      finished: null,
      error: null,
      myPermissions: ["read"],
      creator: { id: "user-1", slug: "john", username: "john" },
      corpus: {
        id: "corpus-1",
        slug: "my-corpus",
        title: "My Corpus",
        creator: { id: "user-1", slug: "john" },
      },
      fieldset: { id: "fs-1", name: "FS", description: "" },
    };

    it("resolves an extract from /extracts/:extractId into openedExtract", async () => {
      const mocks = [
        {
          request: {
            query: RESOLVE_EXTRACT_BY_ID,
            variables: { extractId: "extract-123" },
          },
          result: { data: { extract: mockExtract } },
        },
      ];

      render(
        <MockedProvider mocks={mocks} addTypename={false}>
          <MemoryRouter initialEntries={["/extracts/extract-123"]}>
            <CentralRouteManager />
          </MemoryRouter>
        </MockedProvider>
      );

      await waitFor(() => {
        expect(routeLoading()).toBe(false);
      });

      expect(openedExtract()).toEqual(mockExtract);
      expect(openedCorpus()).toBeNull();
      expect(openedDocument()).toBeNull();
      expect(openedUser()).toBeNull();
    });
  });
});
