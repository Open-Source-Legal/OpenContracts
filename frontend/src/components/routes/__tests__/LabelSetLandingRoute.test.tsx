import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { LabelSetLandingRoute } from "../LabelSetLandingRoute";
import {
  openedLabelset,
  routeLoading,
  routeError,
} from "../../../graphql/cache";
import type { LabelSetType } from "../../../types/graphql-api";

vi.mock("../../labelsets/LabelSetDetailPage", () => ({
  LabelSetDetailPage: ({ onClose }: any) => (
    <div>
      <span>LabelSetDetailPage Component</span>
      <button onClick={onClose}>close-labelset</button>
    </div>
  ),
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
 * Tests for LabelSetLandingRoute.
 *
 * Dumb consumer of reactive vars set by CentralRouteManager; renders the
 * LabelSetDetailPage when a labelset has been resolved or surfaces
 * loading/error UI otherwise.
 */
describe("LabelSetLandingRoute", () => {
  const mockLabelset: LabelSetType = {
    id: "ls-1",
    title: "My Labels",
    description: "A set of labels",
  } as unknown as LabelSetType;

  const renderRoute = () =>
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/label_sets/ls-1"]}>
          <LabelSetLandingRoute />
        </MemoryRouter>
      </MockedProvider>
    );

  beforeEach(() => {
    openedLabelset(null);
    routeLoading(false);
    routeError(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    openedLabelset(null);
    routeLoading(false);
    routeError(null);
  });

  it("shows loading display when routeLoading is true", () => {
    routeLoading(true);
    renderRoute();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows error display when routeError is set", () => {
    routeError(new Error("Boom"));
    renderRoute();
    expect(screen.getByText(/Error:.*Boom/)).toBeInTheDocument();
  });

  it("shows 'Label set not found' when labelset is null and no loading/error is set", () => {
    renderRoute();
    expect(screen.getByText(/Error:.*Label set not found/)).toBeInTheDocument();
  });

  it("renders LabelSetDetailPage when labelset is loaded", () => {
    openedLabelset(mockLabelset);
    renderRoute();
    expect(
      screen.getByText("LabelSetDetailPage Component")
    ).toBeInTheDocument();
  });

  it("navigates to /label_sets when LabelSetDetailPage invokes onClose", async () => {
    const LocationReporter: React.FC = () => {
      const location = useLocation();
      return <div data-testid="location">{location.pathname}</div>;
    };

    openedLabelset(mockLabelset);

    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/label_sets/ls-1"]}>
          <Routes>
            <Route path="/label_sets/:id" element={<LabelSetLandingRoute />} />
            <Route path="/label_sets" element={<LocationReporter />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    const closeBtn = screen.getByRole("button", { name: "close-labelset" });
    await userEvent.click(closeBtn);

    // CentralRouteManager Phase 1 owns the openedLabelset(null) clear when
    // the new path resolves to a browse route — the route component just
    // navigates and lets the manager handle the var.
    const loc = await screen.findByTestId("location");
    expect(loc.textContent).toBe("/label_sets");
  });
});
