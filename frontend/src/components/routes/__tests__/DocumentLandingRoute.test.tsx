import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DocumentLandingRoute } from "../DocumentLandingRoute";
import {
  openedDocument,
  openedCorpus,
  routeLoading,
  routeError,
} from "../../../graphql/cache";

// Mock the document knowledge base component
vi.mock("../../knowledge_base", () => ({
  DocumentKnowledgeBase: () => <div>DocumentKnowledgeBase Component</div>,
}));

// Mock MetaTags
vi.mock("../../seo/MetaTags", () => ({
  MetaTags: () => null,
}));

// Mock ErrorBoundary
vi.mock("../../widgets/ErrorBoundary", () => ({
  ErrorBoundary: ({ children }: any) => <div>{children}</div>,
}));

// Mock loading/error displays
vi.mock("../../widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Loading...</div>,
}));

vi.mock("../../widgets/ModernErrorDisplay", () => ({
  ModernErrorDisplay: ({ error }: any) => (
    <div>Error: {error?.message || error}</div>
  ),
}));

/**
 * DocumentLandingRoute tests
 *
 * Note: This component is now a DUMB CONSUMER that reads state from reactive vars.
 * CentralRouteManager is responsible for setting these vars based on the URL.
 * These tests verify that the component correctly responds to different state combinations.
 */
describe("DocumentLandingRoute - State-Driven Rendering", () => {
  const mockDocument = {
    id: "doc-123",
    slug: "test-document",
    title: "Test Document",
    description: "Test description",
    creator: {
      id: "user-1",
      slug: "john",
      username: "john",
      email: "john@example.com",
    },
  };

  const mockCorpus = {
    id: "corpus-123",
    slug: "my-corpus",
    title: "My Corpus",
    creator: {
      id: "user-1",
      slug: "john",
      email: "john@example.com",
    },
    analyses: {
      edges: [],
      pageInfo: { hasNextPage: false, hasPreviousPage: false },
    },
    upvoteCount: 0,
    downvoteCount: 0,
    score: 0,
  };

  beforeEach(() => {
    // Clear reactive variables before each test
    openedDocument(null);
    openedCorpus(null);
    routeLoading(false);
    routeError(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Loading State", () => {
    it("should show loading display when routeLoading is true", () => {
      routeLoading(true);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter>
            <DocumentLandingRoute />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(screen.getByText("Loading...")).toBeInTheDocument();
    });
  });

  describe("Error State", () => {
    it("should show error display when routeError is set", () => {
      routeError(new Error("Failed to load document"));

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter>
            <DocumentLandingRoute />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(screen.getByText(/Error:/)).toBeInTheDocument();
    });

    it("should show error when document is null", () => {
      routeLoading(false);
      openedDocument(null);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter>
            <DocumentLandingRoute />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(screen.getByText(/Error:/)).toBeInTheDocument();
    });
  });

  describe("Success State - Standalone Document", () => {
    it("should render DocumentKnowledgeBase when document is loaded", () => {
      routeLoading(false);
      openedDocument(mockDocument);
      openedCorpus(null);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter>
            <DocumentLandingRoute />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(
        screen.getByText("DocumentKnowledgeBase Component")
      ).toBeInTheDocument();
    });
  });

  describe("Success State - Document in Corpus", () => {
    it("should render DocumentKnowledgeBase with corpus context", () => {
      routeLoading(false);
      openedDocument(mockDocument);
      openedCorpus(mockCorpus);

      render(
        <MockedProvider mocks={[]} addTypename={false}>
          <MemoryRouter>
            <DocumentLandingRoute />
          </MemoryRouter>
        </MockedProvider>
      );

      expect(
        screen.getByText("DocumentKnowledgeBase Component")
      ).toBeInTheDocument();
    });
  });
});
