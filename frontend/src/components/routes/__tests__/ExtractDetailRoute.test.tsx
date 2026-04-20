import { render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { GraphQLError } from "graphql";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ExtractDetailRoute } from "../ExtractDetailRoute";
import { openedExtract } from "../../../graphql/cache";
import { RESOLVE_EXTRACT_BY_ID } from "../../../graphql/queries";
import type { ExtractType } from "../../../types/graphql-api";

vi.mock("../../../views/ExtractDetail", () => ({
  ExtractDetail: () => <div>ExtractDetail Component</div>,
}));

vi.mock("../../seo/MetaTags", () => ({
  MetaTags: () => null,
}));

vi.mock("../../widgets/ErrorBoundary", () => ({
  ErrorBoundary: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("../../widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Loading...</div>,
}));

vi.mock("../../widgets/ModernErrorDisplay", () => ({
  ModernErrorDisplay: ({ error }: any) => (
    <div>Error: {error?.message || error}</div>
  ),
}));

/**
 * Tests for ExtractDetailRoute.
 *
 * ExtractDetailRoute resolves /extracts/:extractId by either reusing the
 * openedExtract reactive var (when it matches the URL id) or executing a
 * RESOLVE_EXTRACT_BY_ID query. It surfaces loading, error, and not-found
 * states with the ModernLoading/Error displays and defers to ExtractDetail
 * on success.
 */
describe("ExtractDetailRoute", () => {
  const mockExtract: ExtractType = {
    id: "extract-123",
    name: "Test Extract",
    created: "2024-01-15T10:30:00Z",
    started: null,
    finished: null,
    error: null,
    myPermissions: ["read_extract"],
  } as unknown as ExtractType;

  const renderRoute = (extractId: string | undefined, mocks: any[] = []) => {
    const path = extractId ? `/extracts/${extractId}` : "/extracts/";
    return render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/extracts/:extractId"
              element={<ExtractDetailRoute />}
            />
            <Route path="/extracts/" element={<ExtractDetailRoute />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );
  };

  beforeEach(() => {
    openedExtract(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    openedExtract(null);
  });

  it("shows 'No extract ID provided' when extractId param is missing", () => {
    renderRoute(undefined);
    expect(
      screen.getByText(/Error:.*No extract ID provided/)
    ).toBeInTheDocument();
  });

  it("skips the query and renders ExtractDetail when reactive var already has a matching extract", () => {
    openedExtract({ ...mockExtract, id: "extract-123" } as any);

    renderRoute("extract-123");

    // Query is skipped because existingExtract.id === extractId, so we
    // should see the ExtractDetail view immediately.
    expect(screen.getByText("ExtractDetail Component")).toBeInTheDocument();
  });

  it("renders loading state while resolving an unfamiliar extract id", async () => {
    renderRoute("extract-999", [
      {
        request: {
          query: RESOLVE_EXTRACT_BY_ID,
          variables: { extractId: "extract-999" },
        },
        delay: 100,
        result: { data: { extract: { ...mockExtract, id: "extract-999" } } },
      },
    ]);

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders error state when RESOLVE_EXTRACT_BY_ID returns an error", async () => {
    renderRoute("extract-404", [
      {
        request: {
          query: RESOLVE_EXTRACT_BY_ID,
          variables: { extractId: "extract-404" },
        },
        result: { errors: [new GraphQLError("Extract not found")] },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText(/Error:/)).toBeInTheDocument();
    });
  });

  it("renders not-found state when the query resolves with no extract", async () => {
    renderRoute("extract-missing", [
      {
        request: {
          query: RESOLVE_EXTRACT_BY_ID,
          variables: { extractId: "extract-missing" },
        },
        result: { data: { extract: null } },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText(/Error:.*Extract not found/)).toBeInTheDocument();
    });
  });

  it("renders ExtractDetail and sets openedExtract when the query resolves successfully", async () => {
    const resolved = {
      ...mockExtract,
      id: "extract-555",
      name: "Resolved Extract",
    };
    renderRoute("extract-555", [
      {
        request: {
          query: RESOLVE_EXTRACT_BY_ID,
          variables: { extractId: "extract-555" },
        },
        result: { data: { extract: resolved } },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText("ExtractDetail Component")).toBeInTheDocument();
    });
    expect(openedExtract()?.id).toBe("extract-555");
  });
});
