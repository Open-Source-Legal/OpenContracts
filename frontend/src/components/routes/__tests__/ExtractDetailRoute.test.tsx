import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ExtractDetailRoute } from "../ExtractDetailRoute";
import {
  openedExtract,
  routeLoading,
  routeError,
} from "../../../graphql/cache";
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
 * Tests for ExtractDetailRoute (dumb consumer).
 *
 * URL parsing and the RESOLVE_EXTRACT_BY_ID query now live in
 * CentralRouteManager. ExtractDetailRoute reads openedExtract / routeLoading
 * / routeError and renders one of three states.
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

  const renderRoute = () =>
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/extracts/extract-123"]}>
          <Routes>
            <Route
              path="/extracts/:extractId"
              element={<ExtractDetailRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

  beforeEach(() => {
    openedExtract(null);
    routeLoading(false);
    routeError(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    openedExtract(null);
    routeLoading(false);
    routeError(null);
  });

  it("shows loading display when routeLoading is true and no extract is resolved", () => {
    routeLoading(true);
    renderRoute();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows error display when routeError is set", () => {
    routeError(new Error("Boom"));
    renderRoute();
    expect(screen.getByText(/Error:.*Boom/)).toBeInTheDocument();
  });

  it("shows 'Extract not found' when no extract is resolved and no error/loading is set", () => {
    renderRoute();
    expect(screen.getByText(/Error:.*Extract not found/)).toBeInTheDocument();
  });

  it("renders ExtractDetail when an extract has been resolved", () => {
    openedExtract(mockExtract as any);
    renderRoute();
    expect(screen.getByText("ExtractDetail Component")).toBeInTheDocument();
  });

  it("prefers a resolved extract over the loading state when both are set", () => {
    routeLoading(true);
    openedExtract(mockExtract as any);
    renderRoute();
    expect(screen.getByText("ExtractDetail Component")).toBeInTheDocument();
    expect(screen.queryByText("Loading...")).toBeNull();
  });

  // Regression guard for the navigation-loop fix (#1601). The deleted
  // ExtractLandingRoute used to redirect /e/:user/:extract → /extracts/:id,
  // which fought CentralRouteManager Phase 3's reverse redirect and tripped
  // the circuit breaker. The fix is that ExtractDetailRoute is the single
  // dumb consumer for both URL shapes; this test pins that contract by
  // confirming no internal navigation occurs from a canonical /e/ URL when
  // the extract is already resolved.
  it("renders for canonical /e/:user/:extract without redirecting", () => {
    openedExtract(mockExtract);
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/e/alice/test-extract"]}>
          <Routes>
            <Route
              path="/e/:userIdent/:extractIdent"
              element={<ExtractDetailRoute />}
            />
            <Route
              path="/extracts/:extractId"
              element={<div>SHOULD-NOT-RENDER</div>}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );
    expect(screen.getByText("ExtractDetail Component")).toBeInTheDocument();
    expect(screen.queryByText("SHOULD-NOT-RENDER")).toBeNull();
  });
});
