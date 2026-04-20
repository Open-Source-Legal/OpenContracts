import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ExtractLandingRoute } from "../ExtractLandingRoute";
import {
  openedExtract,
  routeLoading,
  routeError,
} from "../../../graphql/cache";
import type { ExtractType } from "../../../types/graphql-api";

vi.mock("../../widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Loading...</div>,
}));

vi.mock("../../widgets/ModernErrorDisplay", () => ({
  ModernErrorDisplay: ({ error }: any) => (
    <div>Error: {error?.message || error}</div>
  ),
}));

/**
 * Tests for ExtractLandingRoute.
 *
 * This is a dumb consumer that reads state from reactive vars and redirects
 * the legacy /e/:userIdent/:extractId route to the canonical
 * /extracts/:extractId path when the extract has been resolved.
 */
describe("ExtractLandingRoute", () => {
  const LocationReporter: React.FC = () => {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}</div>;
  };

  const renderRoute = () =>
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/e/user/extract-1"]}>
          <Routes>
            <Route
              path="/e/:userIdent/:extractId"
              element={<ExtractLandingRoute />}
            />
            <Route path="/extracts/:id" element={<LocationReporter />} />
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

  it("shows loading display while routeLoading is true", () => {
    routeLoading(true);
    renderRoute();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows error display when routeError is set", () => {
    routeError(new Error("Failed to resolve legacy extract"));
    renderRoute();
    expect(
      screen.getByText(/Error:.*Failed to resolve legacy extract/)
    ).toBeInTheDocument();
  });

  it("shows 'Extract not found' when no extract and no error/loading are set", () => {
    renderRoute();
    expect(screen.getByText(/Error:.*Extract not found/)).toBeInTheDocument();
  });

  it("redirects to /extracts/:id once the reactive var has an extract", async () => {
    openedExtract({
      id: "extract-1",
      name: "Legacy Extract",
    } as ExtractType);

    renderRoute();

    // The redirect effect pushes to /extracts/extract-1 and mounts
    // LocationReporter on the new route.
    await screen.findByTestId("location");
    expect(screen.getByTestId("location").textContent).toBe(
      "/extracts/extract-1"
    );
  });
});
